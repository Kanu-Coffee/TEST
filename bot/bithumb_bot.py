"""High-frequency split-buy bot for the Bithumb USDT/KRW market."""
from __future__ import annotations

import csv
import hashlib
import hmac
import math
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Tuple
from urllib.parse import urlencode

import requests

from .config import BotConfig, StrategyParams
from .home_assistant import HomeAssistantPublisher

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TRADE_LOG = DATA_DIR / "bithumb_trades.csv"
ERROR_LOG = DATA_DIR / "bithumb_errors.log"
SUMMARY_LOG = DATA_DIR / "bithumb_daily_summary.csv"


# ----------------------------------------------------------------------------
# Utility helpers
# ----------------------------------------------------------------------------
def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def krw_round(x: float) -> int:
    return int(round(x))


def safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ensure_csv_headers() -> None:
    if not TRADE_LOG.exists():
        with TRADE_LOG.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    "time",
                    "event",
                    "side",
                    "price",
                    "units",
                    "profit",
                    "avg_price",
                    "pos_units",
                    "tp",
                    "sl",
                    "note",
                    "order_id",
                ]
            )
    if not SUMMARY_LOG.exists():
        with SUMMARY_LOG.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["date", "realized_profit_krw", "trades", "win", "loss"])


def load_daily_summary() -> Dict[str, Dict[str, float]]:
    results: Dict[str, Dict[str, float]] = {}
    if not SUMMARY_LOG.exists():
        return results
    with SUMMARY_LOG.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("date")
            if not date:
                continue
            results[date] = {
                "realized_profit_krw": safe_float(row.get("realized_profit_krw")),
                "trades": safe_float(row.get("trades")),
                "win": safe_float(row.get("win")),
                "loss": safe_float(row.get("loss")),
            }
    return results


def write_daily_summary(rows: Dict[str, Dict[str, float]]) -> None:
    with SUMMARY_LOG.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "realized_profit_krw", "trades", "win", "loss"])
        for date in sorted(rows):
            row = rows[date]
            writer.writerow(
                [
                    date,
                    f"{row['realized_profit_krw']:.2f}",
                    int(row["trades"]),
                    int(row["win"]),
                    int(row["loss"]),
                ]
            )


def log_trade(
    event: str,
    side: str,
    price: float,
    units: float,
    profit: float,
    avg_price: float,
    pos_units: float,
    tp: float,
    sl: float,
    *,
    note: str = "",
    order_id: str = "",
) -> None:
    with TRADE_LOG.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [
                ts(),
                event,
                side,
                price,
                f"{units:.6f}",
                f"{profit:.2f}",
                f"{avg_price:.2f}",
                f"{pos_units:.6f}",
                f"{tp:.5f}",
                f"{sl:.5f}",
                note,
                order_id,
            ]
        )


def log_error(msg: str) -> None:
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{ts()}] {msg}\n")


# ----------------------------------------------------------------------------
# Authentication helpers
# ----------------------------------------------------------------------------
def _now_ms() -> str:
    return str(int(time.time() * 1000))


