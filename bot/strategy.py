"""Core trading strategy implementation."""
from __future__ import annotations

import math
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, List, Optional

from exchanges import get_exchange
from exchanges.base import Exchange, OpenOrder, OrderResult, Quote

from .config import BotConfig, StrategyBand
from .logs import TradeLogger
from .metrics import MetricsPublisher


@dataclass
class Position:
    price: float
    quantity: float


@dataclass
class StrategyState:
    positions: List[Position] = field(default_factory=list)
    realized_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    trades: int = 0
    last_trade_time: str = ""
    last_trade_pnl: float = 0.0


class EWMA:
    def __init__(self, halflife: int, floor: float, ceil: float) -> None:
        self.alpha = math.log(2) / max(1, halflife)
        self.var = max(floor, 1e-6) ** 2
        self.floor = floor
        self.ceil = ceil
        self.prev: Optional[float] = None

    def update(self, price: float) -> float:
        if self.prev is None or price <= 0:
            self.prev = price
            return self.std()
        change = math.log(price / self.prev) if self.prev > 0 else 0.0
        self.prev = price
        change = max(-0.2, min(0.2, change))
        self.var = self.alpha * (change * change) + (1 - self.alpha) * self.var
        return self.std()

    def std(self) -> float:
        value = math.sqrt(max(0.0, self.var))
        return max(self.floor, min(self.ceil, value))


