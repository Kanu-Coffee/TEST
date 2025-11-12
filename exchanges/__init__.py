"""Exchange factory utilities."""
from __future__ import annotations

from typing import Type

from .base import Exchange
from .bithumb import BithumbExchange
from .kis import KisExchange

EXCHANGE_MAP = {
    "BITHUMB": BithumbExchange,
    "KIS": KisExchange,
}


def get_exchange(name: str) -> Type[Exchange]:
    key = (name or "BITHUMB").strip().upper()
    try:
        return EXCHANGE_MAP[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported exchange: {name}") from exc

__all__ = ["get_exchange", "Exchange"]
