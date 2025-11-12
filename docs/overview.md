# Project Overview

This repository contains a grid-based trading bot that can operate against the
Bithumb cryptocurrency exchange or the Korea Investment & Securities (KIS)
OpenAPI.  The original single-file prototype has been expanded into a modular
codebase that supports configuration files, Home Assistant integration, and
HTML reporting driven by the collected CSV logs.

## High-level goals

1. **Reliable automation** – the bot manages split-buy grid orders with
   volatility-aware take-profit/stop-loss limits, CSV audit trails, and daily
   performance summaries.
2. **Simple operations** – a configuration CLI, Home Assistant add-on, and
   FastAPI gateway allow non-developers to provision API keys, tweak strategy
   parameters, and monitor status from a dashboard.
3. **Extensible architecture** – exchanges implement a common interface so
   additional brokers can be onboarded without rewriting the trading logic.

## Runtime architecture

| Component | Responsibility |
|-----------|----------------|
| `bot.config` | Loads `.env`/YAML settings into typed dataclasses for exchanges, strategy bands, and Home Assistant integrations. |
| `bot.strategy` | Implements the grid strategy with EWMA volatility estimation, order throttling, and dynamic TP/SL boundaries. |
| `bot.logs` | Writes trade events, errors, and daily summaries to CSV, reusing the exchange slug as a file prefix. |
| `bot.metrics` | Persists JSON metrics for Home Assistant and optionally publishes them to MQTT topics. |
| `exchanges.*` | REST clients for Bithumb and KIS, normalising orders, notional rules, and price/quantity rounding. |
| `tools/*` | Operational tooling for configuration (`configure_bot.py`), HTML reporting (`generate_report.py`), and the FastAPI gateway (`ha_gateway.py`). |
| `ha-addon/*` | Home Assistant add-on definition, Dockerfile, and init scripts that clone the repository, install dependencies, and launch the bot/gateway. |

## Execution flow

1. The runtime loads configuration using `BotConfig.load()`, which merges `.env`
   values, optional YAML overrides, and sensible defaults.
2. `GridStrategy` instantiates the selected exchange adapter, sets up the EWMA
   volatility estimator, and enters an infinite loop that:
   - fetches quotes,
   - evaluates buy triggers based on the configured grid,
   - executes sell orders when TP/SL criteria are met,
   - manages rate limiting and stale order cancellation, and
   - updates CSV logs plus the metrics payload consumed by Home Assistant.
3. Home Assistant users can interact through two channels:
   - the add-on configuration panel (translations describe each required
     environment variable) and
   - the optional FastAPI gateway (port 6443) which provides a lightweight UI,
     REST metrics, and on-demand report generation.

## Home Assistant add-on workflow

1. The Supervisor pulls the repository (via `repository.yaml`) and builds the
   add-on image defined in `ha-addon/Dockerfile`.
2. During container init the script `10-setup.sh` clones or updates `/opt/bot`,
   installs Python dependencies with `python -m pip`, validates mandatory
   credentials, and emits a `.env` file under `/data/bot`.
3. The service runner sources the `.env`, optionally starts the FastAPI gateway
   (via `python -m uvicorn tools.ha_gateway:app --port 6443`), and finally runs
   `python -m bot` to start the grid engine.
4. Metrics and reports are available inside Home Assistant through Ingress or a
   direct port mapping depending on the add-on configuration.

---

## Korean quick summary (한국어 요약)

- 하나의 봇으로 **빗썸**과 **한국투자증권 OpenAPI**를 모두 다룰 수 있도록
  구조화했습니다.
- 모든 전략/환경 설정은 `.env` 또는 `config/bot_config.yaml`에서 관리하며,
  `tools/configure_bot.py --wizard`를 통해 초보자도 손쉽게 값을 입력할 수
  있습니다.
- 거래 결과는 CSV로 기록되고 `tools/generate_report.py`가 Chart.js 기반의
  HTML 리포트를 만들어 줍니다.
- Home Assistant 애드온은 저장소 클론 → 의존성 설치 → 봇 실행 순서로
  동작하며, FastAPI 게이트웨이(포트 6443)가 실시간 지표와 설정 UI를 제공합니다.
