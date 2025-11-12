"""Korea Investment & Securities (KIS) overseas stock adapter."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Iterable, List

import requests

from bot.config import BotConfig

from .base import Exchange, OpenOrder, OrderResult, Quote


class KisExchange(Exchange):
    _TOKEN_TTL = 3000  # seconds

    def __init__(self, config: BotConfig) -> None:
        super().__init__(config)
        self._session = requests.Session()
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _is_live(self) -> bool:
        return self.config.kis.mode.lower() == "live"

    def _base_url(self) -> str:
        if self._is_live():
            return self.config.kis.base_url_live.rstrip("/")
        return self.config.kis.base_url_paper.rstrip("/")

    def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token
        url = f"{self._base_url()}/oauth2/token"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.config.kis.app_key,
            "appsecret": self.config.kis.app_secret,
        }
        resp = self._session.post(url, json=body, timeout=10)
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Failed to obtain KIS token: {data}")
        expires = int(data.get("expires_in", self._TOKEN_TTL))
        self._token = token
        self._token_expiry = now + max(60, expires - 60)
        return token

    def _hash_body(self, body: Dict[str, Any]) -> str:
        url = f"{self._base_url()}/uapi/hashkey"
        headers = {
            "content-type": "application/json; charset=UTF-8",
            "appKey": self.config.kis.app_key,
            "appSecret": self.config.kis.app_secret,
        }
        resp = self._session.post(url, headers=headers, data=json.dumps(body), timeout=7)
        data = resp.json()
        if "HASH" not in data:
            raise RuntimeError(f"Failed to obtain hashkey: {data}")
        return data["HASH"]

    def _request(self, method: str, endpoint: str, *, params=None, json_body=None, tr_id: str = ""):
        token = self._ensure_token()
        url = f"{self._base_url()}{endpoint}"
        headers = {
            "content-type": "application/json; charset=UTF-8",
            "authorization": f"Bearer {token}",
            "appKey": self.config.kis.app_key,
            "appSecret": self.config.kis.app_secret,
            "tr_id": tr_id,
        }
        data = None
        if json_body is not None:
            headers["hashkey"] = self._hash_body(json_body)
            data = json.dumps(json_body)
        resp = self._session.request(method, url, headers=headers, params=params, data=data, timeout=15)
        if resp.status_code >= 400:
            raise RuntimeError(f"KIS API error {resp.status_code}: {resp.text}")
        return resp.json()

    def _order_tr_id(self, side: str) -> str:
        if side.lower() == "buy":
            return "TTTS03010100" if self._is_live() else "VTTS03010100"
        return "TTTS03010200" if self._is_live() else "VTTS03010200"

    # ------------------------------------------------------------------
    # Exchange interface
    # ------------------------------------------------------------------
    def fetch_quote(self) -> Quote:
        params = {
            "AUTH": "",
            "EXCD": self.config.kis.exchange_code,
            "SYMB": self.config.kis.symbol,
        }
        data = self._request(
            "GET",
            "/uapi/overseas-price/v1/quotations/price",
            params=params,
            tr_id="HHDFS00000300",
        )
        output = data.get("output", {})
        price = float(output.get("last", output.get("ovrs_prpr", 0)) or 0)
        volume = float(output.get("acml_vol", output.get("ovrs_vol", 0)) or 0)
        return Quote(price=price, volume_24h=volume)

    def place_order(self, side: str, price: float, quantity: float) -> OrderResult:
        if self.config.bot.dry_run:
            return OrderResult(True, f"dry-{uuid.uuid4().hex[:12]}", {})
        qty_int = int(round(quantity))
        body = {
            "CANO": self.config.kis.account_no,
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": self.config.kis.exchange_code,
            "PDNO": self.config.kis.symbol,
            "ORD_DVSN": "00",
            "OVRS_ORD_UNPR": f"{price:.2f}",
            "ORD_QTY": str(qty_int),
            "ORD_UNPR": "",
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "OVRS_EXCG_CD2": "",
            "OVRS_ORD_UNPR2": "",
            "ORD_QTY2": "",
        }
        data = self._request(
            "POST",
            "/uapi/overseas-stock/v1/trading/order",
            json_body=body,
            tr_id=self._order_tr_id(side),
        )
        success = data.get("rt_cd") == "0"
        order_id = data.get("output", {}).get("ODNO", "")
        return OrderResult(success, order_id, data)

    def cancel_order(self, order_id: str, side: str) -> bool:
        if self.config.bot.dry_run:
            return True
        body = {
            "CANO": self.config.kis.account_no,
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": self.config.kis.exchange_code,
            "PDNO": self.config.kis.symbol,
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "RVSE_CNCL_DVSN_CD": "02",
            "ORG_ORD_NO": order_id,
        }
        data = self._request(
            "POST",
            "/uapi/overseas-stock/v1/trading/order-cancel",
            json_body=body,
            tr_id="TTTS03010300" if self._is_live() else "VTTS03010300",
        )
        return data.get("rt_cd") == "0"

    def list_open_orders(self) -> Iterable[OpenOrder]:
        if self.config.bot.dry_run:
            return []
        body = {
            "CANO": self.config.kis.account_no,
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": self.config.kis.exchange_code,
            "PDNO": self.config.kis.symbol,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        data = self._request(
            "POST",
            "/uapi/overseas-stock/v1/trading/inquire-nccs",
            json_body=body,
            tr_id="TTTS03010500" if self._is_live() else "VTTS03010500",
        )
        rows = data.get("output", []) or []
        orders: List[OpenOrder] = []
        for row in rows:
            orders.append(
                OpenOrder(
                    order_id=str(row.get("ODNO")),
                    side="buy" if str(row.get("SLL_CCLD_DVSN_CD", "02")) == "01" else "sell",
                )
            )
        return orders

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------
    def round_price(self, price: float) -> float:
        return round(price, 2)

    def round_quantity(self, quantity: float) -> float:
        lot = max(self.config.kis.order_lot_size, 1.0)
        steps = max(1, int(round(quantity / lot)))
        return steps * lot

    def value_to_quantity(self, order_value: float, price: float) -> float:
        if price <= 0:
            return 0.0
        shares = round(order_value / price)
        if shares <= 0 and order_value > 0:
            shares = 1
        return shares

    def is_notional_sufficient(self, notional: float, quantity: float) -> bool:
        return quantity >= self.config.kis.order_lot_size and notional > 0


__all__ = ["KisExchange"]
