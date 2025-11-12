# [Feature Request] Multi-Exchange Support (Bithumb / Korea Investment & Securities OpenAPI)

## 🧩 Summary
현재 봇은 빗썸(Bithumb) API에 종속되어 있지만, 전략 구조(그리드, 레벨 간격, 드라이런, 리포트 생성 등)는 거래소에 의존하지 않는 형태로 설계되어 있습니다.  
따라서 **거래소 인터페이스를 분리**하고, **환경변수 기반으로 선택적으로 로드**할 수 있도록 확장하면  
같은 프로그램으로 빗썸뿐 아니라 **한국투자증권(Korea Investment & Securities, 이하 KIS)** 의 OpenAPI를 통한 해외주식 매매(TQQQ 등)도 실행할 수 있습니다.

이 방식은 Home Assistant Add-on 환경에서도 동일하게 적용 가능하며,  
두 개의 인스턴스를 띄워 각각 **빗썸용** / **KIS용**으로 병렬 구동하는 구조도 가능합니다.

---

## 🚀 제안 기능

### 1️⃣ 거래소 선택 환경변수 추가
- `.env` 또는 Home Assistant Add-on 옵션에서 거래소를 선택하도록 구성:

  ```bash
  EXCHANGE=BITHUMB   # 기존 방식
  # or
  EXCHANGE=KIS       # 한국투자증권 OpenAPI 사용
  ```
- 프로그램 구동 시 `EXCHANGE` 값에 따라 다른 클라이언트를 로드:

  ```python
  if os.getenv("EXCHANGE") == "KIS":
      from exchanges.kis import KisOverseasExchange as Exchange
  else:
      from exchanges.bithumb import BithumbExchange as Exchange
  ```
- 이렇게 하면 코드 수정 없이 환경변수만으로 거래소를 전환할 수 있습니다.
- Home Assistant에서도 Add-on을 두 번 설치해 각각 다른 거래소로 설정하면 완전히 독립적으로 동작합니다.

---

### 2️⃣ KIS 어댑터(`KisOverseasExchange`) 구현

참조: Korea Investment & Securities OpenAPI 문서

| 기능 | KIS API 경로 | 비고 |
|:---|:---|:---|
| 현재가 조회 | `/uapi/overseas-price/v1/quotations/price` | REST 또는 WebSocket 사용 |
| 주문 실행 | `/uapi/overseas-stock/v1/trading/order` | `X-HashKey`, `TR_ID`, 토큰 인증 필요 |
| 주문 취소 | `/uapi/overseas-stock/v1/trading/order-cancel` | 선택 기능 |
| 잔고 조회 | `/uapi/overseas-stock/v1/trading/inquire-balance` | 현재 보유 종목 조회 |
| 미체결 조회 | `/uapi/overseas-stock/v1/trading/inquire-nccs` | 미체결 주문 조회 |
| 인증 | `/oauth2/token` | AppKey, AppSecret 기반 액세스 토큰 발급 |
| 해시키 생성 | `/uapi/hashkey` | 주문 시 본문 데이터 해시용 |

KIS는 REST 방식으로 제공되며, `TR_ID`, `AppKey`/`AppSecret`, `Access Token`, `HashKey` 등을 헤더에 포함해야 합니다.  
또한 모의투자(`openapivts.koreainvestment.com:29443`)와 실전(`openapi.koreainvestment.com:9443`)은 별도 도메인으로 운영됩니다.

---

### 3️⃣ 환경변수 구성 예시

```bash
EXCHANGE=KIS
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678
KIS_MODE=paper        # paper(모의) 또는 live(실전)
KIS_EXCHANGE_CODE=NASD
KIS_SYMBOL=TQQQ
```

이와 별도로 기존 전략 관련 변수는 동일하게 유지합니다:

```bash
GRID_STEPS=20
GRID_GAP_PCT=0.15
ORDER_SIZE=5
BOT_DRY_RUN=true
```

---

### 4️⃣ 프로그램 구조 개선 제안

1. `exchanges/` 디렉토리 생성
   - `bithumb_exchange.py`
   - `kis_exchange.py`
2. `Exchange` 인터페이스 정의

   ```python
   class Exchange:
       def get_quote(self, symbol): ...
       def place_order(self, symbol, side, qty, price=None, order_type="limit"): ...
       def get_balance(self): ...
       def cancel_order(self, order_id): ...
   ```

