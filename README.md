# TEST – Bithumb / KIS Grid Trading Bot

> **Python + Home Assistant 통합용 그리드 트레이딩 봇**  
> Bithumb (코인) 과 KIS(한국투자증권, 미국 주식) 을 지원하는 자동 매매 실험 프로젝트입니다.

---

## ✨ Features

- 🧩 **Grid / DCA Strategy**
  - 분할 매수 + 마팅게일 배수
  - 변동성(EWMA) 기반 TP/SL 조정
- 🌐 **Multi-Exchange**
  - `BITHUMB` – 코인 현물 (예: USDT_KRW, BTC_KRW)
  - `KIS` – 미국 주식/ETF (예: TQQQ)
- 🔁 **Bithumb API Failover**
  - 레거시 v1.2.0 엔드포인트와 v2.1.0 REST 엔드포인트를 자동 페일오버
  - HTTP 4xx/5xx 또는 서명 오류가 발생하면 즉시 대체 경로로 재시도
- 🏠 **Home Assistant Add-on**
  - 애드온으로 설치 후 UI에서 파라미터 설정
  - 포트 `6443` 의 웹 게이트웨이 제공 (선택)
- 📊 **Logging & Metrics**
  - CSV 트레이드 로그 / 일별 실현손익 집계
  - HA 대시보드에서 가격, 포지션, PnL 등 모니터링
- 🧪 **Dry-run 모드**
  - 실제 주문 없이 전략 검증 가능

> ⚠️ **DISCLAIMER**  
> 이 저장소는 개인 연구/실험 목적입니다.  
> 실제 자금 운용 전 **충분한 테스트와 리스크 검토**를 반드시 수행하세요.  
> 모든 책임은 사용자에게 있습니다.

---

## 🧱 Project Structure

```text
bot/                # 전략, 설정, 러너
  ├─ config.py      # BotConfig & StrategyBand
  ├─ strategy.py    # GridStrategy
  ├─ runner.py      # main entrypoint
  └─ ...
exchanges/          # 거래소 추상화 (Bithumb, KIS)
config/
  ├─ bot_config.example.yaml
  └─ bot_config.yaml (optional, user-defined)
ha-addon/           # Home Assistant add-on definition
tools/
  └─ ha_gateway.py  # REST gateway (port 6443)
```

---

## 🚀 Quick Start (Python)

