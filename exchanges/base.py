"""Base classes for exchange adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from bot.config import BotConfig


@dataclass
class Quote:
    price: float
    volume_24h: float


@dataclass
class OrderResult:
    success: bool
    order_id: str
    raw: Any


@dataclass
class OpenOrder:
    order_id: str
    side: str


class Exchange:
    """Abstract exchange interface consumed by the trading loop."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Required API
    # ------------------------------------------------------------------
    def fetch_quote(self) -> Quote:
        raise NotImplementedError

    def place_order(self, side: str, price: float, quantity: float) -> OrderResult:
        raise NotImplementedError

    def cancel_order(self, order_id: str, side: str) -> bool:
        raise NotImplementedError

    def list_open_orders(self) -> Iterable[OpenOrder]:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------
    def round_price(self, price: float) -> float:
        return price

    def round_quantity(self, quantity: float) -> float:
        return quantity

    def value_to_quantity(self, order_value: float, price: float) -> float:
        if price <= 0:
            return 0.0
        return order_value / price

    def notional_value(self, price: float, quantity: float) -> float:
        return price * quantity

    def min_notional(self) -> float:
        return 0.0

    def is_notional_sufficient(self, notional: float, quantity: float) -> bool:
        return notional >= self.min_notional() and quantity > 0


__all__ = ["Exchange", "Quote", "OrderResult", "OpenOrder"]
