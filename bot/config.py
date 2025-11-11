"""Configuration utilities for the Bithumb split-buy bot."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file(path: Path = ENV_FILE) -> None:
    """Populate ``os.environ`` with values from a simple ``.env`` file.

    Lines starting with ``#`` are treated as comments. Values keep their original
    whitespace except for the trailing newline.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        os.environ.setdefault(key, value)


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "t", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class AuthConfig:
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://api.bithumb.com"
    auth_mode: str = "legacy"  # "legacy" | "jwt"


@dataclass
class StrategyParams:
    buy_step: float
    martingale_mul: float
    max_steps: int
    base_krw: int

    vol_halflife: int
    vol_min: float
    vol_max: float
    tp_k: float
    sl_k: float
    tp_floor: float
    sl_floor: float

    sleep_sec: float
    order_cooldown: int
    max_orders_min: int

    cancel_base_wait: float
    cancel_min_wait: float
    cancel_max_wait: float
    cancel_vol_scale: float

    @classmethod
    def from_prefix(cls, prefix: str, defaults: Dict[str, Any]) -> "StrategyParams":
        def _field(name: str, default):
            env_name = f"{prefix}_{name.upper()}"
            if isinstance(default, int):
                return _get_int(env_name, default)
            if isinstance(default, float):
                return _get_float(env_name, default)
            return os.environ.get(env_name, default)

        return cls(
            buy_step=_field("buy_step", defaults["BUY_STEP"]),
            martingale_mul=_field("martingale_mul", defaults["MARTINGALE_MUL"]),
            max_steps=_field("max_steps", defaults["MAX_STEPS"]),
            base_krw=_field("base_krw", defaults["BASE_KRW"]),
            vol_halflife=_field("vol_halflife", defaults["VOL_HALFLIFE"]),
            vol_min=_field("vol_min", defaults["VOL_MIN"]),
            vol_max=_field("vol_max", defaults["VOL_MAX"]),
            tp_k=_field("tp_k", defaults["TP_K"]),
            sl_k=_field("sl_k", defaults["SL_K"]),
            tp_floor=_field("tp_floor", defaults["TP_FLOOR"]),
            sl_floor=_field("sl_floor", defaults["SL_FLOOR"]),
            sleep_sec=_field("sleep_sec", defaults["SLEEP_SEC"]),
            order_cooldown=_field("order_cooldown", defaults["ORDER_COOLDOWN"]),
            max_orders_min=_field("max_orders_min", defaults["MAX_ORDERS_MIN"]),
            cancel_base_wait=_field("cancel_base_wait", defaults["CANCEL_BASE_WAIT"]),
            cancel_min_wait=_field("cancel_min_wait", defaults["CANCEL_MIN_WAIT"]),
            cancel_max_wait=_field("cancel_max_wait", defaults["CANCEL_MAX_WAIT"]),
            cancel_vol_scale=_field("cancel_vol_scale", defaults["CANCEL_VOL_SCALE"]),
        )


@dataclass
class BotConfig:
    symbol_ticker: str
    order_currency: str
    payment_currency: str
    hf_mode: bool
    dry_run: bool
    auth: AuthConfig = field(default_factory=AuthConfig)
    default_params: StrategyParams = field(default_factory=StrategyParams)
    hf_params: StrategyParams = field(default_factory=StrategyParams)

    @classmethod
    def load(cls) -> "BotConfig":
        _load_env_file()
        hf_mode = _get_bool("BOT_HF_MODE", True)
        dry_run = _get_bool("BOT_DRY_RUN", True)
        symbol_ticker = os.environ.get("BOT_SYMBOL_TICKER", "USDT_KRW")
        order_cc = os.environ.get("BOT_ORDER_CURRENCY", "USDT")
        pay_cc = os.environ.get("BOT_PAYMENT_CURRENCY", "KRW")

        auth = AuthConfig(
            api_key=os.environ.get("BITHUMB_API_KEY", ""),
            api_secret=os.environ.get("BITHUMB_API_SECRET", ""),
            base_url=os.environ.get("BITHUMB_BASE_URL", "https://api.bithumb.com"),
            auth_mode=os.environ.get("BITHUMB_AUTH_MODE", "legacy"),
        )

        default_params = StrategyParams.from_prefix(
            "DEFAULT", {
                "BUY_STEP": 0.008,
                "MARTINGALE_MUL": 1.5,
                "MAX_STEPS": 10,
                "BASE_KRW": 5000,
                "VOL_HALFLIFE": 60,
                "VOL_MIN": 0.0010,
                "VOL_MAX": 0.0150,
                "TP_K": 0.55,
                "SL_K": 1.25,
                "TP_FLOOR": 0.0030,
                "SL_FLOOR": 0.0070,
                "SLEEP_SEC": 2.0,
                "ORDER_COOLDOWN": 6,
                "MAX_ORDERS_MIN": 6,
                "CANCEL_BASE_WAIT": 10.0,
                "CANCEL_MIN_WAIT": 5.0,
                "CANCEL_MAX_WAIT": 30.0,
                "CANCEL_VOL_SCALE": 2000.0,
            }
        )

        hf_params = StrategyParams.from_prefix(
            "HF", {
                "BUY_STEP": 0.005,
                "MARTINGALE_MUL": 1.3,
                "MAX_STEPS": 10,
                "BASE_KRW": 5000,
                "VOL_HALFLIFE": 30,
                "VOL_MIN": 0.0045,
                "VOL_MAX": 0.0150,
                "TP_K": 0.8,
                "SL_K": 1.0,
                "TP_FLOOR": 0.0015,
                "SL_FLOOR": 0.0025,
                "SLEEP_SEC": 1.5,
                "ORDER_COOLDOWN": 4,
                "MAX_ORDERS_MIN": 8,
                "CANCEL_BASE_WAIT": 10.0,
                "CANCEL_MIN_WAIT": 5.0,
                "CANCEL_MAX_WAIT": 30.0,
                "CANCEL_VOL_SCALE": 2000.0,
            }
        )

        return cls(
            symbol_ticker=symbol_ticker,
            order_currency=order_cc,
            payment_currency=pay_cc,
            hf_mode=hf_mode,
            dry_run=dry_run,
            auth=auth,
            default_params=default_params,
            hf_params=hf_params,
        )


__all__ = ["BotConfig", "AuthConfig", "StrategyParams"]
