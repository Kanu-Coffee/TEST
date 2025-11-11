"""Interactive helper for managing the bot's environment variables."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

ENV_FILE_DEFAULT = Path(__file__).resolve().parent.parent / ".env"


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
    parser = argparse.ArgumentParser(description="Configure environment variables for the bot.")
    parser.add_argument("--env-file", type=Path, default=ENV_FILE_DEFAULT, help="Path to the .env file")
    parser.add_argument(
        "--set",
        nargs="*",
        metavar="KEY=VALUE",
        help="Set one or more KEY=VALUE pairs non-interactively",
    )
    args = parser.parse_args()

    if args.set:
        pairs: Dict[str, str] = {}
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
