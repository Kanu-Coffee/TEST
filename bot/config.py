"""Configuration utilities for the multi-exchange split-buy bot."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Dict

try:  # pragma: no cover - optional dependency guard
    import yaml
except ImportError:  # pragma: no cover - fallback when PyYAML missing
    yaml = None  # type: ignore


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
YAML_FILE = CONFIG_DIR / "bot_config.yaml"


def _load_env_file(path: Path = ENV_FILE) -> None:
    """Populate ``os.environ`` with values from a simple ``.env`` file."""

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


def _load_yaml_dict(path: Path = YAML_FILE) -> Dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def load_yaml_config(path: Path | None = None) -> Dict[str, Any]:
    """Return the raw YAML configuration if present."""

    return _load_yaml_dict(path or YAML_FILE)


def save_yaml_config(data: Dict[str, Any], path: Path = YAML_FILE) -> None:
    """Persist the YAML configuration, creating the config directory if needed."""

    if yaml is None:
        raise RuntimeError("PyYAML is required to save YAML configuration files")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


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
class BithumbConfig:
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://api.bithumb.com"
    auth_mode: str = "legacy"  # "legacy" | "jwt"


@dataclass
class KisConfig:
    app_key: str = ""
    app_secret: str = ""
    account_no: str = ""
    account_password: str = ""
    mode: str = "paper"  # "paper" | "live"
    exchange_code: str = "NASD"
    symbol: str = "TQQQ"
    currency: str = "USD"
    order_lot_size: float = 1.0
    base_url_paper: str = "https://openapivts.koreainvestment.com:29443"
    base_url_live: str = "https://openapi.koreainvestment.com:9443"


@dataclass
class StrategyParams:
    buy_step: float
    martingale_mul: float
    max_steps: int
    base_order_value: float

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

        def _base_value(default_value: float) -> float:
            primary = os.environ.get(f"{prefix}_BASE_ORDER_VALUE")
            legacy = os.environ.get(f"{prefix}_BASE_KRW") if primary is None else None
            raw = primary if primary is not None else legacy
            if raw is None:
                return default_value
            try:
                return float(raw)
            except ValueError:
                return default_value

        base_default = defaults.get("BASE_ORDER_VALUE", defaults.get("BASE_KRW", 0))

        return cls(
            buy_step=_field("buy_step", defaults["BUY_STEP"]),
            martingale_mul=_field("martingale_mul", defaults["MARTINGALE_MUL"]),
            max_steps=_field("max_steps", defaults["MAX_STEPS"]),
            base_order_value=_base_value(base_default),
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
class MQTTConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 1883
    username: str = ""
    password: str = ""
    base_topic: str = "bithumb_bot"


@dataclass
class ReportingConfig:
    auto_generate: bool = False
    interval_minutes: int = 60
    serve_report: bool = False
    host: str = "0.0.0.0"
    port: int = 6443
    ingress_path: str = "/"
    output_path: str = "reports/latest.html"


@dataclass
class RestAPIConfig:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 6443


@dataclass
class HomeAssistantConfig:
    metrics_file: str = "ha_metrics.json"
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    rest_api: RestAPIConfig = field(default_factory=RestAPIConfig)


@dataclass
class BotConfig:
    exchange: str
    symbol_ticker: str
    order_currency: str
    payment_currency: str
    hf_mode: bool
    dry_run: bool
    bithumb: BithumbConfig = field(default_factory=BithumbConfig)
    kis: KisConfig = field(default_factory=KisConfig)
    default_params: StrategyParams = field(default_factory=StrategyParams)
    hf_params: StrategyParams = field(default_factory=StrategyParams)
    home_assistant: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)

    @classmethod
    def load(cls) -> "BotConfig":
        _load_env_file()
        exchange = os.environ.get("EXCHANGE", "BITHUMB").upper() or "BITHUMB"
        hf_mode = _get_bool("BOT_HF_MODE", True)
        dry_run = _get_bool("BOT_DRY_RUN", True)
        symbol_ticker = os.environ.get("BOT_SYMBOL_TICKER", "USDT_KRW")
        order_cc = os.environ.get("BOT_ORDER_CURRENCY", "USDT")
        pay_cc = os.environ.get("BOT_PAYMENT_CURRENCY", "KRW")

        bithumb = BithumbConfig(
            api_key=os.environ.get("BITHUMB_API_KEY", ""),
            api_secret=os.environ.get("BITHUMB_API_SECRET", ""),
            base_url=os.environ.get("BITHUMB_BASE_URL", "https://api.bithumb.com"),
            auth_mode=os.environ.get("BITHUMB_AUTH_MODE", "legacy"),
        )

        kis = KisConfig(
            app_key=os.environ.get("KIS_APP_KEY", ""),
            app_secret=os.environ.get("KIS_APP_SECRET", ""),
            account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
            account_password=os.environ.get("KIS_ACCOUNT_PASSWORD", ""),
            mode=os.environ.get("KIS_MODE", "paper"),
            exchange_code=os.environ.get("KIS_EXCHANGE_CODE", "NASD"),
            symbol=os.environ.get("KIS_SYMBOL", "TQQQ"),
            currency=os.environ.get("KIS_CURRENCY", "USD"),
            order_lot_size=_get_float("KIS_ORDER_LOT_SIZE", 1.0),
            base_url_paper=os.environ.get(
                "KIS_BASE_URL_PAPER", "https://openapivts.koreainvestment.com:29443"
            ),
            base_url_live=os.environ.get(
                "KIS_BASE_URL_LIVE", "https://openapi.koreainvestment.com:9443"
            ),
        )

        default_params = StrategyParams.from_prefix(
            "DEFAULT", {
                "BUY_STEP": 0.008,
                "MARTINGALE_MUL": 1.5,
                "MAX_STEPS": 10,
                "BASE_KRW": 5000,
                "BASE_ORDER_VALUE": 5000,
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
                "BASE_ORDER_VALUE": 5000,
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

        yaml_cfg = _load_yaml_dict()

        bot_section = yaml_cfg.get("bot", {}) if isinstance(yaml_cfg, dict) else {}
        if isinstance(bot_section, dict):
            exchange = (bot_section.get("exchange", exchange) or exchange).upper()
            symbol_ticker = bot_section.get("symbol_ticker", symbol_ticker) or symbol_ticker
            order_cc = bot_section.get("order_currency", order_cc) or order_cc
            pay_cc = bot_section.get("payment_currency", pay_cc) or pay_cc
            hf_mode = bool(bot_section.get("hf_mode", hf_mode))
            dry_run = bool(bot_section.get("dry_run", dry_run))

        bithumb_section = yaml_cfg.get("bithumb", {}) if isinstance(yaml_cfg, dict) else {}
        if isinstance(bithumb_section, dict):
            bithumb = _replace_dataclass(bithumb, bithumb_section)

        kis_section = yaml_cfg.get("kis", {}) if isinstance(yaml_cfg, dict) else {}
        if isinstance(kis_section, dict):
            kis = _replace_dataclass(kis, kis_section)

        strategy_section = yaml_cfg.get("strategy", {}) if isinstance(yaml_cfg, dict) else {}
        if isinstance(strategy_section, dict):
            default_overrides = strategy_section.get("default", {})
            hf_overrides = strategy_section.get("hf", {})
            default_params = _replace_dataclass(default_params, default_overrides)
            hf_params = _replace_dataclass(hf_params, hf_overrides)

        home_assistant_section = yaml_cfg.get("home_assistant", {}) if isinstance(yaml_cfg, dict) else {}
        home_assistant = _replace_dataclass(
            HomeAssistantConfig(),
            home_assistant_section if isinstance(home_assistant_section, dict) else {},
        )

        return cls(
            exchange=exchange,
            symbol_ticker=symbol_ticker,
            order_currency=order_cc,
            payment_currency=pay_cc,
            hf_mode=hf_mode,
            dry_run=dry_run,
            bithumb=bithumb,
            kis=kis,
            default_params=default_params,
            hf_params=hf_params,
            home_assistant=home_assistant,
        )


def _replace_dataclass(obj, overrides: Dict[str, Any] | None):
    if overrides is None:
        return obj
    updates: Dict[str, Any] = {}
    for field_info in fields(obj):
        name = field_info.name
        if name not in overrides:
            continue
        value = overrides[name]
        current = getattr(obj, name)
        if value is None:
            continue
        if is_dataclass(current) and isinstance(value, dict):
            updates[name] = _replace_dataclass(current, value)
        else:
            updates[name] = value
    if not updates:
        return obj
    return replace(obj, **updates)


def config_to_yaml_dict(config: BotConfig) -> Dict[str, Any]:
    """Convert the runtime configuration into a structure suitable for YAML."""

    return {
        "bot": {
            "exchange": config.exchange,
            "symbol_ticker": config.symbol_ticker,
            "order_currency": config.order_currency,
            "payment_currency": config.payment_currency,
            "hf_mode": config.hf_mode,
            "dry_run": config.dry_run,
        },
        "bithumb": asdict(config.bithumb),
        "kis": asdict(config.kis),
        "strategy": {
            "default": asdict(config.default_params),
            "hf": asdict(config.hf_params),
        },
        "home_assistant": asdict(config.home_assistant),
    }


__all__ = ["BotConfig", "BithumbConfig", "KisConfig", "StrategyParams"]
