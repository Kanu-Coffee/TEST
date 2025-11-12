"""FastAPI service that exposes bot metrics for Home Assistant."""
from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from bot.config import (
    BotConfig,
    config_to_yaml_dict,
    load_yaml_config,
    save_yaml_config,
)
from tools.generate_report import DEFAULT_REPORT, generate_report

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Bithumb Bot Home Assistant Gateway", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _metrics_path(config: BotConfig) -> Path:
    return DATA_DIR / config.home_assistant.metrics_file


def _report_path(config: BotConfig) -> Path:
    return _resolve_path(config.home_assistant.reporting.output_path)


def _load_metrics(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"status": "idle", "message": "Metrics file not found."}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid metrics file"}


async def _auto_report_worker(interval_minutes: int, output_path: Path) -> None:
    interval = max(1, interval_minutes) * 60
    await asyncio.sleep(5)
    while True:
        try:
            result = generate_report(output_path)
            print(f"[HA Gateway] Report refreshed at {result['path']}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[HA Gateway] Report generation failed: {exc}")
        await asyncio.sleep(interval)


@app.on_event("startup")
async def _startup() -> None:
    await _reload_state()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await _stop_report_task()


async def _stop_report_task() -> None:
    task = getattr(app.state, "report_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    app.state.report_task = None


async def _reload_state() -> None:
    app.state.config = BotConfig.load()
    app.state.metrics_path = _metrics_path(app.state.config)
    app.state.report_path = _report_path(app.state.config)
    if not app.state.report_path.exists():
        generate_report(app.state.report_path, config=app.state.config)
    await _stop_report_task()
    ha = app.state.config.home_assistant
    if ha.reporting.auto_generate:
        app.state.report_task = asyncio.create_task(
            _auto_report_worker(ha.reporting.interval_minutes, app.state.report_path)
        )


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Dict[str, Any]:
    if not app.state.config.home_assistant.rest_api.enabled:
        raise HTTPException(status_code=403, detail="REST API disabled")
    return _load_metrics(app.state.metrics_path)


@app.post("/generate-report")
async def trigger_report() -> Dict[str, Any]:
    return generate_report(app.state.report_path, config=app.state.config)


@app.get("/report")
async def report() -> FileResponse:
    if not app.state.config.home_assistant.reporting.serve_report:
        raise HTTPException(status_code=403, detail="Report serving disabled")
    path = app.state.report_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path)


