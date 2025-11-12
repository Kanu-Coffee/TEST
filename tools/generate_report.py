"""Generate an interactive HTML report from bot CSV logs."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List

from bot.config import BotConfig
from bot.logs import TradeLogger

DEFAULT_OUTPUT = Path("reports/latest.html")


def _load_trades(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _load_summary(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _build_html(config: BotConfig, trades: List[Dict[str, str]], summary: List[Dict[str, str]]) -> str:
    trade_rows = "".join(
        f"<tr><td>{row['time']}</td><td>{row['side']}</td><td>{row['price']}</td>"
        f"<td>{row['units']}</td><td>{row['notional']}</td><td>{row['profit']}</td>"
        f"<td>{row['avg_price']}</td><td>{row['pos_units']}</td><td>{row['note']}</td></tr>"
        for row in trades
    )

    summary_rows = "".join(
        f"<tr><td>{row['date']}</td><td>{row['realized_profit']}</td><td>{row['trades']}</td>"
        f"<td>{row['win']}</td><td>{row['loss']}</td></tr>"
        for row in summary
    )

    cum_profit = []
    running = 0.0
    for row in trades:
        try:
            running += float(row.get("profit", 0) or 0)
        except ValueError:
            running += 0.0
        cum_profit.append(running)

    labels = [row.get("time", "") for row in trades]

    return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="utf-8" />
    <title>Trading Bot Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 2rem; background: #0f172a; color: #f8fafc; }}
        h1, h2 {{ color: #38bdf8; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
        th, td {{ border: 1px solid #1e293b; padding: 0.5rem; text-align: center; }}
        th {{ background: #1e293b; }}
        tr:nth-child(even) {{ background: #0f172a; }}
        tr:nth-child(odd) {{ background: #111c2f; }}
        .section {{ margin-bottom: 3rem; }}
    </style>
</head>
<body>
    <h1>거래 요약 - {config.bot.exchange}</h1>
    <p>심볼: {config.bot.symbol_ticker} | HF 모드: {config.bot.hf_mode} | 드라이런: {config.bot.dry_run}</p>
    <div class="section">
        <h2>누적 손익</h2>
        <canvas id="pnlChart"></canvas>
    </div>
    <div class="section">
        <h2>일별 실적</h2>
        <table>
            <thead>
                <tr><th>날짜</th><th>실현손익</th><th>거래수</th><th>승</th><th>패</th></tr>
            </thead>
            <tbody>{summary_rows or '<tr><td colspan="5">데이터가 없습니다</td></tr>'}</tbody>
        </table>
    </div>
    <div class="section">
        <h2>거래 내역</h2>
        <table>
            <thead>
                <tr><th>시간</th><th>구분</th><th>가격</th><th>수량</th><th>금액</th><th>손익</th><th>평단</th><th>보유수량</th><th>비고</th></tr>
            </thead>
            <tbody>{trade_rows or '<tr><td colspan="9">거래 기록이 없습니다</td></tr>'}</tbody>
        </table>
    </div>
    <script>
        const labels = {labels};
        const data = {cum_profit};
        const ctx = document.getElementById('pnlChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [{{
                    label: '누적 손익',
                    data: data,
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.15)',
                    tension: 0.2,
                    fill: true
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    x: {{ ticks: {{ color: '#cbd5f5' }} }},
                    y: {{ ticks: {{ color: '#cbd5f5' }} }}
                }},
                plugins: {{
                    legend: {{ labels: {{ color: '#f8fafc' }} }},
                    tooltip: {{ callbacks: {{ label: ctx => `${{ctx.parsed.y.toFixed(2)}} KRW` }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""


def generate_report(output_path: Path | None = None, config: BotConfig | None = None) -> Dict[str, str]:
    cfg = config or BotConfig.load()
    logger = TradeLogger(cfg)
    trades = _load_trades(logger.paths.trade_log)
    summary = _load_summary(logger.paths.summary_log)

    output = output_path or DEFAULT_OUTPUT
    if not output.is_absolute():
        output = Path.cwd() / output
    output.parent.mkdir(parents=True, exist_ok=True)

    html = _build_html(cfg, trades, summary)
    output.write_text(html, encoding="utf-8")
    return {"path": str(output)}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate HTML report from CSV logs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="저장할 HTML 파일 경로")
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = generate_report(args.output)
    print(f"리포트가 생성되었습니다: {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
