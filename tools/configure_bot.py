"""Interactive helper for managing the bot's configuration files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.config import BotConfig, config_to_yaml_dict, load_yaml_config, save_yaml_config

ENV_FILE_DEFAULT = Path(__file__).resolve().parent.parent / ".env"
YAML_FILE_DEFAULT = Path(__file__).resolve().parent.parent / "config" / "bot_config.yaml"


def read_env(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def write_env(path: Path, values: Dict[str, str]) -> None:
    lines = ["# Generated configuration for the split-buy bot"]
    for key, value in values.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _update_nested(target: Dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    current = target
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def interactive_yaml(path: Path) -> None:
    current = load_yaml_config(path)
    if not current:
        current = config_to_yaml_dict(BotConfig.load())

    bool_fields = {
        "bot.hf_mode",
        "bot.dry_run",
        "home_assistant.mqtt.enabled",
        "home_assistant.reporting.auto_generate",
        "home_assistant.reporting.serve_report",
        "home_assistant.rest_api.enabled",
    }
    int_fields = {
        "home_assistant.mqtt.port",
        "home_assistant.reporting.interval_minutes",
        "home_assistant.reporting.port",
        "home_assistant.rest_api.port",
    }
    float_fields = {"kis.order_lot_size"}

    prompts = [
        ("bot.exchange", "Exchange (BITHUMB/KIS)", current["bot"].get("exchange", "BITHUMB")),
        ("bot.symbol_ticker", "Market ticker", current["bot"].get("symbol_ticker", "USDT_KRW")),
        ("bot.order_currency", "Order currency", current["bot"].get("order_currency", "USDT")),
        ("bot.payment_currency", "Payment currency", current["bot"].get("payment_currency", "KRW")),
        ("bot.hf_mode", "Enable HF mode? (y/n)", current["bot"].get("hf_mode", True)),
        ("bot.dry_run", "Enable dry-run? (y/n)", current["bot"].get("dry_run", True)),
        ("bithumb.api_key", "Bithumb API key", current.get("bithumb", {}).get("api_key", "")),
        ("bithumb.api_secret", "Bithumb API secret", current.get("bithumb", {}).get("api_secret", "")),
        (
            "bithumb.base_url",
            "Bithumb base URL",
            current.get("bithumb", {}).get("base_url", "https://api.bithumb.com"),
        ),
        (
            "bithumb.auth_mode",
            "Bithumb auth mode",
            current.get("bithumb", {}).get("auth_mode", "legacy"),
        ),
        ("kis.app_key", "KIS app key", current.get("kis", {}).get("app_key", "")),
        ("kis.app_secret", "KIS app secret", current.get("kis", {}).get("app_secret", "")),
        (
            "kis.account_no",
            "KIS account number",
            current.get("kis", {}).get("account_no", ""),
        ),
        (
            "kis.account_password",
            "KIS account password",
            current.get("kis", {}).get("account_password", ""),
        ),
        ("kis.mode", "KIS mode (paper/live)", current.get("kis", {}).get("mode", "paper")),
        (
            "kis.exchange_code",
            "KIS exchange code",
            current.get("kis", {}).get("exchange_code", "NASD"),
        ),
        ("kis.symbol", "KIS symbol", current.get("kis", {}).get("symbol", "TQQQ")),
        ("kis.currency", "KIS currency", current.get("kis", {}).get("currency", "USD")),
        (
            "kis.order_lot_size",
            "KIS lot size",
            current.get("kis", {}).get("order_lot_size", 1.0),
        ),
        (
            "home_assistant.reporting.auto_generate",
            "Auto-generate report? (y/n)",
            current["home_assistant"]["reporting"].get("auto_generate", True),
        ),
        (
            "home_assistant.reporting.interval_minutes",
            "Report interval (minutes)",
            current["home_assistant"]["reporting"].get("interval_minutes", 60),
        ),
        (
            "home_assistant.reporting.output_path",
            "Report output path",
            current["home_assistant"]["reporting"].get("output_path", "reports/latest.html"),
        ),
        (
            "home_assistant.mqtt.enabled",
            "Enable MQTT publishing? (y/n)",
            current["home_assistant"]["mqtt"].get("enabled", False),
        ),
        (
            "home_assistant.mqtt.host",
            "MQTT host",
            current["home_assistant"]["mqtt"].get("host", "127.0.0.1"),
        ),
        (
            "home_assistant.mqtt.port",
            "MQTT port",
            current["home_assistant"]["mqtt"].get("port", 1883),
        ),
        (
            "home_assistant.mqtt.base_topic",
            "MQTT base topic",
            current["home_assistant"]["mqtt"].get("base_topic", "bithumb_bot"),
        ),
    ]

    def _parse(value: str, key: str):
        if key in bool_fields:
            return value.lower() in {"y", "yes", "true", "1"}
        if key in int_fields:
            try:
                return int(value)
            except ValueError:
                return value
        if key in float_fields:
            try:
                return float(value)
            except ValueError:
                return value
        return value

    print(f"Writing configuration to {path}\n")
    for dotted, prompt, default in prompts:
        default_str = "y" if isinstance(default, bool) and default else "n" if isinstance(default, bool) else str(default)
        response = input(f"{prompt} [{default_str}]: ").strip()
        if response == "":
            value = default
        else:
            value = _parse(response, dotted)
        _update_nested(current, dotted, value)

    save_yaml_config(current, path)
    print("YAML configuration saved.")


def set_yaml_values(path: Path, pairs: Dict[str, str]) -> None:
    current = load_yaml_config(path) or config_to_yaml_dict(BotConfig.load())
    bool_fields = {
        "bot.hf_mode",
        "bot.dry_run",
        "home_assistant.mqtt.enabled",
        "home_assistant.reporting.auto_generate",
        "home_assistant.reporting.serve_report",
        "home_assistant.rest_api.enabled",
    }
    int_fields = {
        "home_assistant.mqtt.port",
        "home_assistant.reporting.interval_minutes",
        "home_assistant.reporting.port",
        "home_assistant.rest_api.port",
    }
    float_fields = {"kis.order_lot_size"}

    for key, value in pairs.items():
        if key in bool_fields:
            _update_nested(current, key, value.lower() in {"1", "true", "t", "yes", "y"})
        elif key in int_fields:
            try:
                _update_nested(current, key, int(value))
            except ValueError:
                _update_nested(current, key, value)
        elif key in float_fields:
            try:
                _update_nested(current, key, float(value))
            except ValueError:
                _update_nested(current, key, value)
        else:
            _update_nested(current, key, value)

    save_yaml_config(current, path)
    print(f"Updated YAML configuration at {path}")


FIELDS = [
    ("EXCHANGE", "Exchange (BITHUMB or KIS)"),
    ("BITHUMB_API_KEY", "Bithumb API key"),
    ("BITHUMB_API_SECRET", "Bithumb API secret"),
    ("BITHUMB_BASE_URL", "Bithumb API base URL"),
    ("BITHUMB_AUTH_MODE", "Bithumb auth mode (legacy/jwt)"),
    ("KIS_APP_KEY", "KIS app key"),
    ("KIS_APP_SECRET", "KIS app secret"),
    ("KIS_ACCOUNT_NO", "KIS account number (e.g. 12345678-01)"),
    ("KIS_ACCOUNT_PASSWORD", "KIS account password (optional)"),
    ("KIS_MODE", "KIS mode (paper/live)"),
    ("KIS_EXCHANGE_CODE", "KIS exchange code (e.g. NASD)"),
    ("KIS_SYMBOL", "KIS symbol (e.g. TQQQ)"),
    ("KIS_CURRENCY", "KIS settlement currency (e.g. USD)"),
    ("KIS_ORDER_LOT_SIZE", "KIS order lot size (default 1)"),
    ("BOT_SYMBOL_TICKER", "Market ticker (e.g. USDT_KRW)"),
    ("BOT_ORDER_CURRENCY", "Order currency (e.g. USDT)"),
    ("BOT_PAYMENT_CURRENCY", "Payment currency (e.g. KRW)"),
    ("BOT_HF_MODE", "Use HF parameters? (true/false)"),
    ("BOT_DRY_RUN", "Enable dry-run? (true/false)"),
]


def interactive_config(path: Path) -> None:
    current = read_env(path)
    print(f"Writing configuration to {path}\n")
    updated: Dict[str, str] = {}
    for key, prompt in FIELDS:
        default = current.get(key, "")
        display_default = f" [{default}]" if default else ""
        value = input(f"{prompt}{display_default}: ").strip()
        if not value:
            value = default
        updated[key] = value
    write_env(path, updated)
    print("Configuration saved.")


def set_values(path: Path, pairs: Dict[str, str]) -> None:
    current = read_env(path)
    current.update(pairs)
    write_env(path, current)
    print(f"Updated {len(pairs)} entr{'y' if len(pairs) == 1 else 'ies'} in {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure environment variables or YAML for the bot.")
    parser.add_argument("--env-file", type=Path, default=ENV_FILE_DEFAULT, help="Path to the .env file")
    parser.add_argument("--yaml", action="store_true", help="Edit the YAML configuration instead of the .env file")
    parser.add_argument("--yaml-file", type=Path, default=YAML_FILE_DEFAULT, help="Path to bot_config.yaml")
    parser.add_argument(
        "--set",
        nargs="*",
        metavar="KEY=VALUE",
        help="Set one or more KEY=VALUE pairs non-interactively",
    )
    args = parser.parse_args()

    if args.yaml:
        target = args.yaml_file
        if args.set:
            pairs = {}
            for item in args.set:
                if "=" not in item:
                    raise SystemExit(f"Invalid --set argument: {item}")
                key, value = item.split("=", 1)
                pairs[key] = value
            set_yaml_values(target, pairs)
        else:
            interactive_yaml(target)
    else:
        if args.set:
            pairs = {}
            for item in args.set:
                if "=" not in item:
                    raise SystemExit(f"Invalid --set argument: {item}")
                key, value = item.split("=", 1)
                pairs[key] = value
            set_values(args.env_file, pairs)
        else:
            interactive_config(args.env_file)


if __name__ == "__main__":
    main()