def _build_form(config: Dict[str, Any]) -> str:
    bot = config.get("bot", {})
    bithumb_cfg = config.get("bithumb", {})
    kis_cfg = config.get("kis", {})
    ha = config.get("home_assistant", {})
    mqtt = ha.get("mqtt", {})
    reporting = ha.get("reporting", {})
    rest_api = ha.get("rest_api", {})

    def _is_true(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "t", "yes", "y", "on"}
        return bool(value)

    def _checked(value: Any) -> str:
        return "checked" if _is_true(value) else ""

    try:
        default_output = str(DEFAULT_REPORT.relative_to(ROOT_DIR))
    except ValueError:
        default_output = str(DEFAULT_REPORT)
    output_value = reporting.get("output_path", default_output)

    return f"""
    <html>
    <head>
        <meta charset='utf-8'>
        <title>Bithumb Bot Configuration</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 2rem; background: #111827; color: #e5e7eb; }}
            h1 {{ color: #38bdf8; }}
            fieldset {{ margin-bottom: 1.5rem; border: 1px solid #334155; padding: 1rem; border-radius: 8px; }}
            label {{ display: block; margin-bottom: 0.75rem; }}
            input[type="text"], input[type="number"] {{ width: 100%; padding: 0.5rem; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #e2e8f0; }}
            .row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
            button {{ background: #38bdf8; color: #0f172a; padding: 0.75rem 1.5rem; border: none; border-radius: 9999px; cursor: pointer; font-weight: bold; }}
            button:hover {{ background: #0ea5e9; }}
        </style>
    </head>
    <body>
        <h1>Bithumb Bot Configuration</h1>
        <form method="post" action="/config">
            <fieldset>
                <legend>Bot</legend>
                <div class="row">
                    <label>Exchange
                        <input type="text" name="bot.exchange" value="{bot.get('exchange', 'BITHUMB')}" />
                    </label>
                    <label>Symbol ticker
                        <input type="text" name="bot.symbol_ticker" value="{bot.get('symbol_ticker', '')}" />
                    </label>
                    <label>Order currency
                        <input type="text" name="bot.order_currency" value="{bot.get('order_currency', '')}" />
                    </label>
                    <label>Payment currency
                        <input type="text" name="bot.payment_currency" value="{bot.get('payment_currency', '')}" />
                    </label>
                </div>
                <div class="row">
                    <label>HF mode
                        <input type="checkbox" name="bot.hf_mode" value="true" {_checked(bot.get('hf_mode', False))} />
                    </label>
                    <label>Dry run
                        <input type="checkbox" name="bot.dry_run" value="true" {_checked(bot.get('dry_run', True))} />
                    </label>
                </div>
            </fieldset>
            <fieldset>
                <legend>Bithumb</legend>
                <div class="row">
                    <label>API key
                        <input type="text" name="bithumb.api_key" value="{bithumb_cfg.get('api_key', '')}" />
                    </label>
                    <label>API secret
                        <input type="text" name="bithumb.api_secret" value="{bithumb_cfg.get('api_secret', '')}" />
                    </label>
                </div>
                <div class="row">
                    <label>Base URL
                        <input type="text" name="bithumb.base_url" value="{bithumb_cfg.get('base_url', 'https://api.bithumb.com')}" />
                    </label>
                    <label>Auth mode
                        <input type="text" name="bithumb.auth_mode" value="{bithumb_cfg.get('auth_mode', 'legacy')}" />
                    </label>
                </div>
            </fieldset>
            <fieldset>
                <legend>KIS OpenAPI</legend>
                <div class="row">
                    <label>App key
                        <input type="text" name="kis.app_key" value="{kis_cfg.get('app_key', '')}" />
                    </label>
                    <label>App secret
                        <input type="text" name="kis.app_secret" value="{kis_cfg.get('app_secret', '')}" />
                    </label>
                    <label>Account no.
                        <input type="text" name="kis.account_no" value="{kis_cfg.get('account_no', '')}" />
                    </label>
                </div>
                <div class="row">
                    <label>Account password
                        <input type="text" name="kis.account_password" value="{kis_cfg.get('account_password', '')}" />
                    </label>
                    <label>Mode (paper/live)
                        <input type="text" name="kis.mode" value="{kis_cfg.get('mode', 'paper')}" />
                    </label>
                    <label>Order lot size
                        <input type="number" step="0.01" name="kis.order_lot_size" value="{kis_cfg.get('order_lot_size', 1.0)}" />
                    </label>
                </div>
                <div class="row">
                    <label>Exchange code
                        <input type="text" name="kis.exchange_code" value="{kis_cfg.get('exchange_code', 'NASD')}" />
                    </label>
                    <label>Symbol
                        <input type="text" name="kis.symbol" value="{kis_cfg.get('symbol', 'TQQQ')}" />
                    </label>
                    <label>Currency
                        <input type="text" name="kis.currency" value="{kis_cfg.get('currency', 'USD')}" />
                    </label>
                </div>
            </fieldset>
            <fieldset>
                <legend>MQTT</legend>
                <div class="row">
                    <label>Enable MQTT
                        <input type="checkbox" name="mqtt.enabled" value="true" {_checked(mqtt.get('enabled', False))} />
                    </label>
                    <label>Host
                        <input type="text" name="mqtt.host" value="{mqtt.get('host', '')}" />
                    </label>
                    <label>Port
                        <input type="number" name="mqtt.port" value="{mqtt.get('port', 1883)}" />
                    </label>
                    <label>Username
                        <input type="text" name="mqtt.username" value="{mqtt.get('username', '')}" />
                    </label>
                    <label>Password
                        <input type="text" name="mqtt.password" value="{mqtt.get('password', '')}" />
                    </label>
                    <label>Base topic
                        <input type="text" name="mqtt.base_topic" value="{mqtt.get('base_topic', 'bithumb_bot')}" />
                    </label>
                </div>
            </fieldset>
            <fieldset>
                <legend>Reporting</legend>
                <div class="row">
                    <label>Auto-generate report
                        <input type="checkbox" name="reporting.auto_generate" value="true" {_checked(reporting.get('auto_generate', True))} />
                    </label>
                    <label>Interval minutes
                        <input type="number" name="reporting.interval_minutes" value="{reporting.get('interval_minutes', 60)}" />
                    </label>
                    <label>Serve report over HTTP
                        <input type="checkbox" name="reporting.serve_report" value="true" {_checked(reporting.get('serve_report', True))} />
                    </label>
                    <label>Host
                        <input type="text" name="reporting.host" value="{reporting.get('host', '0.0.0.0')}" />
                    </label>
                    <label>Port
                        <input type="number" name="reporting.port" value="{reporting.get('port', 8080)}" />
                    </label>
                    <label>Ingress path
                        <input type="text" name="reporting.ingress_path" value="{reporting.get('ingress_path', '/bithumb-bot')}" />
                    </label>
                    <label>Output path
                        <input type="text" name="reporting.output_path" value="{output_value}" />
                    </label>
                </div>
            </fieldset>
            <fieldset>
                <legend>REST API</legend>
                <div class="row">
                    <label>Enable REST API
                        <input type="checkbox" name="rest_api.enabled" value="true" {_checked(rest_api.get('enabled', True))} />
                    </label>
                    <label>Host
                        <input type="text" name="rest_api.host" value="{rest_api.get('host', '0.0.0.0')}" />
                    </label>
                    <label>Port
                        <input type="number" name="rest_api.port" value="{rest_api.get('port', 8080)}" />
                    </label>
                </div>
            </fieldset>
            <button type="submit">Save configuration</button>
        </form>
    </body>
    </html>
    """


@app.get("/")
async def index() -> HTMLResponse:
    cfg = load_yaml_config() or config_to_yaml_dict(app.state.config)
    return HTMLResponse(_build_form(cfg))


def _update_nested(target: Dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    current = target
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


@app.post("/config")
async def update_config(request: Request) -> RedirectResponse:
    current = load_yaml_config() or config_to_yaml_dict(app.state.config)
    form = await request.form()
    bool_fields = {
        "bot.hf_mode",
        "bot.dry_run",
        "mqtt.enabled",
        "reporting.auto_generate",
        "reporting.serve_report",
        "rest_api.enabled",
    }
    int_fields = {
        "mqtt.port",
        "reporting.interval_minutes",
        "reporting.port",
        "rest_api.port",
    }

    for field in bool_fields:
        _update_nested(current, field, form.get(field) is not None)

    for field in int_fields:
        raw = form.get(field)
        if raw is None or raw == "":
            continue
        try:
            value = int(raw)
        except ValueError:
            value = raw
        _update_nested(current, field, value)

    for key, value in form.items():
        if key in bool_fields or key in int_fields:
            continue
        _update_nested(current, key, value)

    save_yaml_config(current)
    await _reload_state()
    return RedirectResponse(url="/", status_code=303)


@app.get("/config/json")
async def config_json() -> JSONResponse:
    return JSONResponse(config_to_yaml_dict(app.state.config))
