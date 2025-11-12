"""FastAPI gateway exposing configuration, metrics, and reports."""
from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from bot.config import BotConfig, ENV_PATH, save_yaml_config
from bot.metrics import DATA_DIR
from tools.generate_report import generate_report

app = FastAPI(title="Trading Bot Home Assistant Gateway", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_env() -> Dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    data: Dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _write_env(data: Dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in sorted(data.items())]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _metrics_path(config: BotConfig) -> Path:
    return DATA_DIR / config.home_assistant.rest_api.metrics_file


def _report_path(config: BotConfig) -> Path:
    path = Path(config.home_assistant.reporting.output_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


async def _auto_report_worker(interval_minutes: int, path: Path, config: BotConfig) -> None:
    await asyncio.sleep(5)
    seconds = max(1, interval_minutes) * 60
    while True:
        try:
            generate_report(path, config=config)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[HA Gateway] report generation failed: {exc}")
        await asyncio.sleep(seconds)


async def _stop_task() -> None:
    task = getattr(app.state, "report_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    app.state.report_task = None


async def _reload_state() -> None:
    cfg = BotConfig.load()
    app.state.config = cfg
    app.state.metrics_path = _metrics_path(cfg)
    app.state.report_path = _report_path(cfg)
    app.state.report_path.parent.mkdir(parents=True, exist_ok=True)
    if not app.state.report_path.exists():
        generate_report(app.state.report_path, config=cfg)
    await _stop_task()
    ha = cfg.home_assistant.reporting
    if ha.auto_generate:
        app.state.report_task = asyncio.create_task(
            _auto_report_worker(ha.interval_minutes, app.state.report_path, cfg)
        )


@app.on_event("startup")
async def startup() -> None:
    await _reload_state()


@app.on_event("shutdown")
async def shutdown() -> None:
    await _stop_task()


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> JSONResponse:
    cfg: BotConfig = app.state.config
    if not cfg.home_assistant.rest_api.enabled:
        raise HTTPException(status_code=403, detail="REST API disabled")
    path = app.state.metrics_path
    if not path.exists():
        return JSONResponse({"status": "idle", "message": "Metrics file not found"})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {"status": "error", "message": "Invalid metrics file"}
    return JSONResponse(data)


@app.get("/")
async def index() -> HTMLResponse:
    cfg: BotConfig = app.state.config
    env = _read_env()
    band = cfg.active_band()
    html = f"""
    <html>
    <head>
        <meta charset='utf-8'/>
        <title>Trading Bot Gateway</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #0f172a; color: #e5e7eb; padding: 2rem; }}
            h1 {{ color: #38bdf8; }}
            fieldset {{ border: 1px solid #1e293b; margin-bottom: 1.5rem; padding: 1rem; border-radius: 0.75rem; }}
            legend {{ padding: 0 0.5rem; color: #bae6fd; }}
            label {{ display: block; margin-bottom: 0.75rem; }}
            input {{ width: 100%; padding: 0.5rem; border-radius: 0.5rem; border: 1px solid #1e293b; background: #111c2f; color: #e5e7eb; }}
            button {{ background: #38bdf8; color: #0f172a; border: none; padding: 0.75rem 1.5rem; border-radius: 9999px; cursor: pointer; font-weight: bold; }}
            button:hover {{ background: #0ea5e9; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
            .note {{ font-size: 0.9rem; color: #cbd5f5; margin-top: 0.5rem; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 2rem; }}
            th, td {{ border: 1px solid #1e293b; padding: 0.5rem; text-align: left; }}
            th {{ background: #1e293b; }}
        </style>
    </head>
    <body>
        <h1>Trading Bot 설정</h1>
        <p>현재 사용 중인 환경변수 값을 수정하려면 아래 입력창을 채우고 저장 버튼을 클릭하세요.</p>
        <form method="post" action="/config">
            <fieldset>
                <legend>기본 설정</legend>
                <div class="grid">
                    <label>Exchange (필수)
                        <input name="EXCHANGE" value="{cfg.bot.exchange}" />
                        <span class="note">BITHUMB 또는 KIS</span>
                    </label>
                    <label>Symbol Ticker (필수)
                        <input name="BOT_SYMBOL_TICKER" value="{cfg.bot.symbol_ticker}" />
                        <span class="note">예: USDT_KRW, TQQQ</span>
                    </label>
                    <label>Order Currency
                        <input name="BOT_ORDER_CURRENCY" value="{cfg.bot.order_currency}" />
                    </label>
                    <label>Payment Currency
                        <input name="BOT_PAYMENT_CURRENCY" value="{cfg.bot.payment_currency}" />
                    </label>
                    <label>Dry Run (true/false)
                        <input name="BOT_DRY_RUN" value="{str(cfg.bot.dry_run).lower()}" />
                    </label>
                    <label>HF Mode (true/false)
                        <input name="BOT_HF_MODE" value="{str(cfg.bot.hf_mode).lower()}" />
                    </label>
                </div>
            </fieldset>
            <fieldset>
                <legend>전략 파라미터 (현재 활성화된 모드)</legend>
                <div class="grid">
                    <label>Base Order Value
                        <input name="ACTIVE_BASE_ORDER_VALUE" value="{band.base_order_value}" />
                    </label>
                    <label>Buy Step
                        <input name="ACTIVE_BUY_STEP" value="{band.buy_step}" />
                    </label>
                    <label>Martingale Multiplier
                        <input name="ACTIVE_MARTINGALE" value="{band.martingale_multiplier}" />
                    </label>
                    <label>Max Steps
                        <input name="ACTIVE_MAX_STEPS" value="{band.max_steps}" />
                    </label>
                    <label>Take Profit Floor
                        <input name="ACTIVE_TAKE_PROFIT" value="{band.tp_floor}" />
                    </label>
                    <label>Stop Loss Floor
                        <input name="ACTIVE_STOP_LOSS" value="{band.sl_floor}" />
                    </label>
                </div>
                <p class="note">HF 모드가 켜져 있으면 HF_* 환경변수를, 꺼져 있으면 DEFAULT_* 환경변수를 수정하세요.</p>
            </fieldset>
            <fieldset>
                <legend>API Credentials</legend>
                <div class="grid">
                    <label>Bithumb API Key
                        <input name="BITHUMB_API_KEY" value="{env.get('BITHUMB_API_KEY', '')}" />
                    </label>
                    <label>Bithumb API Secret
                        <input name="BITHUMB_API_SECRET" value="{env.get('BITHUMB_API_SECRET', '')}" />
                    </label>
                    <label>KIS App Key
                        <input name="KIS_APP_KEY" value="{env.get('KIS_APP_KEY', '')}" />
                    </label>
                    <label>KIS App Secret
                        <input name="KIS_APP_SECRET" value="{env.get('KIS_APP_SECRET', '')}" />
                    </label>
                    <label>KIS Account No
                        <input name="KIS_ACCOUNT_NO" value="{env.get('KIS_ACCOUNT_NO', '')}" />
                    </label>
                    <label>KIS Account Password
                        <input name="KIS_ACCOUNT_PASSWORD" value="{env.get('KIS_ACCOUNT_PASSWORD', '')}" />
                    </label>
                </div>
            </fieldset>
            <button type="submit">저장</button>
        </form>
        <table>
            <thead><tr><th>환경변수</th><th>현재 값</th></tr></thead>
            <tbody>
                {''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k, v in sorted(env.items())) or '<tr><td colspan="2">.env 파일이 없습니다</td></tr>'}
            </tbody>
        </table>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.post("/config")
async def update_config(
    EXCHANGE: str = Form(...),
    BOT_SYMBOL_TICKER: str = Form(...),
    BOT_ORDER_CURRENCY: str = Form(...),
    BOT_PAYMENT_CURRENCY: str = Form(...),
    BOT_DRY_RUN: str = Form(...),
    BOT_HF_MODE: str = Form(...),
    ACTIVE_BASE_ORDER_VALUE: str = Form(...),
    ACTIVE_BUY_STEP: str = Form(...),
    ACTIVE_MARTINGALE: str = Form(...),
    ACTIVE_MAX_STEPS: str = Form(...),
    ACTIVE_TAKE_PROFIT: str = Form(...),
    ACTIVE_STOP_LOSS: str = Form(...),
    BITHUMB_API_KEY: str = Form(""),
    BITHUMB_API_SECRET: str = Form(""),
    KIS_APP_KEY: str = Form(""),
    KIS_APP_SECRET: str = Form(""),
    KIS_ACCOUNT_NO: str = Form(""),
    KIS_ACCOUNT_PASSWORD: str = Form(""),
) -> HTMLResponse:
    env = _read_env()
    env.update(
        {
            "EXCHANGE": EXCHANGE.strip().upper(),
            "BOT_SYMBOL_TICKER": BOT_SYMBOL_TICKER.strip(),
            "BOT_ORDER_CURRENCY": BOT_ORDER_CURRENCY.strip(),
            "BOT_PAYMENT_CURRENCY": BOT_PAYMENT_CURRENCY.strip(),
            "BOT_DRY_RUN": BOT_DRY_RUN.strip().lower(),
            "BOT_HF_MODE": BOT_HF_MODE.strip().lower(),
            "BITHUMB_API_KEY": BITHUMB_API_KEY.strip(),
            "BITHUMB_API_SECRET": BITHUMB_API_SECRET.strip(),
            "KIS_APP_KEY": KIS_APP_KEY.strip(),
            "KIS_APP_SECRET": KIS_APP_SECRET.strip(),
            "KIS_ACCOUNT_NO": KIS_ACCOUNT_NO.strip(),
            "KIS_ACCOUNT_PASSWORD": KIS_ACCOUNT_PASSWORD.strip(),
        }
    )

    prefix = "HF" if BOT_HF_MODE.strip().lower() in {"true", "1", "y", "yes"} else "DEFAULT"
    env[f"{prefix}_BASE_ORDER_VALUE"] = ACTIVE_BASE_ORDER_VALUE.strip()
    env[f"{prefix}_BUY_STEP"] = ACTIVE_BUY_STEP.strip()
    env[f"{prefix}_MARTINGALE_MUL"] = ACTIVE_MARTINGALE.strip()
    env[f"{prefix}_MAX_STEPS"] = ACTIVE_MAX_STEPS.strip()
    env[f"{prefix}_TAKE_PROFIT"] = ACTIVE_TAKE_PROFIT.strip()
    env[f"{prefix}_STOP_LOSS"] = ACTIVE_STOP_LOSS.strip()

    _write_env(env)
    cfg = BotConfig.load()
    save_yaml_config(cfg.to_dict())
    await _reload_state()
    return HTMLResponse("<p>설정이 저장되었습니다. <a href='/'>&larr; 돌아가기</a></p>")


@app.post("/generate-report")
async def trigger_report() -> Dict[str, str]:
    cfg: BotConfig = app.state.config
    result = generate_report(app.state.report_path, config=cfg)
    return {"path": result["path"]}


@app.get("/report")
async def report() -> FileResponse:
    cfg: BotConfig = app.state.config
    if not cfg.home_assistant.reporting.serve_report:
        raise HTTPException(status_code=403, detail="Report serving disabled")
    path = app.state.report_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=6443)


if __name__ == "__main__":
    main()
