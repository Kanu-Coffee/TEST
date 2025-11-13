"""High-frequency split-buy bot with multi-exchange support."""
from __future__ import annotations

import csv
import math
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Tuple

from exchanges import get_exchange
from exchanges.base import Exchange, OrderResult, Quote

from .config import BotConfig, StrategyParams
from .home_assistant import HomeAssistantPublisher

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------

def _slug(config: BotConfig) -> str:
    return config.exchange.lower()


def _trade_log(config: BotConfig) -> Path:
    return DATA_DIR / f"{_slug(config)}_trades.csv"


def _error_log(config: BotConfig) -> Path:
    return DATA_DIR / f"{_slug(config)}_errors.log"


def _summary_log(config: BotConfig) -> Path:
    return DATA_DIR / f"{_slug(config)}_daily_summary.csv"


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ensure_csv_headers(config: BotConfig) -> None:
    trade_log = _trade_log(config)
    summary_log = _summary_log(config)
    if not trade_log.exists():
        with trade_log.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    "time",
                    "event",
                    "side",
                    "price",
                    "units",
                    "notional",
                    "profit",
                    "avg_price",
                    "pos_units",
                    "tp",
                    "sl",
                    "note",
                    "order_id",
                ]
            )
    if not summary_log.exists():
        with summary_log.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["date", "realized_profit", "trades", "win", "loss"])


def load_daily_summary(config: BotConfig) -> Dict[str, Dict[str, float]]:
    results: Dict[str, Dict[str, float]] = {}
    path = _summary_log(config)
    if not path.exists():
        return results
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("date")
            if not date:
                continue
            profit = row.get("realized_profit")
            if profit is None:
                profit = row.get("realized_profit_krw")
            results[date] = {
                "realized_profit": safe_float(profit),
                "trades": safe_float(row.get("trades")),
                "win": safe_float(row.get("win")),
                "loss": safe_float(row.get("loss")),
            }
    return results


def write_daily_summary(config: BotConfig, rows: Dict[str, Dict[str, float]]) -> None:
    path = _summary_log(config)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "realized_profit", "trades", "win", "loss"])
        for date in sorted(rows):
            row = rows[date]
            writer.writerow(
                [
                    date,
                    f"{row['realized_profit']:.2f}",
                    int(row["trades"]),
                    int(row["win"]),
                    int(row["loss"]),
                ]
            )


def log_trade(
    config: BotConfig,
    event: str,
    side: str,
    price: float,
    units: float,
    notional: float,
    profit: float,
    avg_price: float,
    pos_units: float,
    tp: float,
    sl: float,
    *,
    note: str = "",
    order_id: str = "",
) -> None:
    trade_log = _trade_log(config)
    with trade_log.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [
                ts(),
                event,
                side,
                f"{price:.4f}",
                f"{units:.6f}",
                f"{notional:.2f}",
                f"{profit:.2f}",
                f"{avg_price:.4f}",
                f"{pos_units:.6f}",
                f"{tp:.5f}",
                f"{sl:.5f}",
                note,
                order_id,
            ]
        )


def log_error(config: BotConfig, msg: str) -> None:
    path = _error_log(config)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts()}] {msg}\n")


# -----------------------------------------------------------------------------
# Strategy utilities
# -----------------------------------------------------------------------------


@dataclass
class EWMAStd:
    halflife: int
    floor: float
    ceil: float

    def __post_init__(self) -> None:
        self.alpha = math.log(2) / max(1, self.halflife)
        self.var = self.floor**2
        self.prev: float | None = None

    def update(self, price: float) -> float:
        if self.prev is None or price <= 0:
            self.prev = price
            return self.std()
        r = math.log(price / self.prev) if self.prev > 0 else 0.0
        self.prev = price
        r = max(-0.2, min(0.2, r))
        self.var = self.alpha * (r * r) + (1 - self.alpha) * self.var
        return self.std()

    def std(self) -> float:
        s = math.sqrt(max(0.0, self.var))
        return max(self.floor, min(self.ceil, s))


def dyn_tp_sl(params: StrategyParams, vol_est: float) -> Tuple[float, float]:
    tp = max(params.tp_floor, vol_est * params.tp_k)
    sl = max(params.sl_floor, vol_est * params.sl_k)
    return tp, sl


# -----------------------------------------------------------------------------
# Bot runner
# -----------------------------------------------------------------------------

def _select_params(config: BotConfig) -> StrategyParams:
    return config.hf_params if config.hf_mode else config.default_params


def _ensure_order_id(result: OrderResult) -> str:
    return result.order_id or f"gen-{uuid.uuid4().hex[:12]}"


