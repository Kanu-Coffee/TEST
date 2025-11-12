"""Generate an interactive HTML report from the bot CSV logs."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.config import BotConfig

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_REPORT = REPORTS_DIR / "latest.html"


def _slug(config: BotConfig) -> str:
    return config.exchange.lower()


def _trade_log(config: BotConfig) -> Path:
    return DATA_DIR / f"{_slug(config)}_trades.csv"


def _summary_log(config: BotConfig) -> Path:
    return DATA_DIR / f"{_slug(config)}_daily_summary.csv"


def _parse_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_trades(path: Path) -> Tuple[List[str], List[float], List[float]]:
    times: List[str] = []
    pnl: List[float] = []
    cumulative: List[float] = []
    total = 0.0
    if not path.exists():
        return times, pnl, cumulative
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("event") != "SELL":
                continue
            times.append(row.get("time", ""))
            profit = _parse_float(row.get("profit", "0"))
            pnl.append(profit)
            total += profit
            cumulative.append(total)
    return times, pnl, cumulative


def load_summary(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for row in rows:
        if "realized_profit" not in row and "realized_profit_krw" in row:
            row["realized_profit"] = row.get("realized_profit_krw", "0")
    return rows


def compute_stats(pnl: List[float]) -> dict:
    stats = {
        "trades": len(pnl),
        "wins": sum(1 for x in pnl if x >= 0),
        "losses": sum(1 for x in pnl if x < 0),
        "gross_profit": sum(x for x in pnl if x >= 0),
        "gross_loss": sum(x for x in pnl if x < 0),
        "net": sum(pnl),
    }
    stats["win_rate"] = (
        (stats["wins"] / stats["trades"]) * 100 if stats["trades"] else 0.0
    )
    return stats


def build_html(
    config: BotConfig,
    times: List[str],
    pnl: List[float],
    cumulative: List[float],
    daily: List[dict],
) -> str:
    stats = compute_stats(pnl)
    daily_dates = [row.get("date") for row in daily]
    daily_profit = [_parse_float(row.get("realized_profit")) for row in daily]
    pnl_colors = [
        "rgba(34,197,94,0.7)" if value >= 0 else "rgba(239,68,68,0.7)" for value in pnl
    ]
    currency = config.payment_currency if config.exchange != "KIS" else config.kis.currency

    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\">
    <title>Bot Performance ({config.exchange})</title>
    <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
        h1, h2 {{ color: #38bdf8; }}
        section {{ margin-bottom: 2.5rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem; }}
        .card {{ background: #1e293b; padding: 1.5rem; border-radius: 12px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.5); }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 0.5rem 0.75rem; text-align: left; }}
        tr:nth-child(even) {{ background: rgba(148, 163, 184, 0.1); }}
        canvas {{ max-width: 100%; }}
    </style>
</head>
<body>
    <h1>Split-Buy Bot Report ({config.exchange})</h1>
    <section class=\"grid\">
        <div class=\"card\">
            <h2>Overview</h2>
            <p>Total trades: {stats['trades']}</p>
            <p>Win rate: {stats['win_rate']:.2f}%</p>
            <p>Net PnL: {stats['net']:.2f} {currency}</p>
        </div>
        <div class=\"card\">
            <h2>Profit Breakdown</h2>
            <p>Gross profit: {stats['gross_profit']:.2f} {currency}</p>
            <p>Gross loss: {stats['gross_loss']:.2f} {currency}</p>
            <p>Wins / Losses: {stats['wins']} / {stats['losses']}</p>
        </div>
    </section>

    <section class=\"card\">
        <h2>Cumulative Profit</h2>
        <canvas id=\"cumChart\"></canvas>
    </section>

    <section class=\"card\">
        <h2>Trade PnL</h2>
        <canvas id=\"pnlChart\"></canvas>
    </section>

    <section class=\"card\">
        <h2>Daily Summary</h2>
        <canvas id=\"dailyChart\"></canvas>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Realized PnL ({currency})</th>
                    <th>Trades</th>
                    <th>Win</th>
                    <th>Loss</th>
                </tr>
            </thead>
            <tbody>
                {''.join(f"<tr><td>{row.get('date')}</td><td>{row.get('realized_profit')}</td><td>{row.get('trades')}</td><td>{row.get('win')}</td><td>{row.get('loss')}</td></tr>" for row in daily)}
            </tbody>
        </table>
    </section>

    <script>
        const ctxCum = document.getElementById('cumChart');
        new Chart(ctxCum, {{
            type: 'line',
            data: {{
                labels: {json.dumps(times)},
                datasets: [{{
                    label: 'Cumulative PnL ({currency})',
                    data: {json.dumps(cumulative)},
                    borderColor: '#34d399',
                    backgroundColor: 'rgba(52, 211, 153, 0.2)',
                    tension: 0.3,
                    fill: true,
                }}]
            }},
            options: {{
                scales: {{
                    x: {{ ticks: {{ color: '#94a3b8' }} }},
                    y: {{ ticks: {{ color: '#94a3b8' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }}
            }}
        }});

        const ctxPnl = document.getElementById('pnlChart');
        new Chart(ctxPnl, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(times)},
                datasets: [{{
                    label: 'Trade PnL ({currency})',
                    data: {json.dumps(pnl)},
                    backgroundColor: {json.dumps(pnl_colors)}
                }}]
            }},
            options: {{
                scales: {{
                    x: {{ ticks: {{ color: '#94a3b8' }} }},
                    y: {{ ticks: {{ color: '#94a3b8' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }}
            }}
        }});

        const ctxDaily = document.getElementById('dailyChart');
        new Chart(ctxDaily, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(daily_dates)},
                datasets: [{{
                    label: 'Daily Realized PnL ({currency})',
                    data: {json.dumps(daily_profit)},
                    backgroundColor: 'rgba(59,130,246,0.7)'
                }}]
            }},
            options: {{
                scales: {{
                    x: {{ ticks: {{ color: '#94a3b8' }} }},
                    y: {{ ticks: {{ color: '#94a3b8' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }}
            }}
        }});
    </script>
</body>
</html>
"""


def generate_report(
    output: Path | None = None,
    *,
    config: BotConfig | None = None,
) -> Dict[str, object]:
    config = config or BotConfig.load()
    trade_path = _trade_log(config)
    summary_path = _summary_log(config)
    times, pnl, cumulative = load_trades(trade_path)
    daily = load_summary(summary_path)
    html = build_html(config, times, pnl, cumulative, daily)
    target = output or DEFAULT_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return {
        "path": str(target),
        "stats": compute_stats(pnl),
        "trades": len(pnl),
        "daily": daily,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an HTML report using the configured exchange logs."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help="Target HTML file",
    )
    args = parser.parse_args()
    result = generate_report(args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
