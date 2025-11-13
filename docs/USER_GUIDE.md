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
> 실제 자금으로 운용하기 전에 반드시 **充분한 백테스트와 드라이런(dry-run)** 으로 검증해 주세요.  
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