3. `main.py` 또는 `bot_launcher.py`에서 `EXCHANGE` 환경변수에 따라 해당 클래스 로드
4. `tools/configure_bot.py`에서 `EXCHANGE` 선택 메뉴 추가 (Bithumb / KIS 중 선택)

이 구조를 통해 거래소를 자유롭게 교체할 수 있으며, 코드 중복 없이 확장 가능합니다.

---

### 5️⃣ Home Assistant Add-on 병렬 운용

- 동일한 이미지를 이용해 Add-on을 두 번 설치:
  - `bithumb_bot`: `EXCHANGE=BITHUMB`
  - `kis_bot`: `EXCHANGE=KIS`
- 각 컨테이너가 독립적으로 실행되며, 리포트 파일도 분리:

  ```
  reports/bithumb_report.html
  reports/kis_report.html
  ```

- MQTT 또는 REST 센서를 활용해 Home Assistant 대시보드에서 각각의 손익, 거래 횟수, 상태를 모니터링 가능:

  ```
  mqtt topics:
    bithumb_bot/pnl
    kis_bot/pnl
  ```

---

### 6️⃣ 주기적 리포트 생성 및 브로드캐스트

- 현재 `generate_report.py`를 수동으로 실행해야 하지만, 주기적으로 자동 실행하는 옵션 추가:
  - 일정 주기(`REPORT_INTERVAL_MINUTES`)마다 자동으로 리포트 생성
  - 각 인스턴스가 별도의 리포트를 생성하여 HA 대시보드에서 접근 가능
  - 리포트 결과 요약(PnL, 체결 수, 주문 수 등)을 MQTT 또는 REST API로 브로드캐스트하여 실시간 대시보드 구성:

    ```
    bithumb_bot/report/summary
    kis_bot/report/summary
    ```

---

### 7️⃣ 기대효과

| 항목 | 설명 |
|:---|:---|
| 하나의 프레임워크로 국내외 시장 대응 가능 | 가상자산(빗썸) + 해외주식(KIS)을 하나의 전략 기반으로 통합 |
| 운영 유연성 극대화 | 환경변수만 변경해 거래소 전환 가능 |
| HA Add-on 병렬 실행 | 동일한 컨테이너 이미지를 두 개 띄워 서로 다른 거래소로 운영 가능 |
| 코드 일관성 유지 | 전략 로직과 시각화, 리포트 구조는 동일하게 유지 |
| 유저 확장성 향상 | 기존 빗썸 사용자뿐 아니라 증권사 API 사용자도 참여 가능 |
| 운영자동화 | HA 환경에서 봇 상태 모니터링 및 자동 재시작, 리포트 생성 가능 |

---

### 8️⃣ 구현 제안 요약

| 항목 | 설명 |
|:---|:---|
| 인터페이스 통합 | `Exchange` 추상화 클래스 도입 |
| 환경변수 기반 선택 | `EXCHANGE=BITHUMB` 또는 `KIS` |
| 신규 KIS 어댑터 | 한국투자증권 해외주식 API 연동 |
| 인증 지원 | OAuth2 + HashKey 생성 |
| 리포트 통합 | 동일한 구조로 보고서 생성 (거래소별 별도 파일) |
| HA 병렬 운영 | 두 Add-on으로 독립 실행 가능 |
| MQTT/REST 브로드캐스트 | Home Assistant 대시보드 실시간 표시 |
| 주기적 리포트 자동화 | 일정 간격으로 자동 보고서 생성 기능 추가 |

---

## ⚙️ Environment
- Base: Python 3.11
- Platform: Home Assistant Supervised / Docker
- Current Repo: `Kanu-Coffee/TEST`
- Target API: Korea Investment & Securities OpenAPI

---

## 🗣️ Additional Context

이 제안은 단순히 거래소 추가를 넘어서,  
전략 로직과 거래소 인터페이스를 완전히 분리해 확장 가능한 트레이딩 엔진으로 발전시키기 위한 구조적 개선안입니다.

이를 통해 다음과 같은 응용이 가능합니다:
- 하나의 Home Assistant에서 빗썸/한투 두 거래소를 동시에 돌리며 성능 비교
- 두 봇의 손익 리포트를 자동 생성 및 대시보드 표시
- 향후 업비트, NH, 미래에셋, KB증권 등으로 손쉬운 확장

이 프로젝트가 “멀티 브로커 자동매매 프레임워크”로 성장할 수 있도록 구조 개선을 제안드립니다.

---

> 특히 주식거래는 코인거래와 달리 주문이 금액단위가 아니라 1주 단위로 이루어지는 점에 유의하세요.
