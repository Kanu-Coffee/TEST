"""Bithumb REST exchange adapter."""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from typing import Dict, Iterable, List

import requests

from bot.config import BotConfig

from .base import Exchange, OpenOrder, OrderResult, Quote


def _now_ms() -> str:
    return str(int(time.time() * 1000))


class BithumbExchange(Exchange):
    def __init__(self, config: BotConfig) -> None:
        super().__init__(config)
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _base_url(self) -> str:
        return self.config.bithumb.base_url.rstrip("/")

    def _signed_headers(self, endpoint: str, params: Dict[str, str]) -> Dict[str, str]:
        cred = self.config.bithumb
        if cred.auth_mode.lower() == "jwt":
            return {"Authorization": f"Bearer {cred.api_key}", "Content-Type": "application/json"}
        query = "&".join(f"{key}={value}" for key, value in params.items()) if params else ""
        nonce = _now_ms()
        payload = f"{endpoint}\x00{query}\x00{nonce}".encode("utf-8")
        signature = hmac.new(cred.api_secret.encode("utf-8"), payload, hashlib.sha512).hexdigest()
        return {
            "Api-Key": cred.api_key,
            "Api-Nonce": nonce,
            "Api-Sign": signature,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    # ------------------------------------------------------------------
    # Exchange interface
    # ------------------------------------------------------------------
    def fetch_quote(self) -> Quote:
        url = f"{self._base_url()}/public/ticker/{self.config.bot.symbol_ticker}"
        resp = self._session.get(url, timeout=5)
        data = resp.json().get("data", {})
        price = float(data.get("closing_price", 0) or 0)
        volume = float(data.get("units_traded_24H", 0) or 0)
        return Quote(price=price, volume_24h=volume)

    def place_order(self, side: str, price: float, quantity: float) -> OrderResult:
        endpoint = "/trade/place"
        params = {
            "order_currency": self.config.bot.order_currency,
            "payment_currency": self.config.bot.payment_currency,
            "units": f"{quantity:.8f}",
            "price": str(int(round(price))),
            "type": "bid" if side.lower() == "buy" else "ask",
        }
        if self.config.bot.dry_run:
            return OrderResult(True, f"dry-{uuid.uuid4().hex[:12]}", params)
        headers = self._signed_headers(endpoint, params)
        resp = self._session.post(self._base_url() + endpoint, headers=headers, data=params, timeout=7)
        payload = resp.json()
        success = payload.get("status") == "0000"
        return OrderResult(success, payload.get("order_id", ""), payload)

    def cancel_order(self, order_id: str, side: str) -> bool:
        endpoint = "/trade/cancel"
        params = {
            "order_currency": self.config.bot.order_currency,
            "payment_currency": self.config.bot.payment_currency,
            "order_id": order_id,
            "type": "bid" if side.lower() == "buy" else "ask",
        }
        if self.config.bot.dry_run:
            return True
        headers = self._signed_headers(endpoint, params)
        resp = self._session.post(self._base_url() + endpoint, headers=headers, data=params, timeout=7)
        payload = resp.json()
        return payload.get("status") == "0000"

    def list_open_orders(self) -> Iterable[OpenOrder]:
        endpoint = "/info/orders"
        params = {
            "order_currency": self.config.bot.order_currency,
            "payment_currency": self.config.bot.payment_currency,
        }
        if self.config.bot.dry_run:
            return []
        headers = self._signed_headers(endpoint, params)
        resp = self._session.post(self._base_url() + endpoint, headers=headers, data=params, timeout=7)
        payload = resp.json()
        if payload.get("status") != "0000":
            return []
        rows: List[OpenOrder] = []
        for row in payload.get("data") or []:
            rows.append(
                OpenOrder(
                    order_id=str(row.get("order_id")),
                    side="buy" if str(row.get("type", "bid")).lower() == "bid" else "sell",
                )
            )
        return rows

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------
    def round_price(self, price: float) -> float:
        return float(int(round(price)))

    def round_quantity(self, quantity: float) -> float:
        return round(quantity, 8)

    def min_notional(self) -> float:
        return 5000.0


__all__ = ["BithumbExchange"]
