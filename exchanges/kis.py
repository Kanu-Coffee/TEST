"""Korea Investment & Securities (KIS) exchange adapter."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Iterable, List

import requests

from bot.config import BotConfig

from .base import Exchange, OpenOrder, OrderResult, Quote


class KisExchange(Exchange):
    """Implementation of the KIS overseas stock API."""

    _TOKEN_TTL = 3000  # seconds, refreshed proactively

    def __init__(self, config: BotConfig):
        super().__init__(config)
        self._cfg = config.kis
        self._session = requests.Session()
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _base_url(self) -> str:
        return (
            self._cfg.base_url_live.rstrip("/")
            if self._cfg.mode.lower() == "live"
            else self._cfg.base_url_paper.rstrip("/")
        )

    def _is_live(self) -> bool:
        return self._cfg.mode.lower() == "live"

    def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token
        url = f"{self._base_url()}/oauth2/token"
        body = {
            "grant_type": "client_credentials",
            "appkey": self._cfg.app_key,
            "appsecret": self._cfg.app_secret,
        }
        resp = self._session.post(url, json=body, timeout=10)
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Failed to obtain KIS token: {data}")
        self._token = token
        expires_in = int(data.get("expires_in", self._TOKEN_TTL))
        self._token_expiry = now + max(60, expires_in - 60)
        return token

    def _hash_body(self, body: Dict[str, Any]) -> str:
        url = f"{self._base_url()}/uapi/hashkey"
        headers = {
            "content-type": "application/json; charset=UTF-8",
            "appKey": self._cfg.app_key,
            "appSecret": self._cfg.app_secret,
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
            "appKey": self._cfg.app_key,
            "appSecret": self._cfg.app_secret,
            "tr_id": tr_id,
        }
        if json_body is not None:
            headers["hashkey"] = self._hash_body(json_body)
            data = json.dumps(json_body)
        else:
            data = None
        resp = self._session.request(method, url, headers=headers, params=params, data=data, timeout=15)
        if resp.status_code >= 400:
            raise RuntimeError(f"KIS API error {resp.status_code}: {resp.text}")
        return resp.json()

    def _order_tr_id(self, side: str) -> str:
        live = self._is_live()
        if side.lower() == "buy":
            return "TTTS03010100" if live else "VTTS03010100"
        return "TTTS03010200" if live else "VTTS03010200"

    # ------------------------------------------------------------------
    # Exchange interface
    # ------------------------------------------------------------------
    def fetch_quote(self) -> Quote:
        params = {
            "AUTH": "",
            "EXCD": self._cfg.exchange_code,
            "SYMB": self._cfg.symbol,
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
        if self.config.dry_run:
            return OrderResult(True, f"dry-{uuid.uuid4().hex[:12]}", {})
        qty_int = int(round(quantity))
        body = {
            "CANO": self._cfg.account_no,
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": self._cfg.exchange_code,
            "PDNO": self._cfg.symbol,
            "ORD_DVSN": "00",  # limit order
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
        if self.config.dry_run:
            return True
        body = {
            "CANO": self._cfg.account_no,
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": self._cfg.exchange_code,
            "PDNO": self._cfg.symbol,
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
        if self.config.dry_run:
            return []
        body = {
            "CANO": self._cfg.account_no,
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": self._cfg.exchange_code,
            "PDNO": self._cfg.symbol,
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
        lot = max(self._cfg.order_lot_size, 1.0)
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
        return quantity >= self._cfg.order_lot_size and notional > 0
