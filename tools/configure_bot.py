"""Interactive helper for managing the bot's configuration files."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

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
    lines = ["# Generated configuration for the Bithumb bot"]
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

    prompts = [
        ("bot.symbol_ticker", "Market ticker", current["bot"].get("symbol_ticker", "USDT_KRW")),
        ("bot.order_currency", "Order currency", current["bot"].get("order_currency", "USDT")),
        ("bot.payment_currency", "Payment currency", current["bot"].get("payment_currency", "KRW")),
        ("bot.hf_mode", "Enable HF mode? (y/n)", current["bot"].get("hf_mode", True)),
        ("bot.dry_run", "Enable dry-run? (y/n)", current["bot"].get("dry_run", True)),
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

    for key, value in pairs.items():
        if key in bool_fields:
            _update_nested(current, key, value.lower() in {"1", "true", "t", "yes", "y"})
        elif key in int_fields:
            try:
                _update_nested(current, key, int(value))
            except ValueError:
                _update_nested(current, key, value)
        else:
            _update_nested(current, key, value)

    save_yaml_config(current, path)
    print(f"Updated YAML configuration at {path}")


FIELDS = [
    ("BITHUMB_API_KEY", "Bithumb API key"),
    ("BITHUMB_API_SECRET", "Bithumb API secret"),
    ("BITHUMB_BASE_URL", "API base URL (default: https://api.bithumb.com)"),
    ("BITHUMB_AUTH_MODE", "Auth mode (legacy/jwt)"),
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
