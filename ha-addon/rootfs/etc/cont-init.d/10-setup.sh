#!/command/with-contenv bashio
set -euo pipefail

# --------------------------------------------------------------------
# 공통 PATH 설정 (s6 init path bug workaround)
# --------------------------------------------------------------------
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

# --------------------------------------------------------------------
# 애드온 옵션 로딩
# --------------------------------------------------------------------
REPO_URL="$(bashio::config 'repository_url')"
REPO_REF="$(bashio::config 'repository_ref')"
EXCHANGE="$(bashio::config 'exchange' | tr '[:lower:]' '[:upper:]')"
SYMBOL="$(bashio::config 'bot_symbol_ticker')"
ORDER_CCY="$(bashio::config 'bot_order_currency')"
PAY_CCY="$(bashio::config 'bot_payment_currency')"
DRY_RUN="$(bashio::config 'bot_dry_run')"
HF_MODE="$(bashio::config 'bot_hf_mode')"
BASE_RESET_MINUTES="$(bashio::config 'base_reset_minutes')"
DEFAULT_BASE="$(bashio::config 'default_base_order_value')"
DEFAULT_STEP="$(bashio::config 'default_buy_step')"
DEFAULT_MARTINGALE="$(bashio::config 'default_martingale_mul')"
DEFAULT_STEPS="$(bashio::config 'default_max_steps')"
HF_BASE="$(bashio::config 'hf_base_order_value')"
HF_STEP="$(bashio::config 'hf_buy_step')"

# Timezone 설정 (봇용 + 컨테이너용)
BOT_TZ="$(bashio::config 'bot_timezone' 'Asia/Seoul')"
SYS_TZ="$(bashio::config 'tz' "${BOT_TZ}")"
export TZ="${SYS_TZ}"

HF_MARTINGALE="$(bashio::config 'hf_martingale_mul')"
HF_STEPS="$(bashio::config 'hf_max_steps')"
BITHUMB_API_KEY="$(bashio::config 'bithumb_api_key')"
BITHUMB_API_SECRET="$(bashio::config 'bithumb_api_secret')"
KIS_APP_KEY="$(bashio::config 'kis_app_key')"
KIS_APP_SECRET="$(bashio::config 'kis_app_secret')"
KIS_ACCOUNT_NO="$(bashio::config 'kis_account_no')"
KIS_ACCOUNT_PASSWORD="$(bashio::config 'kis_account_password')"
KIS_MODE="$(bashio::config 'kis_mode' | tr '[:upper:]' '[:lower:]')"
KIS_EXCHANGE_CODE="$(bashio::config 'kis_exchange_code')"
KIS_SYMBOL="$(bashio::config 'kis_symbol')"
KIS_CURRENCY="$(bashio::config 'kis_currency')"
KIS_ORDER_LOT_SIZE="$(bashio::config 'kis_order_lot_size')"
ENABLE_GATEWAY="$(bashio::config 'enable_gateway')"
GATEWAY_PORT="$(bashio::config 'gateway_port')"
ENABLE_LOG_GATEWAY="$(bashio::config 'enable_log_gateway')"
TRADE_LOG_PORT="$(bashio::config 'trade_log_port')"
ERROR_LOG_PORT="$(bashio::config 'error_log_port')"

# --------------------------------------------------------------------
# sensible defaults
# --------------------------------------------------------------------
SYMBOL=${SYMBOL:-USDT_KRW}
ORDER_CCY=${ORDER_CCY:-USDT}
PAY_CCY=${PAY_CCY:-KRW}
DRY_RUN=${DRY_RUN:-true}
HF_MODE=${HF_MODE:-true}
BASE_RESET_MINUTES=${BASE_RESET_MINUTES:-15}
DEFAULT_BASE=${DEFAULT_BASE:-5000}
DEFAULT_STEP=${DEFAULT_STEP:-0.008}
DEFAULT_MARTINGALE=${DEFAULT_MARTINGALE:-1.5}
DEFAULT_STEPS=${DEFAULT_STEPS:-10}
HF_BASE=${HF_BASE:-5000}
HF_STEP=${HF_STEP:-0.005}
HF_MARTINGALE=${HF_MARTINGALE:-1.3}
HF_STEPS=${HF_STEPS:-10}
KIS_MODE=${KIS_MODE:-paper}
KIS_EXCHANGE_CODE=${KIS_EXCHANGE_CODE:-NASD}
KIS_SYMBOL=${KIS_SYMBOL:-TQQQ}
KIS_CURRENCY=${KIS_CURRENCY:-USD}
KIS_ORDER_LOT_SIZE=${KIS_ORDER_LOT_SIZE:-1.0}
GATEWAY_PORT=${GATEWAY_PORT:-6443}
TRADE_LOG_PORT=${TRADE_LOG_PORT:-6442}
ERROR_LOG_PORT=${ERROR_LOG_PORT:-6441}

