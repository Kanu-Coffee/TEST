# Multi-Exchange Split-Buy Bot

A modular trading bot that executes a volatility-aware split-buy strategy on
Bithumb (crypto) or the Korea Investment & Securities OpenAPI (overseas
equities).  The project bundles CLI tooling, an HTML report generator, and a
Home Assistant add-on so that long-running deployments can be monitored without
leaving the dashboard.

> 📚 New to the codebase? Start with the [project overview](docs/overview.md) and
> then read the [strategy & environment guide](docs/strategy_guide.md).

## Features

- **Dual-exchange support** – choose between Bithumb or KIS by switching the
  `EXCHANGE` environment variable; both share the same strategy core.
- **Dynamic grid strategy** – EWMA volatility drives take-profit/stop-loss bounds
  while respecting user-defined floors and martingale-style position sizing.
- **Robust logging & reporting** – CSV trades/errors/daily summaries in `data/`
  plus a Chart.js HTML dashboard generated via `tools/generate_report.py`.
- **Friendly configuration** – interactive wizard (`tools/configure_bot.py`),
  `.env` / YAML storage, and a FastAPI web form that mirrors the Home Assistant
  add-on UI.
- **Home Assistant integration** – optional MQTT metrics, JSON snapshots, and an
  add-on that clones the repo, installs dependencies with `python -m pip`, and
  launches the bot + gateway on port `6443`.

## Quick start (English)

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create or update `.env`**
   ```bash
   python tools/configure_bot.py --wizard
   ```
   - Choose the exchange (`BITHUMB` or `KIS`).
   - Enter API keys / account information when prompted.
   - The wizard also records strategy values (base order value, buy step, TP/SL).

3. **Run the bot (dry-run by default)**
   ```bash
   python -m bot
   ```
   - Edit `.env` and set `BOT_DRY_RUN=false` only after verifying in simulation.

4. **Generate a report**
   ```bash
   python tools/generate_report.py --output reports/latest.html
   ```
   Open the resulting HTML file in a browser to inspect trades and daily stats.

5. **Optional – start the FastAPI gateway**
   ```bash
   uvicorn tools.ha_gateway:app --host 0.0.0.0 --port 6443
   ```
   - `http://localhost:6443` shows the config form and `.env` contents.
   - `GET /metrics` returns the latest JSON snapshot for automations.
   - `POST /generate-report` refreshes the HTML report; `GET /report` serves it
     when `REPORT_SERVE=true`.

## 빠르게 시작하기 (한국어)

1. **필수 패키지 설치**
   ```bash
   pip install -r requirements.txt
   ```

2. **환경변수 설정 마법사 실행**
   ```bash
   python tools/configure_bot.py --wizard
   ```
   - 첫 질문에서 거래소(`BITHUMB` 또는 `KIS`)를 고르고 안내에 따라 API 키,
     계좌번호, 주문 파라미터를 입력합니다.
   - 입력이 끝나면 `.env`와 `config/bot_config.yaml`이 동시에 갱신됩니다.

3. **봇 실행 (기본은 드라이런)**
   ```bash
   python -m bot
   ```
   - 터미널에 매수/매도 로그가 출력되고, `data/` 폴더에 CSV가 쌓입니다.
   - 실거래로 전환하려면 `.env`에서 `BOT_DRY_RUN=false`로 바꾼 뒤 다시 실행하세요.

4. **HTML 리포트 생성**
   ```bash
   python tools/generate_report.py --output reports/latest.html
   ```
   - `reports/latest.html`을 브라우저로 열면 누적 손익 그래프와 거래 목록을
     확인할 수 있습니다.

5. **FastAPI 게이트웨이 (선택)**
   ```bash
   uvicorn tools.ha_gateway:app --host 0.0.0.0 --port 6443
   ```
   - `http://localhost:6443`에서 `.env` 값을 웹 UI로 수정할 수 있습니다.
   - `/metrics`, `/report`, `/generate-report` 엔드포인트가 자동화 및 대시보드에
     활용됩니다.

## Home Assistant add-on

1. Home Assistant UI에서 **설정 → 애드온 → 저장소**로 이동하여 커스텀 저장소에
   `https://github.com/Kanu-Coffee/TEST`를 추가합니다.
2. **Bithumb/KIS Trading Bot** 애드온을 설치하고 구성 탭에서 안내 문구에 따라
   각 필드를 채웁니다 (필수/선택 여부가 UI에 표기됩니다).
3. 애드온을 시작하면 컨테이너가 코드를 클론하고 `python -m pip`으로 패키지를
   설치한 뒤 `python -m bot`과 FastAPI 게이트웨이를 실행합니다.
4. 로그 패널에서 `Installing Python dependencies` 이후 오류가 없는지 확인하고,
   필요 시 `http://homeassistant.local:6443`로 접속해 리포트/지표를 살펴보세요.

## Repository layout

```
bot/            → configuration dataclasses, strategy engine, metrics/log helpers
exchanges/      → exchange adapters (Bithumb, KIS)
tools/          → CLI wizard, report generator, FastAPI gateway
ha-addon/       → Home Assistant add-on definition (Dockerfile + scripts)
docs/           → reference documentation and strategy guides
```

## Useful commands

| 목적 | 명령 |
|------|------|
| 설정 확인 | `python tools/configure_bot.py --show` |
| 환경변수 즉시 수정 | `python tools/configure_bot.py --set KEY=VALUE` |
| 리포트 수동 생성 | `python tools/generate_report.py --output reports/custom.html` |
| 게이트웨이 실행 | `uvicorn tools.ha_gateway:app --host 0.0.0.0 --port 6443` |
| 코드 검사 | `python -m compileall bot tools exchanges` |

## Contributing

- 모든 작업은 `codex-dev` 브랜치에서 진행하고 자동 PR 워크플로우가 병합을 담당합니다.
- PR 설명에는 테스트 결과와 변경 요약을 포함하세요.
- 중복 코드나 사용하지 않는 파일이 보이면 정리해 주시면 감사하겠습니다.

---

*Happy trading, and always verify with small dry-run positions before exposing
real capital.*
