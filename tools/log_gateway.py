"""FastAPI applications exposing read-only access to bot logs."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from bot.config import BotConfig
from bot.logs import TradeLogger


def _load_logger() -> TradeLogger:
    return TradeLogger(BotConfig.load())


def _load_trades(path: Path, limit: int) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        reader = list(csv.DictReader(handle))
    return reader[-limit:]


def _load_errors(path: Path, limit: int) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-limit:]]


trade_app = FastAPI(title="Trading Bot Trade Log Gateway", version="1.0")
error_app = FastAPI(title="Trading Bot Error Log Gateway", version="1.0")


@trade_app.get("/health")
async def trade_health() -> Dict[str, str]:
    return {"status": "ok"}


@trade_app.get("/trades")
async def trades(limit: int = Query(100, ge=1, le=1000)) -> JSONResponse:
    logger = _load_logger()
    rows = _load_trades(logger.paths.trade_log, limit)
    return JSONResponse({"count": len(rows), "trades": rows, "path": str(logger.paths.trade_log)})


@trade_app.get("/")
async def trade_index(limit: int = Query(100, ge=1, le=500)) -> HTMLResponse:
    logger = _load_logger()
    rows = _load_trades(logger.paths.trade_log, limit)
    if not rows:
        body = "<p>거래 로그가 아직 없습니다.</p>"
    else:
        header = "".join(f"<th>{col}</th>" for col in rows[0].keys())
        table_rows = "".join(
            "<tr>" + "".join(f"<td>{row.get(col, '')}</td>" for col in rows[0].keys()) + "</tr>"
            for row in rows
        )
        body = f"<table><thead><tr>{header}</tr></thead><tbody>{table_rows}</tbody></table>"
    html = f"""
    <html>
    <head>
        <meta charset='utf-8'/>
        <title>Trade Log</title>
        <style>
            body {{ background: #0f172a; color: #e2e8f0; font-family: Arial, sans-serif; padding: 1.5rem; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
            th, td {{ border: 1px solid #1e293b; padding: 0.35rem; font-size: 0.9rem; }}
            th {{ background: #1e293b; }}
            tr:nth-child(even) {{ background: #1b2538; }}
            tr:nth-child(odd) {{ background: #131c2e; }}
            h1 {{ color: #38bdf8; }}
            a {{ color: #38bdf8; }}
        </style>
    </head>
    <body>
        <h1>거래 로그 (최근 {len(rows)}건)</h1>
        <p>파일 위치: {logger.paths.trade_log}</p>
        <p><a href="/trades?limit={limit}">JSON 보기</a></p>
        {body}
    </body>
    </html>
    """
    return HTMLResponse(html)


@error_app.get("/health")
async def error_health() -> Dict[str, str]:
    return {"status": "ok"}


@error_app.get("/errors")
async def errors(limit: int = Query(200, ge=1, le=2000), format: str = Query("json")) -> JSONResponse | PlainTextResponse:
    logger = _load_logger()
    rows = _load_errors(logger.paths.error_log, limit)
    if format.lower() == "text":
        text = "\n".join(rows) if rows else "(no errors)"
        return PlainTextResponse(text)
    return JSONResponse({"count": len(rows), "errors": rows, "path": str(logger.paths.error_log)})


@error_app.get("/")
async def error_index(limit: int = Query(200, ge=1, le=2000)) -> HTMLResponse:
    logger = _load_logger()
    rows = _load_errors(logger.paths.error_log, limit)
    items = "".join(f"<li><code>{line}</code></li>" for line in rows) or "<li>에러 로그가 없습니다.</li>"
    html = f"""
    <html>
    <head>
        <meta charset='utf-8'/>
        <title>Error Log</title>
        <style>
            body {{ background: #0f172a; color: #f8fafc; font-family: Arial, sans-serif; padding: 1.5rem; }}
            h1 {{ color: #f87171; }}
            ul {{ list-style: none; padding-left: 0; }}
            li {{ background: #1f2937; margin-bottom: 0.5rem; padding: 0.5rem; border-radius: 0.35rem; }}
            code {{ font-family: Consolas, 'Courier New', monospace; }}
            a {{ color: #38bdf8; }}
        </style>
    </head>
    <body>
        <h1>에러 로그 (최근 {len(rows)}줄)</h1>
        <p>파일 위치: {logger.paths.error_log}</p>
        <p><a href="/errors?limit={limit}">JSON 보기</a> · <a href="/errors?limit={limit}&format=text">텍스트 보기</a></p>
        <ul>{items}</ul>
    </body>
    </html>
    """
    return HTMLResponse(html)


__all__ = ["trade_app", "error_app"]