```bash
git clone https://github.com/Kanu-Coffee/TEST.git
cd TEST

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

1. 설정 파일 복사

```bash
cp config/bot_config.example.yaml config/bot_config.yaml
```

2. `config/bot_config.yaml` 열고:

   - `exchange`, `symbol_ticker`
   - `bithumb.api_key`, `bithumb.api_secret` 또는 KIS 키
   - 전략 관련 파라미터 (`buy_step`, `max_steps`, `martingale_multiplier` 등)
   - 필요하면 `base_reset_minutes` (예: 15분 기본값)
   - Bithumb API 페일오버 설정 (`bithumb.prefer_rest`, `bithumb.enable_failover`)
   - 주문 실패 일시정지 조정 (`strategy.*.failure_pause_seconds`, `failure_pause_backoff` 등)

3. dry-run 으로 실행

```bash
python -m bot.runner
```

4. 충분히 검증 후 `dry_run: false` 로 실제 주문 모드 전환

---

## 🏠 Home Assistant Add-on 사용법

1. Home Assistant → **설정 → 애드온 → 애드온 스토어**
2. 우측 상단 메뉴(⁝) → **저장소** → 아래 URL 추가:

   ```text
   https://github.com/Kanu-Coffee/TEST.git
   ```

3. `Bithumb/KIS Trading Bot` 애드온 설치 후:
   - 옵션에서 거래소, 심볼, API 키, 전략 파라미터 입력
   - 필요 시 `enable_gateway: true` 로 설정 (포트 6443)
4. 애드온 시작 후 로그에서:
   - `Environment prepared`
   - `Starting trading bot`
   - 체결/상태 로그를 확인

웹 게이트웨이를 켰다면:

```text
http://<HA_LOCAL_IP>:6443/
```

에서 설정 페이지를 열 수 있습니다 (역방향 프록시 사용 시 해당 도메인:포트로 프록시).

---

## ⚙️ Key Configuration (요약)

- **일반**

  - `exchange`: `BITHUMB` | `KIS`
  - `symbol_ticker`: 예) `USDT_KRW`, `BTC_KRW`, `TQQQ`
  - `dry_run`: `true` → 시뮬레이션, `false` → 실매매
  - `hf_mode`: `true` → 고빈도 파라미터 사용

- **전략 파라미터 (StrategyBand)**

  - `buy_step`: 그리드 간격 비율
  - `martingale_multiplier`: 분할 매수 시 주문 금액 배수
  - `max_steps`: 최대 그리드 개수
  - `base_order_value`: 첫 주문 기준금액
  - `tp_multiplier`, `sl_multiplier`, `tp_floor`, `sl_floor`
  - `vol_halflife`, `vol_min`, `vol_max`
  - `sleep_seconds`, `order_cooldown`, `max_orders_per_minute`
  - `cancel_*`: 미체결 주문 취소 타이밍 제어
  - `failure_pause_seconds`, `failure_pause_backoff`, `failure_pause_max`: 주문 실패 시 자동 일시정지 백오프
  - `post_fill_pause_seconds`: 체결 후 잠깐 쉬어가기

- **기준가 리셋**

  - `base_reset_minutes`
    - N분 동안 기준가가 변하지 않으면 현재가로 자동 리셋 (기본 15분)
    - 환경변수: `BASE_RESET_MINUTES` (또는 `BOT_BASE_RESET_MINUTES`), 기존 `BASE_RESET_HOURS`도 지원

- **Bithumb API 페일오버**

  - `bithumb.rest_*_endpoint`: v2.1.0 REST 경로 (기본 제공값 사용 가능)
  - `bithumb.prefer_rest`: `true` → REST 우선, `false` → 레거시 우선
  - `bithumb.enable_failover`: `true` 면 실패 시 다른 버전으로 자동 재시도
  - `bithumb.rest_symbol_dash/rest_symbol_upper`: 심볼 표기 형태 조정

- **Bithumb API 페일오버**

  - `bithumb.rest_*_endpoint`: v2.1.0 REST 경로 (기본 제공값 사용 가능)
  - `bithumb.prefer_rest`: `true` → REST 우선, `false` → 레거시 우선
  - `bithumb.enable_failover`: `true` 면 실패 시 다른 버전으로 자동 재시도
  - `bithumb.rest_symbol_dash/rest_symbol_upper`: 심볼 표기 형태 조정

자세한 설명은 `docs/USER_GUIDE.md` 를 참고하세요.

---

## 📂 Logs & Data

기본적으로 프로젝트 또는 HA 애드온의 `/data` 경로에 생성됩니다.

- 기본 위치: **`/config/bithumb-bot/`** (HA 파일 편집기에서 바로 열 수 있음)
- `bithumb_trades.csv`
- `bithumb_daily_summary.csv`
- `bithumb_errors.log`
- (KIS 사용 시 `kis_*` 파일들)

웹 보기 전용 게이트웨이도 추가되었습니다.

- `http://<HA_LOCAL_IP>:6442/` → 최근 거래 로그
- `http://<HA_LOCAL_IP>:6441/` → 에러 로그 및 에러 코드 확인

---

## 🙋‍♂️ 기여 & 이슈

- 버그 제보, 기능 제안, PR 모두 환영합니다.  
- 멀티 거래소 확장, 더 똑똑한 리스크 관리, 시각화 강화 등이 향후 계획입니다.

---

## ⚠️ Disclaimer (EN)

This project is an **experimental trading bot**.  
It comes with **no warranty** of profitability or correctness.

Use it **at your own risk**:

- Always start with `dry_run: true`.
- Backtest and paper trade first.
- Never risk money you cannot afford to lose.
