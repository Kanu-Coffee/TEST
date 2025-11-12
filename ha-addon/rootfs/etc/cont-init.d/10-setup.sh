#!/command/with-contenv bashio
set -euo pipefail

REPO_URL="$(bashio::config 'repository_url')"
REPO_REF="$(bashio::config 'repository_ref')"
EXCHANGE="$(bashio::config 'exchange' | tr '[:lower:]' '[:upper:]')"
SYMBOL="$(bashio::config 'bot_symbol_ticker')"
ORDER_CCY="$(bashio::config 'bot_order_currency')"
PAY_CCY="$(bashio::config 'bot_payment_currency')"
DRY_RUN="$(bashio::config 'bot_dry_run')"
HF_MODE="$(bashio::config 'bot_hf_mode')"
DEFAULT_BASE="$(bashio::config 'default_base_order_value')"
DEFAULT_STEP="$(bashio::config 'default_buy_step')"
DEFAULT_MARTINGALE="$(bashio::config 'default_martingale_mul')"
DEFAULT_STEPS="$(bashio::config 'default_max_steps')"
HF_BASE="$(bashio::config 'hf_base_order_value')"
HF_STEP="$(bashio::config 'hf_buy_step')"
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

SYMBOL=${SYMBOL:-USDT_KRW}
ORDER_CCY=${ORDER_CCY:-USDT}
PAY_CCY=${PAY_CCY:-KRW}
DRY_RUN=${DRY_RUN:-true}
HF_MODE=${HF_MODE:-true}
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

bashio::log.info "Preparing trading bot workspace"

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

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
    bashio::log.fatal "Python runtime not found in the container"
    exit 1
fi

if [ -f /opt/bot/requirements.txt ]; then
    bashio::log.info "Installing Python dependencies"
    if "${PYTHON_BIN}" -m ensurepip --help >/dev/null 2>&1; then
        "${PYTHON_BIN}" -m ensurepip --upgrade || bashio::log.warning "ensurepip upgrade reported an error"
    else
        bashio::log.warning "ensurepip module unavailable; attempting bootstrap via Python"
    fi

    if ! "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
        bashio::log.info "Bootstrapping pip module"
        "${PYTHON_BIN}" - <<'PY'
import ensurepip
ensurepip.bootstrap(upgrade=True)
PY
    fi

    if ! "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
        bashio::log.fatal "pip module is not available even after bootstrapping"
        exit 1
    fi

    "${PYTHON_BIN}" -m pip install --upgrade pip
    "${PYTHON_BIN}" -m pip install --no-cache-dir -r /opt/bot/requirements.txt
fi

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

mkdir -p /data/bot
ENV_FILE="/data/bot/.env"
{
    printf 'EXCHANGE=%s\n' "${EXCHANGE}"
    printf 'BOT_SYMBOL_TICKER=%s\n' "${SYMBOL}"
    printf 'BOT_ORDER_CURRENCY=%s\n' "${ORDER_CCY}"
    printf 'BOT_PAYMENT_CURRENCY=%s\n' "${PAY_CCY}"
    printf 'BOT_DRY_RUN=%s\n' "${DRY_RUN}"
    printf 'BOT_HF_MODE=%s\n' "${HF_MODE}"
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
} > "${ENV_FILE}"

echo "ENABLE_GATEWAY=${ENABLE_GATEWAY}" > /var/run/ha_bot_enable_gateway
echo "${GATEWAY_PORT}" > /var/run/ha_bot_gateway_port

bashio::log.info "Environment prepared"
