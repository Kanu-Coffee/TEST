"""Configuration helpers for the multi-exchange trading bot.

The configuration system is intentionally explicit: every tunable value is
stored inside a dataclass so the running strategy can rely on type hints and
sensible defaults.  Configuration values are collected from three sources in
order of precedence:

1. ``os.environ`` (already populated by the environment)
2. the optional ``.env`` file in the project root
3. ``config/bot_config.yaml`` if it exists

Environment variables always win.  Missing values fall back to defaults that are
safe for dry-run simulations.  The module also exposes helper functions for
CLI tools that need to save YAML or render configuration summaries.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
CONFIG_DIR = ROOT_DIR / "config"
YAML_PATH = CONFIG_DIR / "bot_config.yaml"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        os.environ.setdefault(key, value)


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_yaml_config(path: Path = YAML_PATH) -> Dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def save_yaml_config(data: Mapping[str, Any], path: Path = YAML_PATH) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to save YAML configuration files")
    _ensure_config_dir()
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dict(data), handle, sort_keys=False, allow_unicode=True)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _as_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _select(env: Mapping[str, str], aliases: Iterable[str], default: Any) -> Any:
    for name in aliases:
        if name in env and env[name] != "":
            return env[name]
    return default


# ---------------------------------------------------------------------------
# Dataclasses describing the configuration
# ---------------------------------------------------------------------------


@dataclass
class BithumbSettings:
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://api.bithumb.com"
    rest_base_url: str = "https://api.bithumb.com"
    rest_place_endpoint: str = "/api/v2/spot/trade/place"
    rest_market_buy_endpoint: str = "/api/v2/spot/trade/market_buy"
    rest_market_sell_endpoint: str = "/api/v2/spot/trade/market_sell"
    prefer_rest: bool = False
    enable_failover: bool = True
    rest_symbol_dash: bool = True
    rest_symbol_upper: bool = True
    auth_mode: str = "legacy"  # "legacy" | "jwt"


@dataclass
class KisSettings:
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
class StrategyBand:
    """Parameters describing a single grid strategy band."""

    buy_step: float
    martingale_multiplier: float
    max_steps: int
    base_order_value: float
    tp_multiplier: float
    sl_multiplier: float
    tp_floor: float
    sl_floor: float
    vol_halflife: int
    vol_min: float
    vol_max: float
    sleep_seconds: float
    order_cooldown: float
    max_orders_per_minute: int
    cancel_base_wait: float
    cancel_min_wait: float
    cancel_max_wait: float
    cancel_volume_scale: float
    failure_pause_seconds: float
    failure_pause_backoff: float
    failure_pause_max: float
    post_fill_pause_seconds: float


@dataclass
class GridStrategySettings:
    default: StrategyBand
    high_frequency: StrategyBand


@dataclass
class BotSettings:
    exchange: str = "BITHUMB"
    symbol_ticker: str = "USDT_KRW"
    order_currency: str = "USDT"
    payment_currency: str = "KRW"
    dry_run: bool = True
    hf_mode: bool = True
    use_market_orders: bool = False
    timezone: str = "Asia/Seoul"
    report_interval_minutes: int = 60
    log_level: str = "INFO"


@dataclass
class MQTTSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 1883
    username: str = ""
    password: str = ""
    base_topic: str = "bithumb_bot"


@dataclass
class ReportingSettings:
    auto_generate: bool = False
    interval_minutes: int = 60
    serve_report: bool = True
    output_path: str = "reports/latest.html"


@dataclass
class RestAPISettings:
    enabled: bool = True
    metrics_file: str = "metrics.json"


@dataclass
class HomeAssistantSettings:
    mqtt: MQTTSettings = field(default_factory=MQTTSettings)
    reporting: ReportingSettings = field(default_factory=ReportingSettings)
    rest_api: RestAPISettings = field(default_factory=RestAPISettings)


@dataclass
class BotConfig:
    bot: BotSettings
    strategy: GridStrategySettings
    bithumb: BithumbSettings
    kis: KisSettings
    home_assistant: HomeAssistantSettings

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, *, env: Optional[MutableMapping[str, str]] = None) -> "BotConfig":
        _load_env_file()
        source_env = dict(os.environ if env is None else env)
        yaml_data = load_yaml_config()

        def yml(section: str) -> Dict[str, Any]:
            raw = yaml_data.get(section, {})
            return raw if isinstance(raw, dict) else {}

        bot_section = yml("bot")
        strat_section = yml("strategy")
        default_section = strat_section.get("default", {}) if isinstance(strat_section, dict) else {}
        hf_section = strat_section.get("high_frequency", {}) if isinstance(strat_section, dict) else {}
        ha_section = yml("home_assistant")
        mqtt_section = ha_section.get("mqtt", {}) if isinstance(ha_section, dict) else {}
        reporting_section = ha_section.get("reporting", {}) if isinstance(ha_section, dict) else {}
        rest_section = ha_section.get("rest_api", {}) if isinstance(ha_section, dict) else {}
        bithumb_section = yml("bithumb")
        kis_section = yml("kis")

        bot = BotSettings(
            exchange=str(_select(source_env, ["EXCHANGE", "BOT_EXCHANGE"], bot_section.get("exchange", "BITHUMB"))).upper(),
            symbol_ticker=str(_select(source_env, ["BOT_SYMBOL_TICKER", "SYMBOL", "SYMBOL_TICKER"], bot_section.get("symbol_ticker", "USDT_KRW"))),
            order_currency=str(_select(source_env, ["BOT_ORDER_CURRENCY", "ORDER_CURRENCY"], bot_section.get("order_currency", "USDT"))),
            payment_currency=str(_select(source_env, ["BOT_PAYMENT_CURRENCY", "PAYMENT_CURRENCY"], bot_section.get("payment_currency", "KRW"))),
            dry_run=_as_bool(_select(source_env, ["BOT_DRY_RUN", "DRY_RUN"], bot_section.get("dry_run", True)), True),
            hf_mode=_as_bool(_select(source_env, ["BOT_HF_MODE", "HF_MODE"], bot_section.get("hf_mode", True)), True),
            use_market_orders=_as_bool(_select(source_env, ["BOT_USE_MARKET_ORDERS", "USE_MARKET_ORDERS"], bot_section.get("use_market_orders", False)), False),
            timezone=str(_select(source_env, ["TIMEZONE"], bot_section.get("timezone", "Asia/Seoul"))),
            report_interval_minutes=_as_int(_select(source_env, ["REPORT_INTERVAL_MINUTES"], bot_section.get("report_interval_minutes", 60)), 60),
            log_level=str(_select(source_env, ["LOG_LEVEL"], bot_section.get("log_level", "INFO"))).upper(),
        )

        def build_band(prefix: str, section: Mapping[str, Any], defaults: Dict[str, Any]) -> StrategyBand:
            env_prefix = prefix.upper()

            # ✅ 여기부터 수정된 부분
            def pick(name: str, default_value: Any, *, aliases: Iterable[str] = ()) -> Any:
                names = [f"{env_prefix}_{name.upper()}"] + list(aliases)
                # 1) ENV 값 우선
                # 2) YAML section[name.lower()]
                # 3) 마지막으로 default_value
                return _select(
                    source_env,
                    names,
                    section.get(name.lower(), default_value),
                )

            def f(name: str, default_value: float, aliases: Iterable[str] = ()) -> float:
                return _as_float(pick(name, default_value, aliases=aliases), default_value)

            def i(name: str, default_value: int, aliases: Iterable[str] = ()) -> int:
                return _as_int(pick(name, default_value, aliases=aliases), default_value)
            # ✅ 수정 끝

            base_order_default = defaults.get("BASE_ORDER_VALUE", defaults.get("BASE_KRW", 0.0))
            base_aliases = [
                f"{env_prefix}_BASE_KRW",
                f"{env_prefix}_ORDER_VALUE",
            ]

            tp_floor_aliases = [f"{env_prefix}_TAKE_PROFIT", f"{env_prefix}_TP_FLOOR"]
            sl_floor_aliases = [f"{env_prefix}_STOP_LOSS", f"{env_prefix}_SL_FLOOR"]
            mult_aliases = [f"{env_prefix}_STEP_MULTIPLIER"]

            return StrategyBand(
                buy_step=f("buy_step", defaults["BUY_STEP"]),
                martingale_multiplier=f("martingale_mul", defaults["MARTINGALE_MUL"], aliases=mult_aliases),
                max_steps=i("max_steps", defaults["MAX_STEPS"]),
                base_order_value=f("base_order_value", base_order_default, aliases=base_aliases),
                tp_multiplier=f("tp_k", defaults["TP_K"], aliases=[f"{env_prefix}_TP_MULTIPLIER"]),
                sl_multiplier=f("sl_k", defaults["SL_K"], aliases=[f"{env_prefix}_SL_MULTIPLIER"]),
                tp_floor=f("tp_floor", defaults["TP_FLOOR"], aliases=tp_floor_aliases),
                sl_floor=f("sl_floor", defaults["SL_FLOOR"], aliases=sl_floor_aliases),
                vol_halflife=i("vol_halflife", defaults["VOL_HALFLIFE"]),
                vol_min=f("vol_min", defaults["VOL_MIN"]),
                vol_max=f("vol_max", defaults["VOL_MAX"]),
                sleep_seconds=f("sleep_sec", defaults["SLEEP_SEC"], aliases=[f"{env_prefix}_SLEEP_SECONDS"]),
                order_cooldown=f("order_cooldown", defaults["ORDER_COOLDOWN"]),
                max_orders_per_minute=i("max_orders_min", defaults["MAX_ORDERS_MIN"], aliases=[f"{env_prefix}_MAX_ORDERS_PER_MINUTE"]),
                cancel_base_wait=f("cancel_base_wait", defaults["CANCEL_BASE_WAIT"]),
                cancel_min_wait=f("cancel_min_wait", defaults["CANCEL_MIN_WAIT"]),
                cancel_max_wait=f("cancel_max_wait", defaults["CANCEL_MAX_WAIT"]),
                cancel_volume_scale=f("cancel_vol_scale", defaults["CANCEL_VOL_SCALE"]),
                failure_pause_seconds=f("failure_pause_seconds", defaults["FAILURE_PAUSE_SECONDS"]),
                failure_pause_backoff=f("failure_pause_backoff", defaults["FAILURE_PAUSE_BACKOFF"]),
                failure_pause_max=f("failure_pause_max", defaults["FAILURE_PAUSE_MAX"]),
                post_fill_pause_seconds=f("post_fill_pause_seconds", defaults["POST_FILL_PAUSE_SECONDS"]),
            )

        default_defaults = {
            "BUY_STEP": 0.008,
            "MARTINGALE_MUL": 1.5,
            "MAX_STEPS": 10,
            "BASE_ORDER_VALUE": 5000.0,
            "VOL_HALFLIFE": 60,
            "VOL_MIN": 0.001,
            "VOL_MAX": 0.015,
            "TP_K": 0.55,
            "SL_K": 1.25,
            "TP_FLOOR": 0.003,
            "SL_FLOOR": 0.007,
            "SLEEP_SEC": 2.0,
            "ORDER_COOLDOWN": 6.0,
            "MAX_ORDERS_MIN": 6,
            "CANCEL_BASE_WAIT": 10.0,
            "CANCEL_MIN_WAIT": 5.0,
            "CANCEL_MAX_WAIT": 30.0,
            "CANCEL_VOL_SCALE": 2000.0,
            "FAILURE_PAUSE_SECONDS": 10.0,
            "FAILURE_PAUSE_BACKOFF": 2.0,
            "FAILURE_PAUSE_MAX": 180.0,
            "POST_FILL_PAUSE_SECONDS": 3.0,
        }
        hf_defaults = {
            "BUY_STEP": 0.005,
            "MARTINGALE_MUL": 1.3,
            "MAX_STEPS": 10,
            "BASE_ORDER_VALUE": 5000.0,
            "VOL_HALFLIFE": 30,
            "VOL_MIN": 0.0045,
            "VOL_MAX": 0.015,
            "TP_K": 0.8,
            "SL_K": 1.0,
            "TP_FLOOR": 0.0015,
            "SL_FLOOR": 0.0025,
            "SLEEP_SEC": 1.5,
            "ORDER_COOLDOWN": 4.0,
            "MAX_ORDERS_MIN": 8,
            "CANCEL_BASE_WAIT": 10.0,
            "CANCEL_MIN_WAIT": 5.0,
            "CANCEL_MAX_WAIT": 30.0,
            "CANCEL_VOL_SCALE": 2000.0,
            "FAILURE_PAUSE_SECONDS": 8.0,
            "FAILURE_PAUSE_BACKOFF": 2.0,
            "FAILURE_PAUSE_MAX": 120.0,
            "POST_FILL_PAUSE_SECONDS": 2.0,
        }

        strategy = GridStrategySettings(
            default=build_band("DEFAULT", default_section, default_defaults),
            high_frequency=build_band("HF", hf_section, hf_defaults),
        )

        bithumb = BithumbSettings(
            api_key=str(_select(source_env, ["BITHUMB_API_KEY"], bithumb_section.get("api_key", ""))),
            api_secret=str(_select(source_env, ["BITHUMB_API_SECRET"], bithumb_section.get("api_secret", ""))),
            base_url=str(_select(source_env, ["BITHUMB_BASE_URL", "BITHUMB_LEGACY_BASE_URL"], bithumb_section.get("base_url", "https://api.bithumb.com"))),
            rest_base_url=str(_select(source_env, ["BITHUMB_REST_BASE_URL"], bithumb_section.get("rest_base_url", bithumb_section.get("base_url", "https://api.bithumb.com")))),
            rest_place_endpoint=str(_select(source_env, ["BITHUMB_REST_PLACE_ENDPOINT"], bithumb_section.get("rest_place_endpoint", "/api/v2/spot/trade/place"))),
            rest_market_buy_endpoint=str(_select(source_env, ["BITHUMB_REST_MARKET_BUY"], bithumb_section.get("rest_market_buy_endpoint", "/api/v2/spot/trade/market_buy"))),
            rest_market_sell_endpoint=str(_select(source_env, ["BITHUMB_REST_MARKET_SELL"], bithumb_section.get("rest_market_sell_endpoint", "/api/v2/spot/trade/market_sell"))),
            prefer_rest=_as_bool(_select(source_env, ["BITHUMB_PREFER_REST"], bithumb_section.get("prefer_rest", False)), False),
            enable_failover=_as_bool(_select(source_env, ["BITHUMB_FAILOVER"], bithumb_section.get("enable_failover", True)), True),
            rest_symbol_dash=_as_bool(_select(source_env, ["BITHUMB_REST_SYMBOL_DASH"], bithumb_section.get("rest_symbol_dash", True)), True),
            rest_symbol_upper=_as_bool(_select(source_env, ["BITHUMB_REST_SYMBOL_UPPER"], bithumb_section.get("rest_symbol_upper", True)), True),
            auth_mode=str(_select(source_env, ["BITHUMB_AUTH_MODE"], bithumb_section.get("auth_mode", "legacy"))).lower(),
        )

        kis = KisSettings(
            app_key=str(_select(source_env, ["KIS_APP_KEY"], kis_section.get("app_key", ""))),
            app_secret=str(_select(source_env, ["KIS_APP_SECRET"], kis_section.get("app_secret", ""))),
            account_no=str(_select(source_env, ["KIS_ACCOUNT_NO"], kis_section.get("account_no", ""))),
            account_password=str(_select(source_env, ["KIS_ACCOUNT_PASSWORD"], kis_section.get("account_password", ""))),
            mode=str(_select(source_env, ["KIS_MODE"], kis_section.get("mode", "paper"))).lower(),
            exchange_code=str(_select(source_env, ["KIS_EXCHANGE_CODE"], kis_section.get("exchange_code", "NASD"))),
            symbol=str(_select(source_env, ["KIS_SYMBOL"], kis_section.get("symbol", "TQQQ"))),
            currency=str(_select(source_env, ["KIS_CURRENCY"], kis_section.get("currency", "USD"))),
            order_lot_size=_as_float(_select(source_env, ["KIS_ORDER_LOT_SIZE"], kis_section.get("order_lot_size", 1.0)), 1.0),
            base_url_paper=str(_select(source_env, ["KIS_BASE_URL_PAPER"], kis_section.get("base_url_paper", "https://openapivts.koreainvestment.com:29443"))),
            base_url_live=str(_select(source_env, ["KIS_BASE_URL_LIVE"], kis_section.get("base_url_live", "https://openapi.koreainvestment.com:9443"))),
        )

        home_assistant = HomeAssistantSettings(
            mqtt=MQTTSettings(
                enabled=_as_bool(_select(source_env, ["MQTT_ENABLED"], mqtt_section.get("enabled", False)), False),
                host=str(_select(source_env, ["MQTT_HOST"], mqtt_section.get("host", "127.0.0.1"))),
                port=_as_int(_select(source_env, ["MQTT_PORT"], mqtt_section.get("port", 1883)), 1883),
                username=str(_select(source_env, ["MQTT_USERNAME"], mqtt_section.get("username", ""))),
                password=str(_select(source_env, ["MQTT_PASSWORD"], mqtt_section.get("password", ""))),
                base_topic=str(_select(source_env, ["MQTT_BASE_TOPIC"], mqtt_section.get("base_topic", "bithumb_bot"))),
            ),
            reporting=ReportingSettings(
                auto_generate=_as_bool(_select(source_env, ["REPORT_AUTO_GENERATE"], reporting_section.get("auto_generate", False)), False),
                interval_minutes=_as_int(_select(source_env, ["REPORT_INTERVAL_MINUTES"], reporting_section.get("interval_minutes", bot.report_interval_minutes)), bot.report_interval_minutes),
                serve_report=_as_bool(_select(source_env, ["REPORT_SERVE"], reporting_section.get("serve_report", True)), True),
                output_path=str(_select(source_env, ["REPORT_OUTPUT_PATH"], reporting_section.get("output_path", "reports/latest.html"))),
            ),
            rest_api=RestAPISettings(
                enabled=_as_bool(_select(source_env, ["REST_API_ENABLED"], rest_section.get("enabled", True)), True),
                metrics_file=str(_select(source_env, ["METRICS_FILE"], rest_section.get("metrics_file", "metrics.json"))),
            ),
        )

        return cls(bot=bot, strategy=strategy, bithumb=bithumb, kis=kis, home_assistant=home_assistant)

    # ------------------------------------------------------------------
    # Convenience helpers for tools
    # ------------------------------------------------------------------
    def active_band(self) -> StrategyBand:
        return self.strategy.high_frequency if self.bot.hf_mode else self.strategy.default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bot": asdict(self.bot),
            "strategy": {
                "default": asdict(self.strategy.default),
                "high_frequency": asdict(self.strategy.high_frequency),
            },
            "bithumb": asdict(self.bithumb),
            "kis": asdict(self.kis),
            "home_assistant": {
                "mqtt": asdict(self.home_assistant.mqtt),
                "reporting": asdict(self.home_assistant.reporting),
                "rest_api": asdict(self.home_assistant.rest_api),
            },
        }

    def to_env_pairs(self) -> List[Tuple[str, str]]:
        band_default = self.strategy.default
        band_hf = self.strategy.high_frequency

        pairs = [
            ("EXCHANGE", self.bot.exchange),
            ("BOT_SYMBOL_TICKER", self.bot.symbol_ticker),
            ("BOT_ORDER_CURRENCY", self.bot.order_currency),
            ("BOT_PAYMENT_CURRENCY", self.bot.payment_currency),
            ("BOT_DRY_RUN", str(self.bot.dry_run).lower()),
            ("BOT_HF_MODE", str(self.bot.hf_mode).lower()),
            ("BOT_USE_MARKET_ORDERS", str(self.bot.use_market_orders).lower()),
            ("TIMEZONE", self.bot.timezone),
            ("REPORT_INTERVAL_MINUTES", str(self.bot.report_interval_minutes)),
            ("LOG_LEVEL", self.bot.log_level),
            ("BITHUMB_API_KEY", self.bithumb.api_key),
            ("BITHUMB_API_SECRET", self.bithumb.api_secret),
            ("BITHUMB_BASE_URL", self.bithumb.base_url),
            ("BITHUMB_AUTH_MODE", self.bithumb.auth_mode),
            ("KIS_APP_KEY", self.kis.app_key),
            ("KIS_APP_SECRET", self.kis.app_secret),
            ("KIS_ACCOUNT_NO", self.kis.account_no),
            ("KIS_ACCOUNT_PASSWORD", self.kis.account_password),
            ("KIS_MODE", self.kis.mode),
            ("KIS_EXCHANGE_CODE", self.kis.exchange_code),
            ("KIS_SYMBOL", self.kis.symbol),
            ("KIS_CURRENCY", self.kis.currency),
            ("KIS_ORDER_LOT_SIZE", str(self.kis.order_lot_size)),
        ]

        def band_pairs(prefix: str, band: StrategyBand) -> List[Tuple[str, str]]:
            def fmt(value: Any) -> str:
                if isinstance(value, bool):
                    return str(value).lower()
                return str(value)

            entries = []
            mapping = asdict(band)
            for key, value in mapping.items():
                entries.append((f"{prefix}_{key.upper()}", fmt(value)))
            return entries

        pairs.extend(band_pairs("DEFAULT", band_default))
        pairs.extend(band_pairs("HF", band_hf))

        ha = self.home_assistant
        pairs.extend(
            [
                ("MQTT_ENABLED", str(ha.mqtt.enabled).lower()),
                ("MQTT_HOST", ha.mqtt.host),
                ("MQTT_PORT", str(ha.mqtt.port)),
                ("MQTT_USERNAME", ha.mqtt.username),
                ("MQTT_PASSWORD", ha.mqtt.password),
                ("MQTT_BASE_TOPIC", ha.mqtt.base_topic),
                ("REPORT_AUTO_GENERATE", str(ha.reporting.auto_generate).lower()),
                ("REPORT_SERVE", str(ha.reporting.serve_report).lower()),
                ("REPORT_OUTPUT_PATH", ha.reporting.output_path),
                ("REST_API_ENABLED", str(ha.rest_api.enabled).lower()),
                ("METRICS_FILE", ha.rest_api.metrics_file),
            ]
        )
        return pairs

    def write_env_file(self, path: Path = ENV_PATH) -> None:
        lines = [f"{key}={value}" for key, value in self.to_env_pairs()]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


__all__ = [
    "BotConfig",
    "BotSettings",
    "GridStrategySettings",
    "StrategyBand",
    "BithumbSettings",
    "KisSettings",
    "HomeAssistantSettings",
    "MQTTSettings",
    "ReportingSettings",
    "RestAPISettings",
    "load_yaml_config",
    "save_yaml_config",
]
