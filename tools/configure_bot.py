"""Interactive configuration helper for the trading bot."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple

from bot.config import BotConfig, ENV_PATH, save_yaml_config


def _read_env_file(path: Path = ENV_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    data: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _write_env_file(values: Dict[str, str], path: Path = ENV_PATH) -> None:
    lines = [f"{key}={value}" for key, value in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prompt(label: str, *, default: str = "", required: bool = False, secret: bool = False) -> str:
    while True:
        display_default = f" [{default}]" if default else ""
        suffix = " (필수)" if required else ""
        raw = input(f"{label}{suffix}{display_default}: ").strip()
        if not raw:
            raw = default
        if required and not raw:
            print("값을 입력해주세요.")
            continue
        if secret and raw:
            print("입력 완료")
        return raw


def _bool_prompt(label: str, *, default: bool) -> bool:
    text = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} ({text}): ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes", "1", "true"}:
            return True
        if raw in {"n", "no", "0", "false"}:
            return False
        print("y 또는 n으로 입력해주세요.")


def run_wizard() -> None:
    print("\n=== 거래 봇 설정 마법사 ===\n")
    existing = _read_env_file()
    env: Dict[str, str] = dict(existing)

    exchange = _prompt("거래소 (BITHUMB 또는 KIS)", default=existing.get("EXCHANGE", "BITHUMB"))
    exchange = exchange.strip().upper() or "BITHUMB"
    env["EXCHANGE"] = exchange

    env["BOT_SYMBOL_TICKER"] = _prompt(
        "거래 심볼 (예: USDT_KRW 또는 TQQQ)",
        default=existing.get("BOT_SYMBOL_TICKER", "USDT_KRW"),
        required=True,
    )
    env["BOT_ORDER_CURRENCY"] = _prompt(
        "주문 통화 (예: USDT 또는 TQQQ)",
        default=existing.get("BOT_ORDER_CURRENCY", "USDT"),
        required=True,
    )
    env["BOT_PAYMENT_CURRENCY"] = _prompt(
        "결제 통화 (예: KRW 또는 USD)",
        default=existing.get("BOT_PAYMENT_CURRENCY", "KRW"),
        required=True,
    )

    dry_run = _bool_prompt("드라이런 모드로 시작할까요?", default=existing.get("BOT_DRY_RUN", "true").lower() in {"true", "1", "y"})
    env["BOT_DRY_RUN"] = str(dry_run).lower()
    hf_mode = _bool_prompt("고빈도(HF) 전략을 활성화할까요?", default=existing.get("BOT_HF_MODE", "true").lower() in {"true", "1", "y"})
    env["BOT_HF_MODE"] = str(hf_mode).lower()

    env["DEFAULT_BASE_ORDER_VALUE"] = _prompt(
        "기본 모드 1회 주문 금액 (KRW)",
        default=existing.get("DEFAULT_BASE_ORDER_VALUE", "5000"),
        required=True,
    )
    env["DEFAULT_BUY_STEP"] = _prompt(
        "기본 모드 매수 간격 (예: 0.008)",
        default=existing.get("DEFAULT_BUY_STEP", "0.008"),
        required=True,
    )
    env["DEFAULT_MARTINGALE_MUL"] = _prompt(
        "기본 모드 물타기 배수 (예: 1.5)",
        default=existing.get("DEFAULT_MARTINGALE_MUL", existing.get("DEFAULT_STEP_MULTIPLIER", "1.5")),
        required=True,
    )
    env["DEFAULT_MAX_STEPS"] = _prompt(
        "기본 모드 최대 스텝 수",
        default=existing.get("DEFAULT_MAX_STEPS", "10"),
        required=True,
    )
    env["DEFAULT_TAKE_PROFIT"] = _prompt(
        "기본 모드 최소 익절 비율 (예: 0.008)",
        default=existing.get("DEFAULT_TAKE_PROFIT", "0.008"),
        required=True,
    )
    env["DEFAULT_STOP_LOSS"] = _prompt(
        "기본 모드 최대 손절 비율 (예: 0.012)",
        default=existing.get("DEFAULT_STOP_LOSS", "0.012"),
        required=True,
    )

    env["HF_BASE_ORDER_VALUE"] = _prompt(
        "HF 모드 1회 주문 금액",
        default=existing.get("HF_BASE_ORDER_VALUE", "5000"),
        required=True,
    )
    env["HF_BUY_STEP"] = _prompt(
        "HF 모드 매수 간격",
        default=existing.get("HF_BUY_STEP", "0.005"),
        required=True,
    )
    env["HF_MARTINGALE_MUL"] = _prompt(
        "HF 모드 물타기 배수",
        default=existing.get("HF_MARTINGALE_MUL", "1.3"),
        required=True,
    )
    env["HF_MAX_STEPS"] = _prompt(
        "HF 모드 최대 스텝 수",
        default=existing.get("HF_MAX_STEPS", "10"),
        required=True,
    )
    env["HF_TAKE_PROFIT"] = _prompt(
        "HF 모드 최소 익절 비율",
        default=existing.get("HF_TAKE_PROFIT", "0.006"),
        required=True,
    )
    env["HF_STOP_LOSS"] = _prompt(
        "HF 모드 최대 손절 비율",
        default=existing.get("HF_STOP_LOSS", "0.010"),
        required=True,
    )

    env["TIMEZONE"] = _prompt(
        "보고 및 로그에 사용할 타임존",
        default=existing.get("TIMEZONE", "Asia/Seoul"),
        required=True,
    )
    env["REPORT_INTERVAL_MINUTES"] = _prompt(
        "자동 리포트 주기(분)",
        default=existing.get("REPORT_INTERVAL_MINUTES", "60"),
        required=True,
    )
    env["LOG_LEVEL"] = _prompt(
        "로그 레벨 (DEBUG/INFO/WARNING)",
        default=existing.get("LOG_LEVEL", "INFO"),
        required=True,
    )

    if exchange == "BITHUMB":
        print("\n--- 빗썸 API 키 ---")
        env["BITHUMB_API_KEY"] = _prompt("API Key", default=existing.get("BITHUMB_API_KEY", ""), required=not dry_run, secret=True)
        env["BITHUMB_API_SECRET"] = _prompt(
            "API Secret",
            default=existing.get("BITHUMB_API_SECRET", ""),
            required=not dry_run,
            secret=True,
        )
    elif exchange == "KIS":
        print("\n--- 한국투자증권 OpenAPI ---")
        env["KIS_APP_KEY"] = _prompt("App Key", default=existing.get("KIS_APP_KEY", ""), required=True, secret=True)
        env["KIS_APP_SECRET"] = _prompt("App Secret", default=existing.get("KIS_APP_SECRET", ""), required=True, secret=True)
        env["KIS_ACCOUNT_NO"] = _prompt(
            "계좌번호 (8자리 + 지점번호)",
            default=existing.get("KIS_ACCOUNT_NO", ""),
            required=True,
        )
        env["KIS_ACCOUNT_PASSWORD"] = _prompt(
            "계좌 비밀번호",
            default=existing.get("KIS_ACCOUNT_PASSWORD", ""),
            required=not dry_run,
            secret=True,
        )
        env["KIS_MODE"] = _prompt(
            "거래 모드 (paper 또는 live)",
            default=existing.get("KIS_MODE", "paper"),
            required=True,
        )
        env["KIS_EXCHANGE_CODE"] = _prompt(
            "거래소 코드 (예: NASD)",
            default=existing.get("KIS_EXCHANGE_CODE", "NASD"),
            required=True,
        )
        env["KIS_SYMBOL"] = _prompt(
            "종목 코드 (예: TQQQ)",
            default=existing.get("KIS_SYMBOL", "TQQQ"),
            required=True,
        )
        env["KIS_CURRENCY"] = _prompt(
            "통화 (예: USD)",
            default=existing.get("KIS_CURRENCY", "USD"),
            required=True,
        )
        env["KIS_ORDER_LOT_SIZE"] = _prompt(
            "최소 주문 주식 수",
            default=existing.get("KIS_ORDER_LOT_SIZE", "1"),
            required=True,
        )

    _write_env_file(env)
    cfg = BotConfig.load()
    save_yaml_config(cfg.to_dict())
    print("\n설정이 저장되었습니다. .env 및 config/bot_config.yaml 파일을 확인하세요.\n")


def apply_set(assignments: Iterable[str]) -> None:
    if not assignments:
        return
    env = _read_env_file()
    for item in assignments:
        if "=" not in item:
            raise ValueError(f"Invalid assignment: {item}")
        key, value = item.split("=", 1)
        env[key.strip()] = value.strip()
    _write_env_file(env)
    cfg = BotConfig.load()
    save_yaml_config(cfg.to_dict())


def show_config() -> None:
    cfg = BotConfig.load()
    print("\n=== 현재 설정 ===")
    for section, values in cfg.to_dict().items():
        if isinstance(values, dict):
            print(f"[{section}]")
            for key, value in values.items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"    - {sub_key}: {sub_value}")
                else:
                    print(f"  - {key}: {value}")
        else:
            print(f"{section}: {values}")
    print()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure the trading bot")
    parser.add_argument("--wizard", action="store_true", help="간단한 질답 형식으로 설정합니다")
    parser.add_argument("--show", action="store_true", help="현재 설정 값을 출력합니다")
    parser.add_argument("--set", metavar="KEY=VALUE", nargs="*", help="지정된 환경변수를 업데이트합니다")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.set:
            apply_set(args.set)
        if args.wizard:
            run_wizard()
        elif args.show:
            show_config()
        elif not args.set:
            parser.print_help()
    except Exception as exc:
        print(f"설정 중 오류가 발생했습니다: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