def run_bot(config: BotConfig | None = None) -> None:
    config = config or BotConfig.load()
    ensure_csv_headers(config)
    summary_cache = load_daily_summary(config)

    exchange_cls = get_exchange(config.exchange)
    exchange: Exchange = exchange_cls(config)
    params = _select_params(config)

    positions: List[Tuple[float, float]] = []
    realized = 0.0
    win = loss = trades = 0
    last_trade_time = ""
    last_trade_pnl = 0.0

    order_times: Deque[float] = deque(maxlen=100)
    last_order = 0.0

    vol_estimator = EWMAStd(
        halflife=params.vol_halflife,
        floor=params.vol_min,
        ceil=params.vol_max,
    )

    quote = exchange.fetch_quote()
    price = quote.price
    base = price
    vol = vol_estimator.update(price)
    tp_r, sl_r = dyn_tp_sl(params, vol)

    print(
        f"🚀 EXCHANGE={config.exchange} HF={config.hf_mode} START price={price:.4f} "
        f"vol~{vol * 100:.2f}%"
    )

    publisher = HomeAssistantPublisher(config, DATA_DIR, on_error=lambda msg: log_error(config, msg))

    pending: Dict[str, Dict[str, float | str]] = {}

    def emit_metrics(status: str = "running", error_message: str | None = None) -> None:
        total_units = sum(u for _, u in positions)
        avg_price = sum(p * u for p, u in positions) / total_units if total_units > 0 else 0.0
        payload = {
            "timestamp": ts(),
            "status": status,
            "exchange": config.exchange,
            "symbol": config.symbol_ticker,
            "price": price,
            "volatility": vol,
            "tp_ratio": tp_r,
            "sl_ratio": sl_r,
            "positions": len(positions),
            "position_units": total_units,
            "avg_entry_price": avg_price,
            "realized_pnl": realized,
            "trades": trades,
            "wins": win,
            "losses": loss,
            "pending_orders": len(pending),
            "dry_run": config.dry_run,
            "hf_mode": config.hf_mode,
            "last_trade_time": last_trade_time,
            "last_trade_pnl": last_trade_pnl,
        }
        if error_message:
            payload["error"] = error_message
        publisher.publish(payload)

    def can_order() -> bool:
        nonlocal last_order
        now = time.time()
        if now - last_order < params.order_cooldown:
            return False
        while order_times and now - order_times[0] > 60.0:
            order_times.popleft()
        return len(order_times) < params.max_orders_min

    def mark_order() -> None:
        nonlocal last_order
        order_times.append(time.time())
        last_order = time.time()

    def record_daily(pnl_value: float, did_win: bool, did_loss: bool) -> None:
        date_key = datetime.now().strftime("%Y-%m-%d")
        row = summary_cache.setdefault(
            date_key,
            {"realized_profit": 0.0, "trades": 0.0, "win": 0.0, "loss": 0.0},
        )
        row["realized_profit"] += pnl_value
        row["trades"] += 1
        if did_win:
            row["win"] += 1
        if did_loss:
            row["loss"] += 1
        write_daily_summary(config, summary_cache)

    try:
        emit_metrics()
        while True:
            try:
                quote = exchange.fetch_quote()
                price = quote.price
                vol = vol_estimator.update(price)
                tp_r, sl_r = dyn_tp_sl(params, vol)

                # ---------- 여기부터 수정 ----------
                if positions:
                    tot_units = sum(u for _, u in positions)
                    avg_price = sum(p * u for p, u in positions) / max(1e-12, tot_units)

                    # base 가 아직 0이거나 음수면 한 번만 세팅
                    if base <= 0:
                        base = avg_price
                    else:
                        # 기존 기준가와 평균 매수가 중 더 낮은 쪽을 유지
                        base = min(base, avg_price)
                # 포지션이 하나도 없을 때는 base 를 건드리지 않는다.
                # (초기값은 맨 위에서 첫 quote 기준으로 한 번만 세팅됨)
                # ---------- 수정 끝 ----------


                triggers = [base * (1 - params.buy_step * (i + 1)) for i in range(params.max_steps)]
                next_idx = len(positions)

                if next_idx < params.max_steps and can_order():
                    trigger = triggers[next_idx]
                    if price <= trigger:
                        order_value = params.base_order_value * (params.martingale_mul**next_idx)
                        raw_qty = exchange.value_to_quantity(order_value, price)
                        qty = exchange.round_quantity(raw_qty)
                        ord_price = exchange.round_price(price)
                        notional = exchange.notional_value(ord_price, qty)
                        if exchange.is_notional_sufficient(notional, qty):
                            result = exchange.place_order("buy", ord_price, qty)
                            if result.success:
                                oid = _ensure_order_id(result)
                                positions.append((ord_price, qty))
                                pending[oid] = {"time": time.time(), "side": "buy"}
                                mark_order()
                                total_units = sum(u for _, u in positions)
                                avg_price = sum(p * u for p, u in positions) / total_units
                                log_trade(
                                    config,
                                    "BUY_ATTEMPT",
                                    "BUY",
                                    ord_price,
                                    qty,
                                    notional,
                                    0.0,
                                    avg_price,
                                    total_units,
                                    tp_r,
                                    sl_r,
                                    note=f"step={next_idx + 1}",
                                    order_id=oid,
                                )
                                print(
                                    f"✅ BUY {config.exchange} step{next_idx + 1}: "
                                    f"price={ord_price:.4f} qty={qty:.4f} | oid={oid}"
                                )
                            else:
                                log_trade(
                                    config,
                                    "BUY_FAIL",
                                    "BUY",
                                    ord_price,
                                    qty,
                                    notional,
                                    0.0,
                                    0.0,
                                    0.0,
                                    tp_r,
                                    sl_r,
                                    note=str(result.raw),
                                )

                for bp, qty in list(positions):
                    change = (price - bp) / bp if bp else 0.0
                    take = change >= tp_r
                    stop = change <= -sl_r
                    if (take or stop) and can_order():
                        ord_price = exchange.round_price(price)
                        result = exchange.place_order("sell", ord_price, qty)
                        if result.success:
                            oid = _ensure_order_id(result)
                            pnl = (ord_price - bp) * qty
                            realized += pnl
                            trades += 1
                            did_win = pnl >= 0
                            win += 1 if did_win else 0
                            loss += 1 if not did_win else 0
                            positions.remove((bp, qty))
                            pending[oid] = {"time": time.time(), "side": "sell"}
                            mark_order()
                            remaining_units = sum(u for _, u in positions)
                            avg_price = (
                                sum(p * u for p, u in positions) / remaining_units if remaining_units > 0 else 0.0
                            )
                            log_trade(
                                config,
                                "SELL",
                                "SELL",
                                ord_price,
                                qty,
                                exchange.notional_value(ord_price, qty),
                                pnl,
                                avg_price,
                                remaining_units,
                                tp_r,
                                sl_r,
                                note="TP" if take else "SL",
                                order_id=oid,
                            )
                            record_daily(pnl, did_win, not did_win)
                            last_trade_time = ts()
                            last_trade_pnl = pnl
                            print(
                                f"💰 SELL {config.exchange} {'TP' if take else 'SL'}: "
                                f"price={ord_price:.4f} pnl={pnl:.2f} | cum={realized:.2f} | oid={oid}"
                            )
                        else:
                            log_trade(
                                config,
                                "SELL_FAIL",
                                "SELL",
                                ord_price,
                                qty,
                                exchange.notional_value(ord_price, qty),
                                0.0,
                                0.0,
                                0.0,
                                tp_r,
                                sl_r,
                                note=str(result.raw),
                            )

                wait_seconds = max(
                    params.cancel_min_wait,
                    min(
                        params.cancel_max_wait,
                        params.cancel_base_wait * max(0.5, min(2.0, quote.volume_24h / params.cancel_vol_scale)),
                    ),
                )

                for order in exchange.list_open_orders():
                    created = pending.get(order.order_id, {}).get("time", time.time())
                    if time.time() - float(created) >= wait_seconds:
                        if exchange.cancel_order(order.order_id, order.side):
                            print("🕒 cancel", order.order_id, order.side)
                        pending.pop(order.order_id, None)

                if int(time.time()) % 30 == 0:
                    total_units = sum(u for _, u in positions)
                    avg_price = (
                        sum(p * u for p, u in positions) / total_units if total_units > 0 else 0.0
                    )
                    print(
                        f"[{ts()}] exch={config.exchange} price={price:.4f} vol~{vol * 100:.2f}% "
                        f"TP={tp_r * 100:.2f}% SL={sl_r * 100:.2f}% pos={total_units:.6f} avg={avg_price:.4f} "
                        f"PnL={realized:.2f} trades={trades} W/L={win}/{loss}"
                    )

                emit_metrics()
                time.sleep(params.sleep_sec + random.uniform(0.0, 0.3))
            except Exception as exc:  # pragma: no cover - defensive
                log_error(config, str(exc))
                print("⚠️ ERROR:", exc)
                emit_metrics(status="error", error_message=str(exc))
                time.sleep(5)
    finally:
        publisher.close()


def main() -> None:
    try:
        run_bot()
    except Exception as exc:  # pragma: no cover - defensive
        cfg = BotConfig.load()
        log_error(cfg, f"FATAL:{exc}")
        print("FATAL:", exc)


if __name__ == "__main__":
    main()
