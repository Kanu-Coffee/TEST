# TEST Trading Bot 사용자 가이드

> Bithumb / KIS(한국투자증권) 멀티 거래소 지원 그리드 트레이딩 봇  
> Python 단독 실행 또는 Home Assistant 애드온으로 사용할 수 있습니다.

---

## 1. 개요

### 1.1 이 저장소가 하는 일

이 프로젝트는 다음을 목표로 하는 **그리드 기반 알고리즘 트레이딩 봇**입니다.

- Bithumb 선/현물(현재는 USDT_KRW, BTC_KRW 위주) 자동 매매
- KIS(한국투자증권) 미국 주식(예: TQQQ) 자동 매매
- **분할매수 + 그리드 전략**으로 횡보장에서 수익 추구
- 변동성(EWMA) 기반의 동적 TP/SL(익절/손절) 설정
- Home Assistant와 연동해:
  - 실시간 상태/지표를 대시보드에서 확인
  - 웹 UI에서 전략 파라미터를 실시간 수정

> ⚠️ **중요 경고**  
> 이 코드는 개인 실험용 / 교육용 예제에 가깝습니다.  
> 실제 자금으로 운용하기 전에 반드시 **충분한 백테스트와 드라이런(dry-run)** 으로 검증해 주세요.  
> 손실은 전적으로 사용자 책임입니다.

---

## 2. 전체 구조

### 2.1 디렉터리 구조 (요약)

```text
.
├── bot/                    # 봇 코어 로직
│   ├── bithumb_bot.py      # (구) 바이낸리용 러너 - 레거시, 참고용
│   ├── config.py           # 설정 로딩 / dataclass 정의
│   ├── home_assistant.py   # HA로 메트릭 전송
│   ├── logs.py             # CSV/텍스트 로그
│   ├── metrics.py          # 메트릭 퍼블리셔
│   ├── runner.py           # 새로운 엔트리포인트
│   └── strategy.py         # GridStrategy (구동 전략)
├── exchanges/              # 거래소 추상화
│   ├── base.py             # Exchange 인터페이스 / 공통 유틸
│   ├── bithumb.py          # Bithumb 구현
│   └── kis.py              # KIS 구현
├── config/
│   ├── bot_config.example.yaml   # 예시 설정
│   └── ... (선택) bot_config.yaml
├── ha-addon/               # Home Assistant 애드온 정의
├── tools/
│   ├── ha_gateway.py       # 포트 6443 REST 게이트웨이
│   └── ...                 # 기타 유틸
├── requirements.txt
└── README.md
```

---

## 3. 설정 시스템 전체 이해

### 3.1 설정 값 우선순위

`bot/config.py` 에 정의된 로딩 순서는 다음과 같습니다.

1. **환경변수 (`os.environ`)**
2. **프로젝트 루트의 `.env` 파일**
3. **`config/bot_config.yaml`** (있다면)

즉, 같은 항목이 여러 군데에 있을 때 **환경변수가 항상 최우선**입니다.  
Home Assistant 애드온의 옵션도 내부적으로 환경변수로 전달되므로, 역시 1번 우선순위를 가집니다.

---

## 4. 주요 설정 항목 (BotConfig)

### 4.1 Bot 전역 설정 (`bot` 섹션)

```yaml
bot:
  exchange: BITHUMB        # BITHUMB 또는 KIS
  symbol_ticker: USDT_KRW  # 예: USDT_KRW, BTC_KRW, TQQQ
  order_currency: USDT
  payment_currency: KRW
  dry_run: true
  hf_mode: true
  timezone: Asia/Seoul
  report_interval_minutes: 60
  log_level: INFO
  base_reset_minutes: 1440  # 선택: N분 동안 매수 없으면 기준가(base) 리셋
```

- **exchange**
  - `BITHUMB` : 빗썸 현물 / 코인
  - `KIS`     : 한국투자증권, 주식/ETF
- **dry_run**
  - `true`  : 주문은 시뮬레이션, 실제 주문 X
  - `false` : 실제 주문
- **hf_mode**
  - `true`  : 고빈도(HF) 밴드 파라미터 사용
  - `false` : 기본(default) 밴드 사용