# ensure PATH covers all base locations (s6 init path bug workaround)
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

# ⏰ NTP 시간 동기화 (Home Assistant 시간 드리프트 대응)
# 컨테이너 시작 시 강제 동기화
bashio::log.info "Syncing system time with NTP servers"
if command -v chronyc &>/dev/null; then
    chronyc makestep || true  # Chrony가 설치된 경우
elif command -v ntpdate &>/dev/null; then
    ntpdate -s pool.ntp.org || true  # ntpdate 사용
else
    # busybox/Alpine 기본 유틸 사용
    ntpd -q -n -p pool.ntp.org 2>/dev/null || true
fi

bashio::log.info "Preparing trading bot workspace"

# Ensure git is available (base 이미지를 재활용해도 안전하게 설치)
if ! command -v git >/dev/null 2>&1; then
    if command -v apk >/dev/null 2>&1; then
        bashio::log.warning "git not found, installing via apk"
        apk add --no-cache git || true
    elif command -v apt-get >/dev/null 2>&1; then
        bashio::log.warning "git not found, installing via apt-get"
        apt-get update && apt-get install -y git && apt-get clean && rm -rf /var/lib/apt/lists/* || true
    fi
fi

if ! command -v git >/dev/null 2>&1; then
    bashio::log.fatal "git command not available even after attempted installation"
    exit 1
fi

# clone or update repo
if [ -d "/opt/bot/.git" ]; then
    bashio::log.info "Updating existing repository in /opt/bot"
    git -C /opt/bot remote set-url origin "${REPO_URL}"
    git -C /opt/bot fetch --all --prune
else
    rm -rf /opt/bot
    git clone "${REPO_URL}" /opt/bot
fi

git -C /opt/bot checkout "${REPO_REF}"
git -C /opt/bot submodule update --init --recursive

# --------------------------------------------------------------------
# Python runtime 탐지
# --------------------------------------------------------------------
PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
    bashio::log.fatal "Python runtime not found in the container"
    exit 1
fi

# --------------------------------------------------------------------
# pip dependency 설치 (PEP 668-aware, 최초 1회만 pip 업그레이드)
# --------------------------------------------------------------------
if [ -f /opt/bot/requirements.txt ]; then
    bashio::log.info "Installing Python dependencies"

    # system env 설치 허용 (PEP 668 override)
    export PIP_BREAK_SYSTEM_PACKAGES=1

    # pip 명령어 결정 (모듈 방식 우선)
    PIP_CMD=()
    if "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
        PIP_CMD=("${PYTHON_BIN}" -m pip)
        bashio::log.info "Using Python module invocation for pip: ${PYTHON_BIN} -m pip"
    elif command -v pip3 >/dev/null 2>&1; then
        PIP_CMD=("$(command -v pip3)")
        bashio::log.warning "Using fallback pip3 executable: ${PIP_CMD[*]}"
    elif command -v pip >/dev/null 2>&1; then
        PIP_CMD=("$(command -v pip)")
        bashio::log.warning "Using fallback pip executable: ${PIP_CMD[*]}"
    else
        bashio::log.fatal "pip executable not found in PATH (${PATH}); aborting"
        exit 1
    fi

    # HAOS pip path issue용 심링크 (한 번만)
    if ! command -v pip >/dev/null 2>&1 && command -v pip3 >/dev/null 2>&1; then
        ln -sf "$(command -v pip3)" /usr/bin/pip || true
    fi

    # pip 업그레이드는 최초 1회만 수행하여 부팅시간 단축
    PIP_UPGRADE_FLAG="/data/bot/.pip_upgraded"
    mkdir -p "$(dirname "${PIP_UPGRADE_FLAG}")"

    if [ ! -f "${PIP_UPGRADE_FLAG}" ]; then
        if ! "${PIP_CMD[@]}" install --upgrade pip --break-system-packages; then
            bashio::log.warning "pip upgrade failed, continuing with existing version"
        else
            touch "${PIP_UPGRADE_FLAG}"
        fi
    else
        bashio::log.info "pip already upgraded previously, skipping upgrade step"
    fi

    # requirements 설치
    #  - --no-cache-dir 제거: 이미 설치된 패키지는 캐시 및 기존 설치를 활용해 빠르게 종료
    "${PIP_CMD[@]}" install --break-system-packages -r /opt/bot/requirements.txt
fi

# --------------------------------------------------------------------
# Dry-run 및 키 검증
# --------------------------------------------------------------------
if bashio::var.true "${DRY_RUN}"; then
    bashio::log.notice "Dry-run mode is enabled. No live orders will be sent."
fi

if [[ "${EXCHANGE}" == "BITHUMB" ]]; then
    if [[ -z "${BITHUMB_API_KEY}" || -z "${BITHUMB_API_SECRET}" ]]; then
        if bashio::var.true "${DRY_RUN}"; then
            bashio::log.warning "Bithumb API credentials are empty. Live trading requires valid keys."
        else
            bashio::log.fatal "Bithumb API Key/Secret are required when exchange=BITHUMB."
            exit 1
        fi
    fi
elif [[ "${EXCHANGE}" == "KIS" ]]; then
    if [[ -z "${KIS_APP_KEY}" || -z "${KIS_APP_SECRET}" || -z "${KIS_ACCOUNT_NO}" ]]; then
        if bashio::var.true "${DRY_RUN}"; then
            bashio::log.warning "KIS credentials or account details are empty. Provide real values before going live."
        else
            bashio::log.fatal "KIS AppKey/AppSecret/Account number are required when exchange=KIS."
            exit 1
        fi
    fi
fi

# --------------------------------------------------------------------
# .env 생성
# --------------------------------------------------------------------
mkdir -p /data/bot
mkdir -p /config/bithumb-bot
ENV_FILE="/data/bot/.env"

{
    printf 'EXCHANGE=%s\n' "${EXCHANGE}"
    printf 'BOT_SYMBOL_TICKER=%s\n' "${SYMBOL}"
    printf 'BOT_ORDER_CURRENCY=%s\n' "${ORDER_CCY}"
    printf 'BOT_PAYMENT_CURRENCY=%s\n' "${PAY_CCY}"
    printf 'BOT_DRY_RUN=%s\n' "${DRY_RUN}"
    printf 'BOT_HF_MODE=%s\n' "${HF_MODE}"
    printf 'BASE_RESET_MINUTES=%s\n' "${BASE_RESET_MINUTES}"
    printf 'DEFAULT_BASE_ORDER_VALUE=%s\n' "${DEFAULT_BASE}"
    printf 'DEFAULT_BASE_KRW=%s\n' "${DEFAULT_BASE}"
    printf 'DEFAULT_BUY_STEP=%s\n' "${DEFAULT_STEP}"
    printf 'DEFAULT_MARTINGALE_MUL=%s\n' "${DEFAULT_MARTINGALE}"
    printf 'DEFAULT_MAX_STEPS=%s\n' "${DEFAULT_STEPS}"
    printf 'HF_BASE_ORDER_VALUE=%s\n' "${HF_BASE}"
    printf 'HF_BASE_KRW=%s\n' "${HF_BASE}"
    printf 'HF_BUY_STEP=%s\n' "${HF_STEP}"
    printf 'HF_MARTINGALE_MUL=%s\n' "${HF_MARTINGALE}"
    printf 'HF_MAX_STEPS=%s\n' "${HF_STEPS}"
    printf 'BITHUMB_API_KEY=%s\n' "${BITHUMB_API_KEY}"
    printf 'BITHUMB_API_SECRET=%s\n' "${BITHUMB_API_SECRET}"
    printf 'KIS_APP_KEY=%s\n' "${KIS_APP_KEY}"
    printf 'KIS_APP_SECRET=%s\n' "${KIS_APP_SECRET}"
    printf 'KIS_ACCOUNT_NO=%s\n' "${KIS_ACCOUNT_NO}"
    printf 'KIS_ACCOUNT_PASSWORD=%s\n' "${KIS_ACCOUNT_PASSWORD}"
    printf 'KIS_MODE=%s\n' "${KIS_MODE}"
    printf 'KIS_EXCHANGE_CODE=%s\n' "${KIS_EXCHANGE_CODE}"
    printf 'KIS_SYMBOL=%s\n' "${KIS_SYMBOL}"
    printf 'KIS_CURRENCY=%s\n' "${KIS_CURRENCY}"
    printf 'KIS_ORDER_LOT_SIZE=%s\n' "${KIS_ORDER_LOT_SIZE}"
    printf 'BOT_DATA_DIR=%s\n' "/config/bithumb-bot"
} > "${ENV_FILE}"

# --------------------------------------------------------------------
# Gateway 제어용 런타임 파일
# --------------------------------------------------------------------
echo "ENABLE_GATEWAY=${ENABLE_GATEWAY}" > /var/run/ha_bot_enable_gateway
echo "${GATEWAY_PORT}" > /var/run/ha_bot_gateway_port
echo "ENABLE_LOG_GATEWAY=${ENABLE_LOG_GATEWAY}" > /var/run/ha_bot_enable_log_gateway
echo "${TRADE_LOG_PORT}" > /var/run/ha_bot_trade_port
echo "${ERROR_LOG_PORT}" > /var/run/ha_bot_error_port

bashio::log.info "Environment prepared"