def headers_legacy(endpoint: str, params: Dict[str, str], config: BotConfig) -> Dict[str, str]:
    query = urlencode(params) if params else ""
    nonce = _now_ms()
    payload = f"{endpoint}\x00{query}\x00{nonce}".encode("utf-8")
    sig = hmac.new(config.auth.api_secret.encode("utf-8"), payload, hashlib.sha512).hexdigest()
    return {
        "Api-Key": config.auth.api_key,
        "Api-Nonce": nonce,
        "Api-Sign": sig,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def headers_jwt_dummy(config: BotConfig) -> Dict[str, str]:
    return {"Authorization": f"Bearer {config.auth.api_key}", "Content-Type": "application/json"}


def signed_headers(endpoint: str, params: Dict[str, str], config: BotConfig) -> Dict[str, str]:
    if config.auth.auth_mode == "legacy":
        return headers_legacy(endpoint, params, config)
    if config.auth.auth_mode == "jwt":
        return headers_jwt_dummy(config)
    return {}


# ----------------------------------------------------------------------------
# Network helpers
# ----------------------------------------------------------------------------
def http_get(url: str, **kwargs):
    return requests.get(url, timeout=5, **kwargs)


def http_post(url: str, headers=None, data=None, json=None):
    return requests.post(url, headers=headers, data=data, json=json, timeout=7)


# ----------------------------------------------------------------------------
# Strategy utilities
# ----------------------------------------------------------------------------
@dataclass
class EWMAStd:
    halflife: int
    floor: float
    ceil: float

    def __post_init__(self):
        self.alpha = math.log(2) / max(1, self.halflife)
        self.var = self.floor ** 2
        self.prev = None

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


# ----------------------------------------------------------------------------
# Core bot logic
# ----------------------------------------------------------------------------
def get_ticker_price_and_vol(config: BotConfig) -> Tuple[float, float]:
    r = http_get(f"{config.auth.base_url}/public/ticker/{config.symbol_ticker}")
    j = r.json()
    data = j.get("data", {})
    return safe_float(data.get("closing_price")), safe_float(data.get("units_traded_24H"))


def place_order(order_type: str, price: int, units: float, config: BotConfig) -> Dict[str, str]:
    endpoint = "/trade/place"
    params = {
        "order_currency": config.order_currency,
        "payment_currency": config.payment_currency,
        "units": f"{units:.8f}",
        "price": str(price),
        "type": order_type,
    }
    if config.dry_run:
        return {"status": "0000", "order_id": f"dry-{uuid.uuid4().hex[:12]}"}
    headers = signed_headers(endpoint, params, config)
    r = http_post(config.auth.base_url + endpoint, headers=headers, data=params)
    return r.json()


def cancel_order(order_id: str, order_type: str, config: BotConfig) -> Dict[str, str]:
    endpoint = "/trade/cancel"
    params = {
        "order_currency": config.order_currency,
        "payment_currency": config.payment_currency,
        "order_id": order_id,
        "type": order_type,
    }
    if config.dry_run:
        return {"status": "0000"}
    headers = signed_headers(endpoint, params, config)
    r = http_post(config.auth.base_url + endpoint, headers=headers, data=params)
    return r.json()


def get_open_orders(config: BotConfig) -> Iterable[Dict[str, str]]:
    endpoint = "/info/orders"
    params = {
        "order_currency": config.order_currency,
        "payment_currency": config.payment_currency,
    }
    if config.dry_run:
        return []
    headers = signed_headers(endpoint, params, config)
    r = http_post(config.auth.base_url + endpoint, headers=headers, data=params)
    j = r.json()
    if j.get("status") == "0000":
        return j.get("data") or []
    return []


# ----------------------------------------------------------------------------
# Bot runner
# ----------------------------------------------------------------------------
def _select_params(config: BotConfig) -> StrategyParams:
    return config.hf_params if config.hf_mode else config.default_params


def run_bot(config: BotConfig | None = None) -> None:
    config = config or BotConfig.load()
    params = _select_params(config)
    ensure_csv_headers()
    daily_summary = load_daily_summary()

    positions: List[Tuple[int, float]] = []
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

    price, vol24 = get_ticker_price_and_vol(config)
    base = price
    vol = vol_estimator.update(price)
    tp_r, sl_r = dyn_tp_sl(params, vol)

    print(
        f"🚀 HF={config.hf_mode} START base={base:.0f} px={price:.0f} 24hVol={vol24:.2f}  "
        f"vol~{vol * 100:.2f}%"
    )

    publisher = HomeAssistantPublisher(config, DATA_DIR, on_error=log_error)

    pending: Dict[str, Dict[str, float]] = {}

    def emit_metrics(status: str = "running", error_message: str | None = None) -> None:
        tot_units = sum(u for _, u in positions)
        avg_price = sum(p * u for p, u in positions) / tot_units if tot_units > 0 else 0.0
        payload = {
            "timestamp": ts(),
            "status": status,
            "symbol": config.symbol_ticker,
            "price": price,
            "volatility": vol,
            "tp_ratio": tp_r,
            "sl_ratio": sl_r,
            "positions": len(positions),
            "position_units": tot_units,
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
        row = daily_summary.setdefault(
            date_key,
            {"realized_profit_krw": 0.0, "trades": 0.0, "win": 0.0, "loss": 0.0},
        )
        row["realized_profit_krw"] += pnl_value
        row["trades"] += 1
        if did_win:
            row["win"] += 1
        if did_loss:
            row["loss"] += 1
        write_daily_summary(daily_summary)

    try:
        emit_metrics()

        while True:
            try:
                price_now, vol_now = get_ticker_price_and_vol(config)
                dvol = max(vol_now - vol24, 1.0)
                vol24 = vol_now

                activity = max(0.5, min(2.0, dvol / params.cancel_vol_scale))
                wait_s = max(
                    params.cancel_min_wait,
                    min(params.cancel_max_wait, params.cancel_base_wait * activity),
                )

                for od in get_open_orders(config):
                    oid = od.get("order_id")
                    side = od.get("type", "bid")
                    created = pending.get(oid, {}).get("time", time.time())
                    if (time.time() - created) >= wait_s:
                        cr = cancel_order(oid, side, config)
                        print("🕒 cancel", oid, side, "→", cr.get("status"))
                        pending.pop(oid, None)

                price = price_now
                vol = vol_estimator.update(price)
                tp_r, sl_r = dyn_tp_sl(params, vol)

                if positions:
                    tot_units = sum(u for _, u in positions)
                    avg_price = sum(p * u for p, u in positions) / max(1e-12, tot_units)
                    base = min(base, avg_price)
                else:
                    base = price

                triggers = [base * (1 - params.buy_step * (i + 1)) for i in range(params.max_steps)]
                next_idx = len(positions)

                if next_idx < params.max_steps and can_order():
                    buy_trg = triggers[next_idx]
                    if price <= buy_trg:
                        krw = params.base_krw * (params.martingale_mul ** next_idx)
                        px = krw_round(price)
                        units = krw / max(1, px)
                        if krw >= 5000:
                            res = place_order("bid", px, units, config)
                            if res.get("status") == "0000":
                                oid = res.get("order_id", "")
                                positions.append((px, units))
                                pending[oid] = {"time": time.time(), "side": "bid"}
                                mark_order()
                                tot_units = sum(u for _, u in positions)
                                avg_price = sum(p * u for p, u in positions) / tot_units
                                log_trade(
                                    "BUY_ATTEMPT",
                                    "BUY",
                                    px,
                                    units,
                                    0.0,
                                    avg_price,
                                    tot_units,
                                    tp_r,
                                    sl_r,
                                    note=f"step={next_idx + 1}",
                                    order_id=oid,
                                )
                                print(f"✅ BUY step{next_idx + 1}: {px} × {units:.6f} | oid={oid}")
                            else:
                                log_trade(
                                    "BUY_FAIL",
                                    "BUY",
                                    px,
                                    units,
                                    0.0,
                                    0.0,
                                    0.0,
                                    tp_r,
                                    sl_r,
                                    note=str(res),
                                )

                for (bp, u) in list(positions):
                    change = (price - bp) / bp
                    take = change >= tp_r
                    stop = change <= -sl_r
                    if (take or stop) and can_order():
                        px = krw_round(price)
                        res = place_order("ask", px, u, config)
                        if res.get("status") == "0000":
                            oid = res.get("order_id", "")
                            pnl = (px - bp) * u
                            realized += pnl
                            trades += 1
                            win += 1 if pnl >= 0 else 0
                            loss += 1 if pnl < 0 else 0
                            positions.remove((bp, u))
                            pending[oid] = {"time": time.time(), "side": "ask"}
                            mark_order()
                            tot_units = sum(xu for _, xu in positions)
                            avg_price = (
                                sum(pp * uu for pp, uu in positions) / tot_units if tot_units > 0 else 0.0
                            )
                            log_trade(
                                "SELL",
                                "SELL",
                                px,
                                u,
                                pnl,
                                avg_price,
                                tot_units,
                                tp_r,
                                sl_r,
                                note=("TP" if take else "SL"),
                                order_id=oid,
                            )
                            record_daily(pnl, pnl >= 0, pnl < 0)
                            last_trade_time = ts()
                            last_trade_pnl = pnl
                            print(
                                f"💰 SELL {'TP' if take else 'SL'}: {px}, pnl={pnl:.2f} "
                                f"| cum={realized:.2f} | oid={oid}"
                            )
                        else:
                            log_trade(
                                "SELL_FAIL",
                                "SELL",
                                px,
                                u,
                                0.0,
                                0.0,
                                0.0,
                                tp_r,
                                sl_r,
                                note=str(res),
                            )

                if int(time.time()) % 30 == 0:
                    tot_units = sum(u for _, u in positions)
                    avg_price = (
                        sum(p * u for p, u in positions) / tot_units if tot_units > 0 else 0.0
                    )
                    print(
                        f"[{ts()}] px={price:.0f} vol~{vol * 100:.2f}% TP={tp_r * 100:.2f}% "
                        f"SL={sl_r * 100:.2f}% pos={tot_units:.6f} avg={avg_price:.2f} "
                        f"PnL={realized:.2f} trades={trades} W/L={win}/{loss}"
                    )

                emit_metrics()
                time.sleep(params.sleep_sec + random.uniform(0.0, 0.3))
            except Exception as exc:  # pragma: no cover - defensive
                log_error(str(exc))
                print("⚠️ ERROR:", exc)
                emit_metrics(status="error", error_message=str(exc))
                time.sleep(5)
    finally:
        publisher.close()


def main() -> None:
    try:
        run_bot()
    except Exception as exc:  # pragma: no cover - defensive
        log_error(f"FATAL:{exc}")
        print("FATAL:", exc)


if __name__ == "__main__":
    main()
