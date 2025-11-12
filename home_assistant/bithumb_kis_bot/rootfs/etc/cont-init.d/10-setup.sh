#!/command/with-contenv bashio
set -euo pipefail

REPO_URL="$(bashio::config 'repository_url')"
REPO_REF="$(bashio::config 'repository_ref')"
EXCHANGE="$(bashio::config 'exchange')"
ENABLE_GATEWAY="$(bashio::config 'enable_gateway')"
ENV_VARS_COUNT=$(bashio::config 'env_vars | length')

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

if [ -f /opt/bot/requirements.txt ]; then
    bashio::log.info "Installing Python dependencies"
    pip install --upgrade pip >/dev/null
    pip install -r /opt/bot/requirements.txt
fi

mkdir -p /data/bot
ENV_FILE="/data/bot/.env"
: > "${ENV_FILE}"
echo "EXCHANGE=${EXCHANGE}" >> "${ENV_FILE}"

declare -a ENV_VARS
for ((i=0; i<ENV_VARS_COUNT; i++)); do
    VALUE="$(bashio::config "env_vars[${i}]")"
    if [[ -n "${VALUE}" ]]; then
        echo "${VALUE}" >> "${ENV_FILE}"
    fi
done

echo "ENABLE_GATEWAY=${ENABLE_GATEWAY}" > /var/run/ha_bot_enable_gateway

bashio::log.info "Environment prepared"