- **base_reset_minutes**
  - 최근 **매수 체결이 없는 시간이 N분을 넘으면** 기준가(`base`) 를 현재 가격으로 재설정  
  - 장이 한 방향으로만 오래 가서 그리드가 전혀 체결되지 않는 상황 방지
  - 기본값 1440분 = 24시간  
  - 환경변수: `BASE_RESET_MINUTES` 또는 `BOT_BASE_RESET_MINUTES`

### 4.2 거래소별 인증 설정

#### 4.2.1 Bithumb

```yaml
bithumb:
  api_key: ""
  api_secret: ""
  base_url: https://api.bithumb.com
  rest_base_url: https://api.bithumb.com
  rest_place_endpoint: /api/v2/spot/trade/place
  rest_market_buy_endpoint: /api/v2/spot/trade/market_buy
  rest_market_sell_endpoint: /api/v2/spot/trade/market_sell
  prefer_rest: false
  enable_failover: true
  rest_symbol_dash: true
  rest_symbol_upper: true
  auth_mode: legacy    # 또는 jwt (추가 구현 시)
```

- `api_key`, `api_secret`
  - 빗썸 API 키
  - 환경변수: `BITHUMB_API_KEY`, `BITHUMB_API_SECRET`
- `prefer_rest`
  - `true` 로 설정하면 v2.1.0 REST → 레거시(v1.2.0) 순으로 주문 전송
  - `false` 이면 레거시 → REST 순
- `enable_failover`
  - `true` 일 때 첫 번째 경로가 4xx/5xx 로 실패하면 다른 버전으로 자동 재시도
