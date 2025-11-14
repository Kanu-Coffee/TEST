"""Bithumb REST exchange adapter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from typing import Dict, Iterable, List
from urllib.parse import urlencode

import requests

from bot.config import BotConfig

from .base import Exchange, OpenOrder, OrderResult, Quote


ERROR_HINTS: Dict[str, str] = {
    "5100": "요청 파라미터를 확인하세요.",
    "5200": "시그니처 오류입니다. API 키와 시크릿, 시스템 시간을 점검하세요.",
    "5300": "Nonce 값이 너무 낮습니다. 서버 시간과 시스템 시간 차이를 확인하세요.",
    "5400": "허용되지 않은 IP입니다. API 키에 등록된 IP를 확인하세요.",
    "5500": "해당 API 키에 필요한 권한이 없습니다.",
    "5600": "API 키가 비활성화되었습니다.",
}


def _now_ms() -> str:
    return str(int(time.time() * 1000))


class BithumbExchange(Exchange):
    def __init__(self, config: BotConfig) -> None:
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "grid-bot/1.0"})
        self._last_clock_warning = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _base_url(self) -> str:
        return self.config.bithumb.base_url.rstrip("/")

    def _signed_headers(self, endpoint: str, body: str) -> Dict[str, str]:
        cred = self.config.bithumb
        headers: Dict[str, str] = {"Api-Client-Type": "2"}
        if cred.auth_mode.lower() == "jwt":
            headers.update(
                {
                    "Authorization": f"Bearer {cred.api_key}",
                    "Content-Type": "application/json",
                }
            )
            return headers

        nonce = _now_ms()
        payload = f"{endpoint}\x00{body}\x00{nonce}".encode("utf-8")
        digest = hmac.new(cred.api_secret.encode("utf-8"), payload, hashlib.sha512).digest()
        signature = base64.b64encode(digest).decode("utf-8")
        headers.update(
            {
                "Api-Key": cred.api_key,
                "Api-Nonce": nonce,
                "Api-Sign": signature,
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        return headers

    def _private_post(self, endpoint: str, params: Dict[str, str]) -> Dict[str, object]:
        url = f"{self._base_url()}{endpoint}"
        auth_mode = self.config.bithumb.auth_mode.lower()
        try:
            if auth_mode == "jwt":
                headers = self._signed_headers(endpoint, "")
                response = self._session.post(url, headers=headers, json=params, timeout=7)
            else:
                encoded = urlencode(params or {}, doseq=True)
                headers = self._signed_headers(endpoint, encoded)
                response = self._session.post(url, headers=headers, data=encoded, timeout=7)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return {"status": "HTTP_ERROR", "message": str(exc)}
        except ValueError as exc:
            return {"status": "JSON_ERROR", "message": str(exc)}

    def _apply_hint(self, payload: Dict[str, object]) -> Dict[str, object]:
        status = str(payload.get("status", ""))
        if status in ERROR_HINTS and "hint" not in payload:
            payload = dict(payload)
            payload["hint"] = ERROR_HINTS[status]
        return payload

    # ------------------------------------------------------------------
    # Exchange interface
    # ------------------------------------------------------------------
    def fetch_quote(self) -> Quote:
        url = f"{self._base_url()}/public/ticker/{self.config.bot.symbol_ticker}"
        resp = self._session.get(url, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        price = float(data.get("closing_price", 0) or 0)
        volume = float(data.get("units_traded_24H", 0) or 0)
        server_time = 0.0
        try:
            server_time = float(data.get("date", 0) or 0) / 1000.0
        except (TypeError, ValueError):
            server_time = 0.0
        now = time.time()
        if server_time:
            drift = abs(now - server_time)
            if drift > 3 and now - self._last_clock_warning > 60:
                print(
                    f"[Bithumb] 시스템 시간과 거래소 시간 차이 {drift:.2f}s 발견. "
                    "서버 시간을 동기화하고 IP 화이트리스트, JWT 설정을 확인하세요."
                )
                self._last_clock_warning = now
        return Quote(price=price, volume_24h=volume, timestamp=now, server_time=server_time)

    def place_order(self, side: str, price: float, quantity: float) -> OrderResult:
        is_buy = side.lower() == "buy"
        if self.config.bot.dry_run:
            return OrderResult(
                True,
                f"dry-{uuid.uuid4().hex[:12]}",
                {
                    "side": side,
                    "price": price,
                    "quantity": quantity,
                    "mode": "market" if self.config.bot.use_market_orders else "limit",
                },
            )

        if self.config.bot.use_market_orders:
            endpoint = "/trade/market_buy" if is_buy else "/trade/market_sell"
            params = {
                "order_currency": self.config.bot.order_currency,
                "payment_currency": self.config.bot.payment_currency,
                "units": f"{quantity:.8f}",
            }
        else:
            endpoint = "/trade/place"
            params = {
                "order_currency": self.config.bot.order_currency,
                "payment_currency": self.config.bot.payment_currency,
                "units": f"{quantity:.8f}",
                "price": str(int(round(price))),
                "type": "bid" if is_buy else "ask",
            }

        payload = self._private_post(endpoint, params)
        payload = self._apply_hint(payload)
        status = str(payload.get("status")) if isinstance(payload, dict) else ""
        success = status == "0000"
        order_id = str(payload.get("order_id", "")) if isinstance(payload, dict) else ""
        return OrderResult(success, order_id, payload)

    def cancel_order(self, order_id: str, side: str) -> bool:
        if self.config.bot.dry_run:
            return True

        endpoint = "/trade/cancel"
        params = {
            "order_currency": self.config.bot.order_currency,
            "payment_currency": self.config.bot.payment_currency,
            "order_id": order_id,
            "type": "bid" if side.lower() == "buy" else "ask",
        }

        payload = self._private_post(endpoint, params)
        payload = self._apply_hint(payload)
        status = str(payload.get("status")) if isinstance(payload, dict) else ""
        return status == "0000"

    def list_open_orders(self) -> Iterable[OpenOrder]:
        if self.config.bot.dry_run:
            return []

        endpoint = "/info/orders"
        params = {
            "order_currency": self.config.bot.order_currency,
            "payment_currency": self.config.bot.payment_currency,
        }

        payload = self._private_post(endpoint, params)
        payload = self._apply_hint(payload)
        if not isinstance(payload, dict) or str(payload.get("status")) != "0000":
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
