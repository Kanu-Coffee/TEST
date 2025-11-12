"""Structured logging helpers for the trading bot."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict

from .config import BotConfig, ROOT_DIR

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class TradeLogPaths:
    trade_log: Path
    error_log: Path
    summary_log: Path


def _slug(config: BotConfig) -> str:
    return config.bot.exchange.lower()


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TradeLogger:
    """Handle CSV logging, error tracking, and daily summaries."""

    def __init__(self, config: BotConfig) -> None:
        slug = _slug(config)
        self.paths = TradeLogPaths(
            trade_log=DATA_DIR / f"{slug}_trades.csv",
            error_log=DATA_DIR / f"{slug}_errors.log",
            summary_log=DATA_DIR / f"{slug}_daily_summary.csv",
        )
        self._ensure_headers()
        self._summary_cache = self._load_summary()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def log_trade(
        self,
        *,
        event: str,
        side: str,
        price: float,
        quantity: float,
        notional: float,
        profit: float,
        avg_price: float,
        position_units: float,
        tp_ratio: float,
        sl_ratio: float,
        note: str = "",
        order_id: str = "",
    ) -> None:
        row = [
            _timestamp(),
            event,
            side,
            f"{price:.6f}",
            f"{quantity:.6f}",
            f"{notional:.2f}",
            f"{profit:.2f}",
            f"{avg_price:.6f}",
            f"{position_units:.6f}",
            f"{tp_ratio:.5f}",
            f"{sl_ratio:.5f}",
            note,
            order_id,
        ]
        with self.paths.trade_log.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(row)

    def log_error(self, message: str) -> None:
        self.paths.error_log.parent.mkdir(parents=True, exist_ok=True)
        with self.paths.error_log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{_timestamp()}] {message}\n")

    def record_daily(self, pnl_value: float, is_win: bool, is_loss: bool) -> None:
        key = datetime.now().strftime("%Y-%m-%d")
        row = self._summary_cache.setdefault(
            key,
            {"realized_profit": 0.0, "trades": 0, "win": 0, "loss": 0},
        )
        row["realized_profit"] += pnl_value
        row["trades"] += 1
        if is_win:
            row["win"] += 1
        if is_loss:
            row["loss"] += 1
        self._persist_summary()

    def summary_snapshot(self) -> Dict[str, Dict[str, float]]:
        return {key: dict(value) for key, value in self._summary_cache.items()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_headers(self) -> None:
        if not self.paths.trade_log.exists():
            with self.paths.trade_log.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(
                    [
                        "time",
                        "event",
                        "side",
                        "price",
                        "units",
                        "notional",
                        "profit",
                        "avg_price",
                        "pos_units",
                        "tp",
                        "sl",
                        "note",
                        "order_id",
                    ]
                )
        if not self.paths.summary_log.exists():
            with self.paths.summary_log.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(
                    ["date", "realized_profit", "trades", "win", "loss"]
                )

    def _load_summary(self) -> Dict[str, Dict[str, float]]:
        if not self.paths.summary_log.exists():
            return {}
        cache: Dict[str, Dict[str, float]] = {}
        with self.paths.summary_log.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    cache[row["date"]] = {
                        "realized_profit": float(row.get("realized_profit", 0.0) or 0.0),
                        "trades": float(row.get("trades", 0) or 0),
                        "win": float(row.get("win", 0) or 0),
                        "loss": float(row.get("loss", 0) or 0),
                    }
                except (KeyError, ValueError):
                    continue
        return cache

    def _persist_summary(self) -> None:
        with self.paths.summary_log.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "realized_profit", "trades", "win", "loss"])
            for date in sorted(self._summary_cache):
                row = self._summary_cache[date]
                writer.writerow(
                    [
                        date,
                        f"{row['realized_profit']:.2f}",
                        int(row["trades"]),
                        int(row["win"]),
                        int(row["loss"]),
                    ]
                )


__all__ = ["TradeLogger", "TradeLogPaths", "DATA_DIR"]
