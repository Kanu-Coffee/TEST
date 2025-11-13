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
        """Return ``True`` when the order value satisfies exchange limits.

        Most exchanges enforce a minimum notional value for spot orders.  The
        bot already computes quantities so that ``price * quantity`` is at
        least ``min_notional``; however, the subsequent rounding of price and
        quantity combined with floating point precision can leave the final
        notional short by a few micro units (e.g. 4,999.9999995 instead of
        5,000).  Exchanges treat these values as valid, but the strict
        comparison would previously reject them, preventing any order from
        being submitted.  We account for that here by allowing a tiny epsilon
        when comparing against the minimum requirement.
        """

        epsilon = max(1e-6, self.min_notional() * 1e-6)
        return quantity > 0 and notional + epsilon >= self.min_notional()


__all__ = ["Exchange", "Quote", "OrderResult", "OpenOrder"]
