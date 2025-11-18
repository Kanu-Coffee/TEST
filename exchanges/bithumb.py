"""Bithumb REST exchange adapter."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlencode

import jwt
import requests

from bot.config import BotConfig

from .base import Exchange, OpenOrder, OrderResult, Quote


ERROR_HINTS: Dict[str, str] = {
    "5100": "요청 파라미터를 확인하세요.",
    "5200": "시그니처 오류입니다. API 키와 시크릿, 시스템 시간을 점검하세요.",
    "5300": "API 키가 잘못되었거나 Nonce가 중복되었습니다. 키·시크릿·권한과 시스템 시간을 다시 확인하세요.",
    "5400": "허용되지 않은 IP입니다. API 키에 등록된 IP를 확인하세요.",
    "5500": "해당 API 키에 필요한 권한이 없습니다.",
    "5600": "API 키가 비활성화되었습니다.",
}

MESSAGE_HINTS: Dict[str, str] = {
    "invalid apikey": "API 키 또는 시크릿이 올바른지, 주문 권한과 IP 화이트리스트가 맞는지 확인하세요.",
    "invalid api key": "API 키 또는 시크릿이 올바른지, 주문 권한과 IP 화이트리스트가 맞는지 확인하세요.",
    "invalid signature": "시그니처가 맞는지, 시크릿과 요청 본문·nonce 생성 방식을 다시 확인하세요.",
    "nonce is too low": "Nonce가 중복되었습니다. 시스템 시간을 NTP로 동기화하고 동시에 여러 주문을 보내지 않았는지 확인하세요.",
}
class BithumbExchange(Exchange):
    def __init__(self, config: BotConfig) -> None:
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "grid-bot/1.0"})
        self._last_clock_warning = 0.0
        self._last_nonce = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _base_url(self) -> str:
        return self.config.bithumb.base_url.rstrip("/")

    def _rest_base_url(self) -> str:
        base = self.config.bithumb.rest_base_url or self.config.bithumb.base_url
        return base.rstrip("/")

    def _next_nonce(self) -> str:
        now = int(time.time() * 1000)
        if now <= self._last_nonce:
            now = self._last_nonce + 1
        self._last_nonce = now
        return str(now)

    def _signed_headers(
        self,
        endpoint: str,
        body: str,
        *,
        content_type: Optional[str] = None,
        signature_style: str = "hex",
        signature_payload: str = "endpoint_body_nonce",
        hash_source: Optional[str] = None,
    ) -> Dict[str, str]:
        cred = self.config.bithumb
        headers: Dict[str, str] = {"Api-Client-Type": "2"}
        auth_mode = cred.auth_mode.lower()
        if auth_mode == "jwt":
            headers.update(
                self._jwt_headers(
                    hash_source=hash_source or body,
                    content_type=content_type or "application/json",
                )
            )
            return headers

        nonce = self._next_nonce()
        if signature_payload == "body_only":
            payload_bytes = body.encode("utf-8")
        elif signature_payload == "body_nonce":
            payload_bytes = f"{body}\x00{nonce}".encode("utf-8")
        else:
            payload_bytes = f"{endpoint}\x00{body}\x00{nonce}".encode("utf-8")
        mac = hmac.new(cred.api_secret.encode("utf-8"), payload_bytes, hashlib.sha512)
        if signature_style.lower() == "hex":
            digest_bytes = mac.hexdigest().encode("utf-8")
        else:
            digest_bytes = mac.digest()
        signature = base64.b64encode(digest_bytes).decode("utf-8")
        headers.update(
            {
                "Api-Key": cred.api_key,
                "Api-Nonce": nonce,
                "Api-Sign": signature,
                "Content-Type": content_type or "application/x-www-form-urlencoded",
            }
        )
        return headers

    def _jwt_headers(self, *, hash_source: str, content_type: str) -> Dict[str, str]:
        cred = self.config.bithumb
        if not cred.api_key or not cred.api_secret:
            raise ValueError("Bithumb JWT mode requires api_key and api_secret")
        hash_bytes = hash_source.encode("utf-8") if hash_source else b""
        query_hash = hashlib.sha512(hash_bytes).hexdigest()
        payload = {
            "access_key": cred.api_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "query_hash": query_hash,
            "query_hash_alg": "SHA512",
        }
        token = jwt.encode(payload, cred.api_secret, algorithm="HS256")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        }

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
        signature_style: str = "digest",
        signature_payload: str = "endpoint_body_nonce",
        hash_source: Optional[str] = None,
        **_: Any,
    ) -> Tuple[bool, Dict[str, object]]:
        headers = self._signed_headers(
            endpoint,
            body,
            content_type=content_type,
            signature_style=signature_style,
            signature_payload=signature_payload,
            hash_source=hash_source,
        )
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
        if self.config.bithumb.auth_mode != "jwt":
            if not self.config.bithumb.api_key or not self.config.bithumb.api_secret:
                return {
                    "status": "CONFIG_ERROR",
                    "message": "Bithumb API 키나 시크릿이 비어 있습니다.",
                    "hint": "Home Assistant 애드온 설정 또는 config/bot_config.yaml에 API 키와 시크릿을 입력했는지 확인하세요.",
                }
        else:
            if not self.config.bithumb.api_key or not self.config.bithumb.api_secret:
                return {
                    "status": "CONFIG_ERROR",
                    "message": "Bithumb JWT 주문에는 Access Key와 Secret이 모두 필요합니다.",
                    "hint": "애드온 설정의 BITHUMB_API_KEY, BITHUMB_API_SECRET 값을 다시 확인하세요.",
                }

        legacy_variants = self._build_legacy_variants(endpoint, params)
        rest_variant = self._build_rest_variant(rest) if rest else None
        order: List[Dict[str, Any]] = []
        if rest_variant is not None and self.config.bithumb.prefer_rest:
            order.append(rest_variant)
        order.extend(legacy_variants)
        if rest_variant is not None and not self.config.bithumb.prefer_rest:
            order.append(rest_variant)

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

    def _build_legacy_variants(
        self,
        endpoint: str,
        params: Dict[str, str],
        *,
        signature_style: str = "hex",
    ) -> List[Dict[str, Any]]:
        encoded = urlencode(params or {}, doseq=True)
        base_payload = {
            "url": f"{self._base_url()}{endpoint}",
            "endpoint": endpoint,
            "body": encoded,
            "data": encoded,
            "json_payload": None,
            "content_type": "application/x-www-form-urlencoded",
        }
        combos = [
            ("legacy", "endpoint_body_nonce", signature_style),
            ("legacy-digest", "endpoint_body_nonce", "digest"),
            ("legacy-body", "body_only", signature_style),
            ("legacy-body-digest", "body_only", "digest"),
            ("legacy-body-nonce", "body_nonce", signature_style),
            ("legacy-body-nonce-digest", "body_nonce", "digest"),
        ]
        variants: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str]] = set()
        for name, payload_mode, sig_style in combos:
            key = (payload_mode, sig_style)
            if key in seen:
                continue
            seen.add(key)
            variant = dict(base_payload)
            variant.update(
                {
                    "name": name,
                    "signature_payload": payload_mode,
                    "signature_style": sig_style,
                }
            )
            variants.append(variant)
        return variants

    def _build_rest_variant(self, rest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        endpoint = str(rest.get("endpoint") or "").strip()
        if not endpoint:
            return None
        params = dict(rest.get("params") or {})
        # Query hash는 문서 예시처럼 URL 인코딩 문자열 기준으로 계산한다.
        query_source = urlencode(params or {}, doseq=True)
        body = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
        data = body
        json_payload: Optional[Dict[str, Any]] = None
        return {
            "name": "rest",
            "url": f"{self._rest_base_url()}{endpoint}",
            "endpoint": endpoint,
            "body": body,
            "data": data,
            "json_payload": json_payload,
            "content_type": "application/json",
            "signature_style": "digest",
            "hash_source": query_source,
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
        if "hint" not in payload:
            message = str(payload.get("remote_message") or payload.get("message") or "").lower()
            for needle, hint in MESSAGE_HINTS.items():
                if needle in message:
                    payload = dict(payload)
                    payload["hint"] = hint
                    break
        if "hint" not in payload:
            http_status = payload.get("http_status")
            if http_status in (404, 405):
                payload = dict(payload)
                payload["hint"] = "REST 엔드포인트 경로나 베이스 URL을 확인하세요. Bithumb 2.x 문서와 동일한지 비교해 주세요."
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
            rest_market = self._rest_symbol()
            rest_side = "bid" if is_buy else "ask"
            rest_ord_type = "limit"
            rest_price_value: Optional[str] = None
            if self.config.bot.use_market_orders:
                if is_buy:
                    rest_ord_type = "price"
                    rest_price_value = str(int(round(price * quantity)))
                else:
                    rest_ord_type = "market"
            else:
                rest_price_value = str(int(round(price)))
            rest_params = {
                "market": rest_market,
                "side": rest_side,
                "volume": f"{quantity:.8f}",
                "price": rest_price_value,
                "ord_type": rest_ord_type,
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
        expected = f"{self.config.bot.order_currency}_{self.config.bot.payment_currency}"
        if symbol.upper() == expected.upper():
            symbol = f"{self.config.bot.payment_currency}_{self.config.bot.order_currency}"
        if self.config.bithumb.rest_symbol_dash:
            symbol = symbol.replace("_", "-")
        if self.config.bithumb.rest_symbol_upper:
            symbol = symbol.upper()
        return symbol


__all__ = ["BithumbExchange"]
