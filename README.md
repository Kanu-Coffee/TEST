# Bithumb Split-Buy Bot Toolkit

This repository contains a high-frequency split-buy trading bot tailored for the
Bithumb USDT/KRW market. It also provides tooling for analysing historical
trades and for managing configuration via environment variables.

## Features

- High-frequency trading loop that adapts to market volatility using EWMA.
- CSV logging for fills, errors, and daily summaries in the `data/` directory.
- Interactive HTML report generator powered by Chart.js.
- CLI helper to create or update the `.env` configuration file.
- Environment-driven configuration that separates credentials from code.

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

   Use `--set KEY=VALUE` pairs for non-interactive updates.
4. Run the bot (defaults to dry-run mode until disabled in the `.env` file):

   ```bash
   python -m bot.bithumb_bot
   ```

5. Generate an HTML performance report from the collected CSVs:

   ```bash
   python tools/generate_report.py
   ```

   The default output lives in `reports/bithumb_report.html`.

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

   - 명령형으로 바로 넣고 싶다면 `python tools/configure_bot.py --set BOT_DRY_RUN=true` 처럼 사용합니다.

5. **봇 실행 (기본은 연습 모드)**

   ```bash
   python -m bot.bithumb_bot
   ```

   - 터미널에 매수/매도 시도 로그가 출력됩니다.
   - `BOT_DRY_RUN`을 `false`로 바꾸기 전까지는 실제 주문이 나가지 않습니다.

6. **CSV 확인**  
   실행 후 `data/` 폴더에 CSV와 로그가 자동으로 쌓입니다.
   - `bithumb_trades.csv`: 매수·매도 내역
   - `bithumb_daily_summary.csv`: 일별 실현손익
   - `bithumb_errors.log`: 에러 메모

7. **리포트 HTML 만들기**

   ```bash
   python tools/generate_report.py
   ```

   실행이 끝나면 `reports/bithumb_report.html`이 생성됩니다. 브라우저로 열면 그래프를 볼 수 있습니다.

8. **문제가 생기면**  
   - `data/bithumb_errors.log`를 확인해 원인을 찾습니다.
   - API 키나 비밀번호가 틀리면 `.env`를 다시 설정합니다.
   - 네트워크 오류는 잠시 뒤 다시 실행하세요.

## Configuration

All runtime settings are loaded from environment variables. The most important
ones are listed below. Defaults mirror the HF-tuned parameters from the
original script.

| Variable | Description |
| --- | --- |
| `BITHUMB_API_KEY` / `BITHUMB_API_SECRET` | API credentials. |
| `BITHUMB_BASE_URL` | Bithumb REST API base URL. |
| `BITHUMB_AUTH_MODE` | `legacy` (default) or `jwt`. |
| `BOT_SYMBOL_TICKER` | Market ticker, e.g. `USDT_KRW`. |
| `BOT_ORDER_CURRENCY` / `BOT_PAYMENT_CURRENCY` | Trading pair symbols. |
| `BOT_HF_MODE` | Toggle high-frequency parameter set. |
| `BOT_DRY_RUN` | Keep orders local for testing. |
| `DEFAULT_*` / `HF_*` | Override strategy parameters (buy steps, TP/SL, etc.). |

Any value left blank in `.env` falls back to the defaults baked into
`bot/config.py`.

## Requirements

Install project dependencies with:

```bash
pip install -r requirements.txt
```

## Data outputs

- `data/bithumb_trades.csv` – detailed log of individual trades and order
  attempts.
- `data/bithumb_daily_summary.csv` – aggregated daily performance statistics
  automatically updated on each filled sell order.
- `data/bithumb_errors.log` – diagnostic information for unexpected errors.

These files power the HTML report generated via `tools/generate_report.py`.

## Disclaimer

This project is provided for educational purposes. Trading cryptocurrencies
involves significant financial risk. Always back-test thoroughly and start with
a dry-run before deploying with real funds.
