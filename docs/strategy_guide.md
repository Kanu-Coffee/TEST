# Strategy & Environment Variable Guide

이 문서는 봇의 매수/매도 전략과 관련된 환경변수를 한눈에 살펴보기 위한
참고 자료입니다. 모든 값은 `.env` 또는 `config/bot_config.yaml`에서 관리할
수 있으며 `tools/configure_bot.py --wizard`가 기본 입력을 도와줍니다.

## 1. 전략 개요

- **그리드 기반 분할매수**: 기준가 대비 일정 비율(`*_BUY_STEP`)로 하락할
  때마다 포지션을 늘리는 구조입니다. 각 스텝은 물타기 배수
  (`*_MARTINGALE_MUL`)로 규모가 커집니다.
- **EWMA 변동성 추정**: 지수가중 이동분산을 통해 최근 변동성을 계산하고
  `TP/SL` 비율을 동적으로 조정합니다. 최소/최대 변동성 범위는
  `VOL_MIN`, `VOL_MAX`로 제한합니다.
- **동적 익절·손절**: 변동성 기반 계수(`TP_K`, `SL_K`)와 바닥 값
  (`*_TAKE_PROFIT`, `*_STOP_LOSS`) 중 큰 값을 택해 목표 수익/손실 비율을
  정합니다.
- **주문 관리**: 분당 주문 수(`*_MAX_STEPS`) 및 주문 쿨다운
  (`ORDER_COOLDOWN`)을 통해 과도한 호출을 제한하고, 거래량 변화에 따라
  주문 취소 대기시간을 조절합니다.

## 2. 주요 환경변수 요약

| 변수 | 필수 | 설명 |
|------|------|------|
| `EXCHANGE` | ✅ | 사용할 거래소 (`BITHUMB` 또는 `KIS`). |
| `BOT_SYMBOL_TICKER` | ✅ | 조회 심볼. 빗썸은 `USDT_KRW` 형태, KIS는 종목코드(`TQQQ`). |
| `BOT_ORDER_CURRENCY` | ✅ | 주문 통화. 빗썸은 매수 자산, KIS는 종목 코드. |
| `BOT_PAYMENT_CURRENCY` | ✅ | 결제 통화. 빗썸은 `KRW`, KIS는 `USD`. |
| `BOT_DRY_RUN` | ✅ | `true`면 시뮬레이션, `false`면 실주문. |
| `BOT_HF_MODE` | ✅ | `true`면 HF 전략 세트를 사용. |
| `TIMEZONE` | ⬜ | 로그 및 리포트 타임존 (기본 `Asia/Seoul`). |
| `REPORT_INTERVAL_MINUTES` | ⬜ | 자동 리포트 주기(분). |
| `LOG_LEVEL` | ⬜ | `INFO`, `DEBUG`, `WARNING` 등.

### 빗썸 인증

| 변수 | 필수 조건 |
|------|-----------|
| `BITHUMB_API_KEY` | 실거래(`BOT_DRY_RUN=false`)에서 필수 |
| `BITHUMB_API_SECRET` | 실거래에서 필수 |

### KIS 인증

| 변수 | 필수 조건 |
|------|-----------|
| `KIS_APP_KEY` | KIS 사용 시 필수 |
| `KIS_APP_SECRET` | KIS 사용 시 필수 |
| `KIS_ACCOUNT_NO` | KIS 사용 시 필수 |
| `KIS_ACCOUNT_PASSWORD` | 실거래 시 필수 (모의투자에서는 빈 값 가능) |
| `KIS_MODE` | `paper`(모의) 또는 `live`(실전) |
| `KIS_EXCHANGE_CODE` | 거래소 코드 (예: `NASD`) |
| `KIS_SYMBOL` | 종목 코드 (예: `TQQQ`) |
| `KIS_ORDER_LOT_SIZE` | 최소 주문 주식 수 |

### 전략 파라미터 (DEFAULT/HF 공통 구조)