class GridStrategy:
    """Grid-style split-buy strategy with volatility-aware exits."""

    def __init__(self, config: BotConfig, logger: TradeLogger, publisher: MetricsPublisher) -> None:
        self.config = config
        self.logger = logger
        self.publisher = publisher
        self.band: StrategyBand = config.active_band()
        self.exchange: Exchange = get_exchange(config.bot.exchange)(config)
        self.state = StrategyState()

        self.order_times: Deque[float] = deque(maxlen=100)
        self.last_order_ts = 0.0
        self.pending_orders: Dict[str, Dict[str, float]] = {}
        self.vol_estimator = EWMA(
            halflife=self.band.vol_halflife,
            floor=self.band.vol_min,
            ceil=self.band.vol_max,
        )
        self._last_clock_warning = 0.0

        # 초기 기준가 및 변동성 설정
        quote = self.exchange.fetch_quote()
        self.price = quote.price
        self.base_price = self.price  # ★ 최초 기준 가격은 봇 시작 시점의 가격
        self.volatility = self.vol_estimator.update(self.price)
        self.tp_ratio, self.sl_ratio = self._compute_targets(self.volatility)

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------
    def run_forever(self) -> None:
        self._publish_metrics()
        try:
            while True:
                try:
                    quote = self.exchange.fetch_quote()
                    self._handle_quote(quote)
                    self._maybe_buy()
                    self._maybe_sell()
                    self._cancel_expired_orders(quote)
                    self._log_status()
                    self._publish_metrics()
                    time.sleep(self.band.sleep_seconds + random.uniform(0.0, 0.3))
                except Exception as exc:  # pragma: no cover - defensive
                    self.logger.log_error(str(exc))
                    self._publish_metrics(status="error", error=str(exc))
                    time.sleep(5)
        finally:
            self.publisher.close()

    # ------------------------------------------------------------------
    # Quote handling
    # ------------------------------------------------------------------
    def _handle_quote(self, quote: Quote) -> None:
        self.price = quote.price
        self.volatility = self.vol_estimator.update(self.price)
        self.tp_ratio, self.sl_ratio = self._compute_targets(self.volatility)

        if quote.server_time:
            drift = abs(time.time() - quote.server_time)
            if drift > 3 and time.time() - self._last_clock_warning > 60:
                self.logger.log_error(
                    f"거래소 서버 시간과 시스템 시간 차이가 {drift:.2f}초입니다. "
                    "서버 시간 동기화와 IP/JWT 설정을 다시 확인하세요."
                )
                self._last_clock_warning = time.time()

        # 포지션이 있을 때만 base_price를 조정한다.
        # - 포지션이 생기면 평균 매수단가가 기준이 되고
        # - 물타기로 평단이 내려갈 경우 base_price도 함께 내려가게 함.
        if self.state.positions:
            total_qty = sum(p.quantity for p in self.state.positions)
            avg_price = sum(
                p.price * p.quantity for p in self.state.positions
            ) / max(total_qty, 1e-12)

            if self.base_price <= 0:
                # 혹시라도 초기값이 0이거나 깨졌다면 한 번만 재설정
                self.base_price = avg_price
            else:
                # 기존 기준가와 평단 중 더 낮은 쪽을 기준으로 유지
                self.base_price = min(self.base_price, avg_price)

        # 포지션이 하나도 없을 때는 base_price를 건드리지 않는다.
        # - 최초 실행 시: __init__에서 잡은 시작 가격을 유지
        # - 모든 포지션 청산 후: 마지막 사이클의 기준 가격을 유지
        # 이렇게 해야 base_price 아래로 내려갔을 때 그리드 매수가 동작한다.

    def _compute_targets(self, volatility: float) -> tuple[float, float]:
        tp = max(self.band.tp_floor, volatility * self.band.tp_multiplier)
        sl = max(self.band.sl_floor, volatility * self.band.sl_multiplier)
        return tp, sl

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------
    def _can_place_order(self) -> bool:
        now = time.time()
        if now - self.last_order_ts < self.band.order_cooldown:
            return False
        while self.order_times and now - self.order_times[0] > 60.0:
            self.order_times.popleft()
        return len(self.order_times) < self.band.max_orders_per_minute

    def _mark_order(self) -> None:
        ts = time.time()
        self.order_times.append(ts)
        self.last_order_ts = ts

    def _trigger_levels(self) -> List[float]:
        # base_price를 기준으로 아래 방향으로 그리드 생성
        return [
            self.base_price * (1 - self.band.buy_step * (i + 1))
            for i in range(self.band.max_steps)
        ]

    def _maybe_buy(self) -> None:
        idx = len(self.state.positions)
        if idx >= self.band.max_steps or not self._can_place_order():
            return

        trigger_price = self._trigger_levels()[idx]

        # 현재가가 트리거 가격 이하로 내려왔을 때만 매수
        if self.price > trigger_price:
            return

        order_value = self.band.base_order_value * (self.band.martingale_multiplier ** idx)
        raw_qty = self.exchange.value_to_quantity(order_value, self.price)
        quantity = self.exchange.round_quantity(raw_qty)
        price = self.exchange.round_price(self.price)
        notional = self.exchange.notional_value(price, quantity)

        if not self.exchange.is_notional_sufficient(notional, quantity):
            return

        result = self.exchange.place_order("buy", price, quantity)
        order_id = self._ensure_order_id(result)

        if result.success:
            self.state.positions.append(Position(price=price, quantity=quantity))
            self.pending_orders[order_id] = {"time": time.time(), "side": "buy"}
            self._mark_order()
            total_units = sum(p.quantity for p in self.state.positions)
            avg_price = sum(
                p.price * p.quantity for p in self.state.positions
            ) / max(total_units, 1e-12)
            self.logger.log_trade(
                event="BUY",
                side="BUY",
                price=price,
                quantity=quantity,
                notional=notional,
                profit=0.0,
                avg_price=avg_price,
                position_units=total_units,
                tp_ratio=self.tp_ratio,
                sl_ratio=self.sl_ratio,
                note=f"step={idx + 1}",
                order_id=order_id,
            )
        else:
            self.logger.log_trade(
                event="BUY_FAIL",
                side="BUY",
                price=price,
                quantity=quantity,
                notional=notional,
                profit=0.0,
                avg_price=0.0,
                position_units=0.0,
                tp_ratio=self.tp_ratio,
                sl_ratio=self.sl_ratio,
                note=str(result.raw),
                order_id=order_id,
            )

    def _maybe_sell(self) -> None:
        if not self.state.positions:
            return

        current_price = self.exchange.round_price(self.price)

        for position in list(self.state.positions):
            change = (self.price - position.price) / position.price if position.price else 0.0
            take_profit = change >= self.tp_ratio
            stop_loss = change <= -self.sl_ratio

            if not (take_profit or stop_loss):
                continue
            if not self._can_place_order():
                continue

            result = self.exchange.place_order("sell", current_price, position.quantity)
            order_id = self._ensure_order_id(result)

            if result.success:
                pnl = (current_price - position.price) * position.quantity
                self.state.realized_pnl += pnl
                self.state.trades += 1
                if pnl >= 0:
                    self.state.wins += 1
                    is_loss = False
                else:
                    self.state.losses += 1
                    is_loss = True

                self.state.positions.remove(position)
                self.pending_orders[order_id] = {"time": time.time(), "side": "sell"}
                self._mark_order()

                remaining_units = sum(p.quantity for p in self.state.positions)
                avg_price = (
                    sum(p.price * p.quantity for p in self.state.positions) / max(remaining_units, 1e-12)
                    if remaining_units
                    else 0.0
                )

                self.logger.log_trade(
                    event="SELL",
                    side="SELL",
                    price=current_price,
                    quantity=position.quantity,
                    notional=self.exchange.notional_value(current_price, position.quantity),
                    profit=pnl,
                    avg_price=avg_price,
                    position_units=remaining_units,
                    tp_ratio=self.tp_ratio,
                    sl_ratio=self.sl_ratio,
                    note="TP" if take_profit else "SL",
                    order_id=order_id,
                )
                self.logger.record_daily(pnl, pnl >= 0, is_loss)
                self.state.last_trade_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.state.last_trade_pnl = pnl
            else:
                self.logger.log_trade(
                    event="SELL_FAIL",
                    side="SELL",
                    price=current_price,
                    quantity=position.quantity,
                    notional=self.exchange.notional_value(current_price, position.quantity),
                    profit=0.0,
                    avg_price=0.0,
                    position_units=0.0,
                    tp_ratio=self.tp_ratio,
                    sl_ratio=self.sl_ratio,
                    note=str(result.raw),
                    order_id=order_id,
                )

    def _cancel_expired_orders(self, quote: Quote) -> None:
        activity = max(0.5, min(2.0, quote.volume_24h / max(self.band.cancel_volume_scale, 1e-9)))
        wait_seconds = max(
            self.band.cancel_min_wait,
            min(self.band.cancel_max_wait, self.band.cancel_base_wait * activity),
        )
        now = time.time()
        open_orders: List[OpenOrder] = list(self.exchange.list_open_orders())
        for order in open_orders:
            created = float(self.pending_orders.get(order.order_id, {}).get("time", now))
            if now - created < wait_seconds:
                continue
            if self.exchange.cancel_order(order.order_id, order.side):
                self.pending_orders.pop(order.order_id, None)

    # ------------------------------------------------------------------
    # Metrics & status
    # ------------------------------------------------------------------
    def _publish_metrics(self, *, status: str = "running", error: Optional[str] = None) -> None:
        total_units = sum(p.quantity for p in self.state.positions)
        avg_price = (
            sum(p.price * p.quantity for p in self.state.positions) / max(total_units, 1e-12)
            if total_units
            else 0.0
        )
        payload = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "exchange": self.config.bot.exchange,
            "symbol": self.config.bot.symbol_ticker,
            "price": self.price,
            "volatility": self.volatility,
            "tp_ratio": self.tp_ratio,
            "sl_ratio": self.sl_ratio,
            "positions": len(self.state.positions),
            "position_units": total_units,
            "avg_entry_price": avg_price,
            "realized_pnl": self.state.realized_pnl,
            "trades": self.state.trades,
            "wins": self.state.wins,
            "losses": self.state.losses,
            "pending_orders": len(self.pending_orders),
            "dry_run": self.config.bot.dry_run,
            "hf_mode": self.config.bot.hf_mode,
            "last_trade_time": self.state.last_trade_time,
            "last_trade_pnl": self.state.last_trade_pnl,
        }
        if error:
            payload["error"] = error
        self.publisher.publish(payload)

    def _log_status(self) -> None:
        # 30초 단위로 상태 로그 (기존 로직 유지)
        if int(time.time()) % 30 != 0:
            return
        total_units = sum(p.quantity for p in self.state.positions)
        avg_price = (
            sum(p.price * p.quantity for p in self.state.positions) / max(total_units, 1e-12)
            if total_units
            else 0.0
        )
        message = (
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] exch={self.config.bot.exchange} "
            f"price={self.price:.4f} vol~{self.volatility * 100:.2f}% "
            f"TP={self.tp_ratio * 100:.2f}% SL={self.sl_ratio * 100:.2f}% "
            f"pos={total_units:.6f} avg={avg_price:.4f} "
            f"PnL={self.state.realized_pnl:.2f} trades={self.state.trades} "
            f"W/L={self.state.wins}/{self.state.losses}"
        )
        print(message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ensure_order_id(self, result: OrderResult) -> str:
        return result.order_id or f"gen-{uuid.uuid4().hex[:12]}"


__all__ = ["GridStrategy", "EWMA"]
