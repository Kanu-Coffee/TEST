"""Bithumb REST exchange adapter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple
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

    def _rest_base_url(self) -> str:
        base = self.config.bithumb.rest_base_url or self.config.bithumb.base_url
        return base.rstrip("/")

    def _signed_headers(self, endpoint: str, body: str, *, content_type: Optional[str] = None) -> Dict[str, str]:
        cred = self.config.bithumb
        headers: Dict[str, str] = {"Api-Client-Type": "2"}
        if cred.auth_mode.lower() == "jwt":
            headers.update(
                {
                    "Authorization": f"Bearer {cred.api_key}",
                    "Content-Type": content_type or "application/json",
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
                "Content-Type": content_type or "application/x-www-form-urlencoded",
            }
        )
        return headers

    def _format_http_error(self, exc: requests.HTTPError) -> Dict[str, object]:
        payload: Dict[str, object] = {"status": "HTTP_ERROR", "message": str(exc)}
        resp = exc.response
        if resp is not None:
            payload["http_status"] = resp.status_code
            body_text = resp.text
            payload["body"] = body_text
            try:
                body_json = resp.json()
            except ValueError:
                body_json = None
            if isinstance(body_json, dict):
                body_json = self._normalise_payload(body_json)
                payload["body_json"] = body_json
                status = body_json.get("status")
                message = body_json.get("message")
                if status and "remote_status" not in payload:
                    payload["remote_status"] = status
                if message and "remote_message" not in payload:
                    payload["remote_message"] = message
        return payload

    def _attempt_post(
        self,
        *,
        url: str,
        endpoint: str,
        body: str,
        data: Optional[str],
        json_payload: Optional[Dict[str, Any]],
        content_type: str,
    ) -> Tuple[bool, Dict[str, object]]:
        headers = self._signed_headers(endpoint, body, content_type=content_type)
        request_kwargs: Dict[str, Any] = {
            "url": url,
            "headers": headers,
            "timeout": 7,
        }
        if data is not None:
            request_kwargs["data"] = data
        if json_payload is not None:
            request_kwargs["json"] = json_payload
        try:
            response = self._session.post(**request_kwargs)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                payload = self._normalise_payload(payload)
            return True, payload
        except requests.HTTPError as exc:
            return False, self._format_http_error(exc)
        except requests.RequestException as exc:
            return False, {"status": "HTTP_ERROR", "message": str(exc)}
        except ValueError as exc:
            return False, {"status": "JSON_ERROR", "message": str(exc)}

    def _private_post(
        self,
        endpoint: str,
        params: Dict[str, str],
        *,
        rest: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, object]:
        legacy_variant = self._build_legacy_variant(endpoint, params)
        rest_variant = self._build_rest_variant(rest) if rest else None
        order: List[Dict[str, Any]] = []
        if rest_variant is not None:
            if self.config.bithumb.prefer_rest:
                order.extend([rest_variant, legacy_variant])
            else:
                order.extend([legacy_variant, rest_variant])
        else:
            order.append(legacy_variant)

        if not order:
            return {"status": "HTTP_ERROR", "message": "Bithumb API endpoints are not configured."}

        if not self.config.bithumb.enable_failover and order:
            order = order[:1]

        attempts: List[Dict[str, object]] = []
        for variant in order:
            success, payload = self._attempt_post(**variant)
            if success:
                if attempts and isinstance(payload, dict):
                    payload = dict(payload)
                    payload.setdefault("failover_history", attempts)
                return payload
            attempt_payload = dict(payload)
            attempt_payload.setdefault("api_version", variant.get("name", "legacy"))
            attempt_payload.setdefault("endpoint", variant.get("endpoint", ""))
            attempts.append(attempt_payload)
            if not self.config.bithumb.enable_failover:
                return payload

        if attempts:
            return {
                "status": "HTTP_ERROR",
                "message": "모든 Bithumb API 시도가 실패했습니다.",
                "failover_history": attempts,
            }
        return {"status": "HTTP_ERROR", "message": "요청이 실패했습니다."}

    def _build_legacy_variant(self, endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
        encoded = urlencode(params or {}, doseq=True)
        return {
            "name": "legacy",
            "url": f"{self._base_url()}{endpoint}",
            "endpoint": endpoint,
            "body": encoded,
            "data": encoded,
            "json_payload": None,
            "content_type": "application/x-www-form-urlencoded",
        }

    def _build_rest_variant(self, rest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        endpoint = str(rest.get("endpoint") or "").strip()
        if not endpoint:
            return None
        params = dict(rest.get("params") or {})
        body = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
        auth_mode = self.config.bithumb.auth_mode.lower()
        if auth_mode == "jwt":
            data = None
            json_payload: Optional[Dict[str, Any]] = params
        else:
            data = body
            json_payload = None
        return {
            "name": "rest",
            "url": f"{self._rest_base_url()}{endpoint}",
            "endpoint": endpoint,
            "body": body,
            "data": data,
            "json_payload": json_payload,
            "content_type": "application/json",
        }

    def _normalise_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "status" not in payload and "code" in payload:
            payload.setdefault("status", payload.get("code"))
        if "message" not in payload and "msg" in payload:
            payload.setdefault("message", payload.get("msg"))
        if "order_id" not in payload:
            order_id = payload.get("orderId") or payload.get("orderid")
            if order_id:
                payload.setdefault("order_id", order_id)
        return payload

    def _apply_hint(self, payload: Dict[str, object]) -> Dict[str, object]:
        status = str(payload.get("status", ""))
        if status in ERROR_HINTS and "hint" not in payload:
            payload = dict(payload)
            payload["hint"] = ERROR_HINTS[status]
        remote_status = str(payload.get("remote_status", ""))
        if remote_status in ERROR_HINTS and "hint" not in payload:
            payload = dict(payload)
            payload["hint"] = ERROR_HINTS[remote_status]
        history = payload.get("failover_history")
        if isinstance(history, list):
            enriched: List[Dict[str, object]] = []
            for entry in history:
                if isinstance(entry, dict):
                    enriched.append(self._apply_hint(entry))
                else:
                    enriched.append(entry)
            if enriched != history:
                payload = dict(payload)
                payload["failover_history"] = enriched
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

        rest_payload: Optional[Dict[str, Any]] = None
        if self.config.bithumb.rest_place_endpoint:
            rest_params = {
                "symbol": self._rest_symbol(),
                "side": "BUY" if is_buy else "SELL",
                "type": "market" if self.config.bot.use_market_orders else "limit",
                "order_type": "market" if self.config.bot.use_market_orders else "limit",
                "price": str(int(round(price))) if not self.config.bot.use_market_orders else None,
                "quantity": f"{quantity:.8f}",
                "units": f"{quantity:.8f}",
                "volume": f"{quantity:.8f}",
                "order_currency": self.config.bot.order_currency,
                "payment_currency": self.config.bot.payment_currency,
            }
            rest_params = {k: v for k, v in rest_params.items() if v is not None}
            rest_endpoint = (
                self.config.bithumb.rest_market_buy_endpoint
                if self.config.bot.use_market_orders and is_buy
                else self.config.bithumb.rest_market_sell_endpoint
                if self.config.bot.use_market_orders and not is_buy
                else self.config.bithumb.rest_place_endpoint
            )
            rest_payload = {"endpoint": rest_endpoint, "params": rest_params}

        payload = self._private_post(endpoint, params, rest=rest_payload)
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

    def _rest_symbol(self) -> str:
        symbol = self.config.bot.symbol_ticker
        if self.config.bithumb.rest_symbol_dash:
            symbol = symbol.replace("_", "-")
        if self.config.bithumb.rest_symbol_upper:
            symbol = symbol.upper()
        return symbol


__all__ = ["BithumbExchange"]