각 접두사는 `DEFAULT` 또는 `HF`로 구분됩니다. HF 모드가 활성화되면 HF 값을
사용하며, 비활성화 시 DEFAULT 값이 적용됩니다.

| 변수 | 설명 |
|------|------|
| `*_BASE_ORDER_VALUE` | 첫 스텝 주문 금액 (KRW 또는 USD 기준). |
| `*_BUY_STEP` | 기준가 대비 매수 진입 간격 (비율). |
| `*_MARTINGALE_MUL` 또는 `*_STEP_MULTIPLIER` | 스텝별 주문 금액 증가 배수. |
| `*_MAX_STEPS` | 최대 스텝 수. |
| `*_TAKE_PROFIT` | 최소 익절 비율 (TP 바닥). |
| `*_STOP_LOSS` | 최대 손절 비율 (SL 바닥). |
| `*_TP_MULTIPLIER` (`TP_K`) | 변동성 대비 TP 계수. |
| `*_SL_MULTIPLIER` (`SL_K`) | 변동성 대비 SL 계수. |
| `*_VOL_HALFLIFE` | EWMA 반감기(초). |
| `*_VOL_MIN`, `*_VOL_MAX` | 변동성 하한/상한. |
| `*_SLEEP_SECONDS` | 루프 대기 시간. |
| `*_ORDER_COOLDOWN` | 주문 간 최소 간격(초). |
| `*_MAX_ORDERS_PER_MINUTE` (`MAX_ORDERS_MIN`) | 분당 주문 제한. |
| `*_CANCEL_BASE_WAIT` | 기본 주문 취소 대기시간(초). |
| `*_CANCEL_MIN_WAIT`, `*_CANCEL_MAX_WAIT` | 취소 대기시간 범위. |
| `*_CANCEL_VOL_SCALE` | 24h 거래량 스케일링 기준.

### 보고 & 메트릭

| 변수 | 설명 |
|------|------|
| `REPORT_AUTO_GENERATE` | `true`면 게이트웨이가 주기적으로 리포트 생성. |
| `REPORT_SERVE` | `false`면 `/report` 엔드포인트 비활성화. |
| `REPORT_OUTPUT_PATH` | HTML 리포트 저장 경로. |
| `REST_API_ENABLED` | `/metrics` 엔드포인트 활성화 여부. |
| `METRICS_FILE` | 메트릭 JSON 파일명. |
| `MQTT_ENABLED` | MQTT 퍼블리셔 사용 여부. |
| `MQTT_HOST`, `MQTT_PORT` | MQTT 브로커 주소. |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | MQTT 인증 정보. |
| `MQTT_BASE_TOPIC` | 메트릭 게시 토픽 접두사. |

## 3. 전략 튜닝 팁

1. **드라이런으로 검증**: `BOT_DRY_RUN=true` 상태에서 최소 24시간 정도
   실행하면서 로그 및 HTML 리포트를 확인하세요.
2. **스텝 조정**: HF 모드에서 스텝 간격(`HF_BUY_STEP`)을 줄이면 체결은 늘지만
   평균 매입가가 빠르게 낮아집니다. 자금 계획에 맞춰 `HF_BASE_ORDER_VALUE`
   와 함께 조정하세요.
3. **익절/손절 균형**: 변동성이 낮은 장에서는 `*_TAKE_PROFIT` 값을 줄이고
   `*_TP_MULTIPLIER`를 크게 설정하면 잦은 익절을 기대할 수 있습니다.
4. **KIS 주문 단위**: 주식은 최소 1주 단위이므로 `KIS_ORDER_LOT_SIZE`를
   종목에 맞춰 설정해야 합니다. 주문 금액이 너무 작으면 최소 수량을 충족하지
   못해 주문이 거절됩니다.
5. **Home Assistant 모니터링**: 게이트웨이를 켠 상태라면 `http://<호스트>:6443`
   에 접속해 환경변수를 바로 수정하고 `/metrics`로 상태를 확인할 수 있습니다.

---

추가 질문이나 개선 제안은 `docs/overview.md`의 흐름을 참고하거나 GitHub
이슈에 남겨주세요.
