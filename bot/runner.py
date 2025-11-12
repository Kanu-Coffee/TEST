"""Runtime entry point for the trading bot."""
from __future__ import annotations

from .config import BotConfig
from .logs import TradeLogger
from .metrics import MetricsPublisher
from .strategy import GridStrategy


def run_bot(config: BotConfig | None = None) -> None:
    cfg = config or BotConfig.load()
    logger = TradeLogger(cfg)
    publisher = MetricsPublisher(cfg, on_error=logger.log_error)
    strategy = GridStrategy(cfg, logger, publisher)

    print(
        f"🚀 Starting grid bot | exchange={cfg.bot.exchange} "
        f"symbol={cfg.bot.symbol_ticker} hf_mode={cfg.bot.hf_mode} dry_run={cfg.bot.dry_run}"
    )

    strategy.run_forever()


def main() -> None:
    try:
        run_bot()
    except KeyboardInterrupt:  # pragma: no cover - manual interruption
        print("Stopping bot (keyboard interrupt)")
    except Exception as exc:  # pragma: no cover - defensive
        cfg = BotConfig.load()
        logger = TradeLogger(cfg)
        logger.log_error(f"FATAL: {exc}")
        raise


if __name__ == "__main__":
    main()
