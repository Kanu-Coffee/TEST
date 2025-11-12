# Split-Buy Bot Toolkit

This repository contains a high-frequency split-buy trading bot that now works
with multiple exchanges. The default setup targets the Bithumb USDT/KRW market,
while an optional adapter supports overseas equities via the Korea Investment &
Securities (KIS) OpenAPI. The toolkit also ships with analytics and
configuration helpers for long-running Home Assistant deployments.

## Features

- Multi-exchange core with adapters for Bithumb spot trading and KIS overseas
  equities (shares handled in whole-lot increments).
- High-frequency trading loop that adapts to market volatility using EWMA.
- CSV logging for fills, errors, and daily summaries in the `data/` directory
  (one set of files per exchange).
- Interactive HTML report generator powered by Chart.js (now scheduled and shareable).
- CLI helper to create or update either the `.env` file or a structured
  `config/bot_config.yaml`.
- FastAPI-based gateway that serves the latest HTML report, exposes a config
  web UI, and streams metrics for Home Assistant.
- Optional MQTT publisher and JSON metrics file (`data/ha_metrics.json`) for
  dashboards and automations.

## Getting started (English)

1. (Optional) Create a virtual environment and install dependencies if you plan
   to extend the project.
2. Install the required Python packages:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure credentials and runtime options:

   ```bash
   python tools/configure_bot.py
   ```

   - Choose the exchange (`BITHUMB` or `KIS`) when prompted and provide the
     corresponding credentials.
   - Use `--set KEY=VALUE` pairs for non-interactive updates.
   - To generate a YAML config with Home Assistant options, run
     `python tools/configure_bot.py --yaml` or copy
     `config/bot_config.example.yaml` to `config/bot_config.yaml` and edit it
     manually.
4. Run the bot (defaults to dry-run mode until disabled in the `.env` file):

   ```bash
   python -m bot.bithumb_bot
   ```

5. Generate an HTML performance report from the collected CSVs:

   ```bash
   python tools/generate_report.py
   ```

   The default output lives in `reports/latest.html`.

6. (Optional) Launch the Home Assistant gateway to auto-refresh reports and expose metrics:

   ```bash
   uvicorn tools.ha_gateway:app --host 0.0.0.0 --port 8080
   ```

   - Open `http://localhost:8080` to edit `config/bot_config.yaml` through a web form.
   - `GET /metrics` returns the latest JSON snapshot (`data/ha_metrics.json`) when `rest_api.enabled` is `true`.
   - `/generate-report` forces an immediate refresh and `/report` serves the latest Chart.js dashboard when
     `reporting.serve_report` is enabled.

## 빠르게 시작하기 (한국어)

> 아래 순서는 **초보자**도 그대로 따라 하면 되도록 단계별로 정리했습니다.

