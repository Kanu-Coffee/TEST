"""Bithumb REST exchange adapter (v1.2.0 legacy + v2.1.x JWT)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode

import requests

from bot.config import BotConfig

from .base import Exchange, OpenOrder, OrderResult, Quote


def _now_ms() -> str:
    return str(int(time.time() * 1000))


def _b64url(data: bytes) -> str:
    """Minimal base64url encoder without padding (for HS256 JWT)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _encode_jwt_hs256(payload: Dict[str, Any], secret: str) -> str:
    """
    Minimal HS256 JWT 구현 (pyjwt 미의존).
    Bithumb v2.1.x 가이드의 HS256 서명 방식과 동일한 포맷을 따른다.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    header_bytes = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    header_b64 = _b64url(header_bytes)
    payload_b64 = _b64url(payload_bytes)
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


class BithumbExchange(Exchange):
    """
    - auth_mode == 'legacy' (기본값): v1.2.0 HMAC (기존 /public, /trade, /info 엔드포인트)
    - auth_mode == 'jwt'         : v2.1.x JWT  ( /v1/ticker, /v1/orders, /v1/order 등)
    """

    def __init__(self, config: BotConfig) -> None:
        super().__init__(config)
        self._session = requests.Session()

        # None / 미설정 / 기타 값 -> 기본 legacy 로 취급
        mode = getattr(self.config.bithumb, "auth_mode", "legacy") or "legacy"
        self._auth_mode = mode.lower()
        self._use_legacy = self._auth_mode != "jwt"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _base_url(self) -> str:
        return self.config.bithumb.base_url.rstrip("/")

    # ---------- v1.2.0 HMAC 서명 --------------------------------------
    def _signed_headers_legacy(self, endpoint: str, params: Dict[str, str]) -> Dict[str, str]:
        """
        v1.2.0 Private API용 HMAC 서명 헤더.
        docs: /public/ticker/{order_currency}_{payment_currency}, /trade/place 등.
        """
        cred = self.config.bithumb
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

    # ---------- v2.1.x JWT 서명 ---------------------------------------
    def _jwt_headers(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        v2.1.x Private API용 JWT Authorization 헤더 생성.
        - access_key: API 키
        - nonce: uuid4
        - timestamp: ms
        - query_hash / query_hash_alg: 파라미터 있는 경우 SHA512(query_string)
        """
        cred = self.config.bithumb
        payload: Dict[str, Any] = {
            "access_key": cred.api_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
        }

        if params:
            # Bithumb 가이드 예시와 동일하게 query string 생성 후 SHA512 적용.
            query = urlencode(params, doseq=True).encode("utf-8")
            h = hashlib.sha512()
            h.update(query)
            payload["query_hash"] = h.hexdigest()
            payload["query_hash_alg"] = "SHA512"

        token = _encode_jwt_hs256(payload, cred.api_secret)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # ---------- 공통 유틸 ----------------------------------------------
    def _market_id(self) -> str:
        """
        v2.1.x 마켓 ID 포맷: KRW-BTC, KRW-USDT 등 (payment-order).
        기존 config.bot.symbol_ticker (e.g. USDT_KRW)는 v1.2.0용으로 그대로 유지.
        """
        return f"{self.config.bot.payment_currency}-{self.config.bot.order_currency}"

    # ------------------------------------------------------------------
    # Exchange interface
    # ------------------------------------------------------------------
    def fetch_quote(self) -> Quote:
        """
        - legacy(HMAC): GET /public/ticker/{order_currency}_{payment_currency} (v1.2.0)
        - jwt        : GET /v1/ticker?markets=KRW-BTC 형식 (응답은 배열)
        """
        if self._use_legacy:
            url = f"{self._base_url()}/public/ticker/{self.config.bot.symbol_ticker}"
            resp = self._session.get(url, timeout=5)
            data = resp.json().get("data", {}) or {}
            price = float(data.get("closing_price", 0) or 0)
            volume = float(data.get("units_traded_24H", 0) or 0)
            return Quote(price=price, volume_24h=volume)

        # v2.1.x ticker (PUBLIC, JWT 불필요)
        url = f"{self._base_url()}/v1/ticker"
        params = {"markets": self._market_id()}
        resp = self._session.get(url, params=params, timeout=5)
        payload = resp.json()

        # 응답은 [{"market": "...", "trade_price": ..., "acc_trade_volume_24h": ...}, ...] 형태
        item: Dict[str, Any] = {}
        if isinstance(payload, list) and payload:
            item = payload[0]
        elif isinstance(payload, dict):
            # 혹시 dict 형태로 오는 경우 대비
            item = payload

        price = float(item.get("trade_price", 0) or 0)
        volume = float(item.get("acc_trade_volume_24h", 0) or 0)
        return Quote(price=price, volume_24h=volume)

    def place_order(self, side: str, price: float, quantity: float) -> OrderResult:
        """
        - legacy(HMAC): POST /trade/place (기존 구현 유지, status == '0000' 체크)
        - jwt        : POST /v1/orders (market, side, volume, price, ord_type)
        """
        if self.config.bot.dry_run:
            params = {
                "side": side,
                "price": self.round_price(price),
                "quantity": self.round_quantity(quantity),
            }
            return OrderResult(True, f"dry-{uuid.uuid4().hex[:12]}", params)

        if self._use_legacy:
            endpoint = "/trade/place"
            params = {
                "order_currency": self.config.bot.order_currency,
                "payment_currency": self.config.bot.payment_currency,
                "units": f"{self.round_quantity(quantity):.8f}",
                "price": str(int(round(self.round_price(price)))),
                "type": "bid" if side.lower() == "buy" else "ask",
            }
            headers = self._signed_headers_legacy(endpoint, params)
            resp = self._session.post(
                self._base_url() + endpoint,
                headers=headers,
                data=params,
                timeout=7,
            )
            payload = resp.json()
            success = payload.get("status") == "0000"
            order_id = str(payload.get("order_id", "") or "")
            return OrderResult(success, order_id, payload)

        # v2.1.x JWT 주문
        endpoint = "/v1/orders"
        body = {
            "market": self._market_id(),
            "side": "bid" if side.lower() == "buy" else "ask",
            "volume": f"{self.round_quantity(quantity):.8f}",
            "price": str(int(round(self.round_price(price)))),
            "ord_type": "limit",  # 봇은 지정가 주문만 사용
        }
        headers = self._jwt_headers(body)
        resp = self._session.post(
            self._base_url() + endpoint,
            headers=headers,
            json=body,
            timeout=7,
        )
        payload = resp.json()
        success = resp.ok and bool(payload.get("uuid"))
        order_id = str(payload.get("uuid", "") or "")
        return OrderResult(success, order_id, payload)

    def cancel_order(self, order_id: str, side: str) -> bool:
        """
        - legacy(HMAC): POST /trade/cancel (order_id + type)
        - jwt        : DELETE /v1/order (uuid)
        """
        if self.config.bot.dry_run:
            return True

        if self._use_legacy:
            endpoint = "/trade/cancel"
            params = {
                "order_currency": self.config.bot.order_currency,
                "payment_currency": self.config.bot.payment_currency,
                "order_id": order_id,
                "type": "bid" if side.lower() == "buy" else "ask",
            }
            headers = self._signed_headers_legacy(endpoint, params)
            resp = self._session.post(
                self._base_url() + endpoint,
                headers=headers,
                data=params,
                timeout=7,
            )
            payload = resp.json()
            return payload.get("status") == "0000"

        # v2.1.x JWT: DELETE /v1/order, body: {"uuid": "..."}
        endpoint = "/v1/order"
        body = {"uuid": order_id}
        headers = self._jwt_headers(body)
        resp = self._session.delete(
            self._base_url() + endpoint,
            headers=headers,
            json=body,
            timeout=7,
        )
        # 정상 응답이면 uuid, state 등이 딸려옴. status 필드는 없다.
        if not resp.ok:
            return False
        payload = resp.json()
        return bool(payload.get("uuid"))

    def list_open_orders(self) -> Iterable[OpenOrder]:
        """
        - legacy(HMAC): POST /info/orders, status == '0000' 이고 data 배열에서 order_id / type 사용.
        - jwt        : GET  /v1/orders?market=...&state=wait (체결 대기 주문 조회).
        """
        if self.config.bot.dry_run:
            return []

        if self._use_legacy:
            endpoint = "/info/orders"
            params = {
                "order_currency": self.config.bot.order_currency,
                "payment_currency": self.config.bot.payment_currency,
            }
            headers = self._signed_headers_legacy(endpoint, params)
            resp = self._session.post(
                self._base_url() + endpoint,
                headers=headers,
                data=params,
                timeout=7,
            )
            payload = resp.json()
            if payload.get("status") != "0000":
                return []

            rows: List[OpenOrder] = []
            for row in payload.get("data") or []:
                rows.append(
                    OpenOrder(
                        order_id=str(row.get("order_id")),
                        side="buy"
                        if str(row.get("type", "bid")).lower() == "bid"
                        else "sell",
                    )
                )
            return rows

        # v2.1.x JWT: GET /v1/orders
        endpoint = "/v1/orders"
        params = {
            "market": self._market_id(),
            "state": "wait",  # 체결 대기 주문
            "page": 1,
            "limit": 100,
            "order_by": "desc",
        }
        headers = self._jwt_headers(params)
        resp = self._session.get(
            self._base_url() + endpoint,
            headers=headers,
            params=params,
            timeout=7,
        )
        payload = resp.json()
        data: List[Dict[str, Any]]
        if isinstance(payload, list):
            data = payload
        else:
            # 혹시 dict에 'data' key로 감싸져올 수도 있으니 방어 코드
            data = payload.get("data") or []

        rows: List[OpenOrder] = []
        for row in data:
            rows.append(
                OpenOrder(
                    order_id=str(row.get("uuid")),
                    side="buy" if str(row.get("side", "bid")).lower() == "bid" else "sell",
                )
            )
        return rows

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------
    def round_price(self, price: float) -> float:
        # KRW 마켓 기준: 1원 단위 절사 (필요하면 나중에 호가단위 로직 붙일 수 있음)
        return float(int(round(price)))

    def round_quantity(self, quantity: float) -> float:
        # BTC/USDT 등 소수 8자리까지 허용
        return round(quantity, 8)

    def min_notional(self) -> float:
        # 최소 주문 금액 (KRW 기준). 필요시 config로 뺄 수 있음.
        return 5000.0


__all__ = ["BithumbExchange"]