- `rest_*_endpoint`
  - 빗썸 API 문서(https://apidocs.bithumb.com/) 기준 엔드포인트를 원하는 버전으로 교체 가능
- `rest_symbol_dash`, `rest_symbol_upper`
  - v2.1 심볼 포맷이 `BTC-KRW` 처럼 하이픈/대문자를 요구할 때 조정
- 주문 시그니처는 공식 문서처럼 **HMAC-SHA512 → hex → Base64** 순으로 계산합니다.
  봇이 millisecond nonce 를 자동 생성하지만, 동일 ms 내 다중 주문을 위해
  시스템 시간이 역행하지 않도록 NTP 동기화를 유지해 주세요.

#### 4.2.2 KIS (한국투자증권)

```yaml
kis:
  app_key: ""
  app_secret: ""
  account_no: ""
  account_password: ""
  mode: paper                # paper | live
  exchange_code: NASD        # 예: NASD, NYSE
  symbol: TQQQ
  currency: USD
  order_lot_size: 1.0
  base_url_paper: https://openapivts.koreainvestment.com:29443
  base_url_live:  https://openapi.koreainvestment.com:9443
```

- `mode`:
  - `paper` : 모의투자
  - `live`  : 실계좌

> ⚠️ KIS 실계좌 모드는 API 제한, 체결 규칙 등 제약이 많으므로  
> 충분한 모의 테스트 후에만 사용하세요.

---

## 5. 전략 파라미터 (StrategyBand)

전략은 **두 개의 밴드**로 정의됩니다.

- `strategy.default`           – 일반 모드
- `strategy.high_frequency`    – HF 모드 (`bot.hf_mode: true` 일 때 사용)

각 밴드에는 다음과 같은 필드가 있습니다.

```yaml
strategy:
  default:
    buy_step: 0.008
    martingale_multiplier: 1.5
    max_steps: 10
    base_order_value: 5000
    tp_multiplier: 0.55
    sl_multiplier: 1.25
    tp_floor: 0.003
    sl_floor: 0.007
    vol_halflife: 60
    vol_min: 0.001
    vol_max: 0.015
    sleep_seconds: 2.0
    order_cooldown: 6.0
    max_orders_per_minute: 6
    cancel_base_wait: 10.0
    cancel_min_wait: 5.0
    cancel_max_wait: 30.0
    cancel_volume_scale: 2000.0
    failure_pause_seconds: 10.0
    failure_pause_backoff: 2.0
    failure_pause_max: 180.0
    post_fill_pause_seconds: 3.0

  high_frequency:
    buy_step: 0.005
    martingale_multiplier: 1.3
    max_steps: 10
    base_order_value: 5000
    # 나머지 필드는 default 와 유사, 필요시 튜닝
```

### 5.1 매수 관련

- **buy_step**
  - 그리드 간격 (비율)
  - 예: `buy_step=0.005`, `base=1500` 이면  
    - 1차 매수 트리거: `1500 * (1 - 0.005) = 1492.5`  
    - 2차: `1500 * (1 - 0.010) = 1485`  
    - ...
- **martingale_multiplier**
  - 아래로 내려갈수록 주문 금액을 곱해가는 배수
  - 예: `1.3`, `base_order_value=5000` 이면
    - 1차 5,000원
    - 2차 6,500원
    - 3차 8,450원 …

- **max_steps**
  - 최대 몇 번까지 아래로 깔 것인지

- **base_order_value**
  - 첫 매수 주문의 KRW 기준 금액 (혹은 USD 등)

### 5.2 TP / SL & 변동성

`EWMA` 기반으로 24h 변동성을 추정한 뒤:

```python
tp = max(tp_floor,  vol * tp_multiplier)
sl = max(sl_floor,  vol * sl_multiplier)
```

- `tp_floor`, `sl_floor`: 최소 익절/손절 한계
- `tp_multiplier`, `sl_multiplier`: 변동성에 곱해지는 계수

### 5.3 주문 실패 백오프 & 휴지기

- **failure_pause_seconds**
  - 첫 번째 매수 실패 후 잠시 멈추는 시간(초)
- **failure_pause_backoff**
  - 같은 이유로 연속 실패하면 대기 시간을 곱해감 (예: 10s → 20s → 40s)
- **failure_pause_max**
  - 백오프로 늘어나더라도 이 값을 넘지 않도록 제한
- **post_fill_pause_seconds**
  - 주문이 체결된 직후 잠깐 쉬어 가격이 튀는 구간에서 과도한 재진입을 방지
- 위 값들은 HF/기본 밴드별로 각각 설정 가능 (`strategy.default.*`, `strategy.high_frequency.*`)

예:  
- `vol ≈ 0.0045 (0.45%)`, `tp_multiplier=0.8`, `tp_floor=0.0015`  
  → `TP ≈ max(0.15%, 0.36%) = 0.36%`

즉 **각 포지션별 개별 진입가 기준으로 ±TP/SL 비율**에 도달하면 매도 시도.

### 5.3 주문 빈도 제한 & 취소

- `order_cooldown`  
  - 마지막 주문 이후 최소 대기 시간(초)
- `max_orders_per_minute`  
  - 1분 동안 허용되는 최대 주문 수

- `cancel_base_wait`, `cancel_min_wait`, `cancel_max_wait`, `cancel_volume_scale`  
  - 24h 거래량을 기준으로 **시장 유동성에 따라 주문 유지/취소까지 기다리는 시간을 동적으로 조정**

---

## 6. GridStrategy 동작 요약

### 6.1 기준가(base)와 그리드

1. 봇 시작 시, 첫 시세를 `base` 로 잡음.
2. **포지션이 전혀 없을 때는 `base` 를 유지** (계속 위에 있어도 그대로).
3. 포지션이 생기면:
   - 모든 포지션의 가중 평균가 `avg_price` 계산
   - `base = min(base, avg_price)`  
     → 평단이 내려갈수록 기준가도 함께 내려가지만, 평단이 올라가면 기준가는 그대로여서  
       그리드가 위로 따라 올라가 **추격 매수**는 하지 않음.
4. `base_reset_minutes` 만큼 매수 체결이 없다면  
   - `base` 를 현재 가격으로 다시 설정 → 새로운 구간에서 다시 그리드 구축

### 6.2 매수 조건

- `positions` 길이가 `max_steps` 미만  
- `can_order()` 가 `True` (쿨다운 및 분당 횟수 제한 통과)  
- 현재 가격 `price` 가 다음 트리거 `trigger = base * (1 - buy_step * (next_idx + 1))` 이하  

→ 시장가/지정가 매수 시도 후, 성공 시 포지션 리스트에 추가

### 6.3 매도 조건

각 포지션 `(bp, qty)` 에 대해:

- `change = (price - bp) / bp`  
- `change >= TP` → 익절  
- `change <= -SL` → 손절  

둘 중 하나 만족 + `can_order()` → 매도 주문

성공 시:

- 실현 손익 누적  
- 일별 통계 CSV 업데이트  
- 포지션 제거 / 남은 포지션 평균가 재계산  
- HA 메트릭 업데이트

---

## 7. 설치 및 실행

### 7.1 Python 단독 실행

1. 클론

```bash
git clone https://github.com/Kanu-Coffee/TEST.git
cd TEST
```

2. 가상환경 + 의존성

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. 설정 파일 준비

```bash
cp config/bot_config.example.yaml config/bot_config.yaml
# 편집기에서 본인 API 키 / 전략 파라미터 입력
```

4. 실행

```bash
python -m bot.runner
```

- `dry_run: true` 로 충분히 테스트 후 `false` 로 변경

### 7.2 Home Assistant 애드온으로 사용

1. Home Assistant → **설정 → 애드온 → 애드온 스토어 → 우측 상단 메뉴 → 저장소**  
2. 저장소 URL 추가:

   ```text
   https://github.com/Kanu-Coffee/TEST.git
   ```

3. `Bithumb/KIS Trading Bot` 애드온 설치  
4. 옵션에서:
   - `repository_url`, `repository_ref` (일반적으로 기본값 유지)
   - `exchange`, `bot_symbol_ticker`, 전략 파라미터, API 키 등 입력
   - `enable_gateway` 를 `true` 로 하면 `http://HA_IP:6443` 에서 웹 UI 접근 가능
5. 애드온 시작 후 로그에서:
   - `Environment prepared`
   - `Starting trading bot`
   - 체결 내역/상태 로그 확인

---

## 8. 로그 & 리포트

### 8.1 CSV/로그 파일

`/data` (또는 프로젝트 `data/`) 아래에 생성됩니다.

- `{exchange}_trades.csv`
  - 시간, 이벤트(BUY/SELL), 가격, 수량, 포지션, TP/SL, 메모
- `{exchange}_daily_summary.csv`
  - 일별 실현 손익, 거래 수, win/loss 횟수
- `{exchange}_errors.log`
  - 예외/오류 메시지

### 8.2 Home Assistant 메트릭

`HomeAssistantPublisher` 와 `ha_gateway` 를 통해:

- REST 엔드포인트로 현재 상태 JSON 제공
- HA 센서/차트에서 가격, 포지션, PnL, 최근 거래 등 확인 가능

---

## 9. 운용 팁 & 권장 설정

- **USDT_KRW** 같이 변동성이 낮은 코인:
  - `buy_step` 을 작게 (예: `0.0015 ~ 0.003`)
  - `max_steps` 를 더 크게 (예: `15~20`)
  - `martingale_multiplier` 는 너무 세게 올리지 말 것 (`1.2~1.3` 근처)
- **BTC_KRW** 같이 변동성이 큰 코인:
  - `buy_step` 을 크게 (`0.004 ~ 0.008`)
  - `max_steps` 는 자본 및 허용 리스크에 따라 조정
- **KIS 주식/ETF**:
  - 장 시간, 호가 규칙, 체결 속도가 다르므로  
    꼭 소액으로 충분히 테스트 후 실계좌 전환

---

## 10. 주의사항 & 면책 조항

- 이 코드는 개인 실험용 프로젝트입니다.
- 거래소 API 정책 변경, 레버리지, 슬리피지 등으로 **실제 결과는 시뮬레이션과 다를 수 있습니다.**
- 모든 매매에 따르는 **손실 및 리스크는 전적으로 사용자 본인 책임**입니다.
- 항상:
  - 드라이런(dry_run)으로 먼저 검증  
  - 소액으로 실험  
  - 충분한 기간 백테스트 수행 후 실전 투입을 추천합니다.