1. **파이썬 설치 확인**  
   Windows는 `cmd`, macOS/Linux는 터미널에서 다음 명령으로 버전을 확인합니다.

   ```bash
   python --version
   ```

   3.9 이상이면 됩니다. 없다면 [python.org](https://www.python.org/downloads/)에서 설치하세요.

2. **(선택) 가상환경 만들기**  
   프로젝트 폴더에서 실행합니다.

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows는 .venv\Scripts\activate
   ```

3. **필수 패키지 설치**

   ```bash
   pip install -r requirements.txt
   ```

4. **환경변수(.env) 설정**
   아래 명령을 실행하면 하나씩 질문이 나오니 순서대로 입력하세요.
   (이미 .env가 있다면 기존 값이 대괄호로 표시됩니다.)

   ```bash
   python tools/configure_bot.py
   ```

   - 첫 번째 질문에서 거래소(`BITHUMB` 또는 `KIS`)를 선택하고 해당 키를
     입력합니다.
   - 명령형으로 바로 넣고 싶다면 `python tools/configure_bot.py --set BOT_DRY_RUN=true` 처럼 사용합니다.
   - 홈어시스턴트 옵션까지 포함한 YAML 설정이 필요하면 `python tools/configure_bot.py --yaml`을 실행하거나
     `config/bot_config.example.yaml`을 복사해 `config/bot_config.yaml`으로 저장한 뒤 수정하세요.

5. **봇 실행 (기본은 연습 모드)**

   ```bash
   python -m bot.bithumb_bot
   ```

   - 터미널에 매수/매도 시도 로그가 출력됩니다.
   - `BOT_DRY_RUN`을 `false`로 바꾸기 전까지는 실제 주문이 나가지 않습니다.

6. **CSV 확인**  
   실행 후 `data/` 폴더에 CSV와 로그가 자동으로 쌓입니다.
   - `<exchange>_trades.csv`: 매수·매도 내역 (예: `bithumb_trades.csv`)
   - `<exchange>_daily_summary.csv`: 일별 실현손익
   - `<exchange>_errors.log`: 에러 메모

7. **리포트 HTML 만들기**

   ```bash
   python tools/generate_report.py
   ```

   실행이 끝나면 `reports/latest.html`이 생성됩니다. 브라우저로 열면 그래프를 볼 수 있습니다.

8. **문제가 생기면**
   - `data/bithumb_errors.log`를 확인해 원인을 찾습니다.
   - API 키나 비밀번호가 틀리면 `.env`를 다시 설정합니다.
   - 네트워크 오류는 잠시 뒤 다시 실행하세요.

9. **(선택) 홈어시스턴트 게이트웨이 실행**

   ```bash
   uvicorn tools.ha_gateway:app --host 0.0.0.0 --port 8080
   ```

   - `http://localhost:8080`에서 웹 폼으로 `config/bot_config.yaml`을 수정할 수 있습니다.
   - `rest_api.enabled`가 `true`이면 `/metrics`에서 JSON 지표(`data/ha_metrics.json`)를 가져올 수 있습니다.
   - `reporting.serve_report`가 `true`이면 `/report`에서 최신 HTML 리포트를 바로 확인하고, `/generate-report`로 즉시 갱신할 수 있습니다.

## Configuration

All runtime settings are loaded from environment variables. The most important
ones are listed below. Defaults mirror the HF-tuned parameters from the
original script.

| Variable | Description |
| --- | --- |
| `EXCHANGE` | Which adapter to use: `BITHUMB` or `KIS`. |
| `BITHUMB_API_KEY` / `BITHUMB_API_SECRET` | Bithumb credentials. |
| `BITHUMB_BASE_URL` / `BITHUMB_AUTH_MODE` | Advanced Bithumb settings. |
| `KIS_APP_KEY` / `KIS_APP_SECRET` | KIS OpenAPI credentials. |
| `KIS_ACCOUNT_NO` / `KIS_ACCOUNT_PASSWORD` | KIS account routing information. |
| `KIS_MODE` | `paper` (default) or `live`. |
| `KIS_SYMBOL` / `KIS_EXCHANGE_CODE` / `KIS_CURRENCY` | Overseas stock routing fields. |
| `KIS_ORDER_LOT_SIZE` | Minimum share lot (usually `1`). |
| `BOT_SYMBOL_TICKER` | Market ticker (Bithumb pair or reference symbol). |
| `BOT_ORDER_CURRENCY` / `BOT_PAYMENT_CURRENCY` | Used for Bithumb pairs. |
| `BOT_HF_MODE` / `BOT_DRY_RUN` | Toggle HF parameters and dry-run mode. |
| `DEFAULT_BASE_ORDER_VALUE` / `HF_BASE_ORDER_VALUE` | Base order sizing per mode (legacy `*_BASE_KRW` still works). |
| Other `DEFAULT_*` / `HF_*` | Override TP/SL, step size, cooldowns, etc. |

Any value left blank in `.env` falls back to the defaults baked into
`bot/config.py`.

## Requirements

Install project dependencies with:

```bash
pip install -r requirements.txt
```

## Data outputs

- `data/<exchange>_trades.csv` – detailed log of individual trades and order
  attempts (e.g. `data/bithumb_trades.csv` or `data/kis_trades.csv`).
- `data/<exchange>_daily_summary.csv` – aggregated daily performance statistics
  automatically updated on each filled sell order.
- `data/<exchange>_errors.log` – diagnostic information for unexpected errors.

These files power the HTML report generated via `tools/generate_report.py`.

## Home Assistant integration

### Custom add-on repository (전체 과정을 따라 하세요)

1. **애드온 저장소 추가** – Home Assistant 웹 UI에서 *설정 → 애드온 → 애드온 스토어*로 이동한 뒤 오른쪽 상단 메뉴에서 “저장소”를 선택하고 아래 주소를 붙여넣습니다.

   ```text
   https://github.com/Kanu-Coffee/TEST
   ```

   이제 “Bithumb/KIS Trading Bot” 애드온이 목록에 나타납니다.

2. **애드온 설치** – `Bithumb/KIS Trading Bot`을 선택해 설치합니다. 이 애드온은 저장소 루트의 `repository.yaml`과 `ha-addon/` 폴더(`config.yaml`, `Dockerfile`, `rootfs/`)를 사용합니다.

3. **옵션 설정** – 설치 후 “구성(Configure)” 화면에서 다음 항목을 입력합니다.

   | 항목 | 설명 |
   | --- | --- |
   | `repository_url` | 실행할 코드가 있는 Git 저장소 (기본값은 현재 프로젝트) |
   | `repository_ref` | 체크아웃할 브랜치 또는 태그 (`main` 등) |
   | `exchange` | 사용할 거래소 (`BITHUMB` 또는 `KIS`) |
   | `env_vars` | `.env`에 추가할 `KEY=VALUE` 목록 (예: `BITHUMB_API_KEY=abc123`) |
   | `enable_gateway` | `true`이면 내장 FastAPI 게이트웨이를 8080 포트에서 실행 |

   값을 저장하면 컨테이너가 `/data/bot/.env` 파일을 생성해 거래소별 설정을 기록합니다.

4. **애드온 시작** – “시작(Start)” 버튼을 누르면 컨테이너가 자동으로 아래 작업을 수행합니다.

   - `repository_url`과 `repository_ref`를 기준으로 코드를 `/opt/bot`에 클론하거나 업데이트합니다.
   - `requirements.txt`를 읽어 필요한 패키지를 설치합니다.
   - `/data/bot/.env`에 기록된 환경변수를 로드하고 `python -m bot.bithumb_bot`을 실행합니다.
   - `enable_gateway`가 `true`이면 `python -m tools.ha_gateway --host 0.0.0.0 --port 8080`을 함께 띄웁니다.

5. **리포트와 상태 확인** – 애드온 로그에서 봇 실행 상황을 확인하고, 게이트웨이를 켰다면 `http://homeassistant.local:8080/report`(또는 ingress)에서 HTML 리포트를 볼 수 있습니다. `/metrics`는 Home Assistant 센서 자동화에 활용할 수 있는 JSON 데이터를 제공합니다.

> 💡 **팁:** 애드온은 `/data`를 지속 저장소로 사용합니다. 필요 시 SSH 애드온이나 Samba를 통해 `config/bot_config.yaml`이나 CSV 로그를 직접 열어볼 수 있습니다.

### 직접 실행형 연동

- Run `uvicorn tools.ha_gateway:app --host 0.0.0.0 --port 8080` alongside the bot to:
  - auto-refresh the latest HTML report based on `home_assistant.reporting.interval_minutes`;
  - expose `/metrics`, `/generate-report`, `/report`, and `/config` endpoints for dashboards or automations;
  - edit `config/bot_config.yaml` through a simple web form (ingress friendly).
- The bot continuously writes a metrics snapshot to `data/ha_metrics.json`. MQTT publishing mirrors the same data to
  `<base_topic>/<metric>` topics when `home_assistant.mqtt.enabled` is true (default base topic: `bithumb_bot`).
- The full custom add-on is defined in `ha-addon/`, and the Supervisor metadata lives
  at the repository root (`repository.yaml`).
- Generated reports default to `reports/latest.html`; change `home_assistant.reporting.output_path` in YAML if you mount a
  different volume inside a container.

## Feature proposals

- 멀티 브로커 확장과 Home Assistant 병렬 운용 아이디어는 `docs/feature_request_multi_exchange.md`에서 자세히
  확인할 수 있습니다. 향후 거래소 인터페이스 분리를 진행할 때 참고 자료로 활용하세요.

## Disclaimer

This project is provided for educational purposes. Trading cryptocurrencies
involves significant financial risk. Always back-test thoroughly and start with
a dry-run before deploying with real funds.
