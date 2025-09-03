#!/usr/bin/env sh
set -eu

### Prereqs:
## 1. A directory with the NFIX repo setup on the main branch to run via docker compose
## 2. Configure the localization from repo
## OPTIONAL: configure token and chatId on .env

NFI_PATH=
ENV_PATH=
FREQTRADE_IMAGE_UPDATE=false
FREQTRADE_IMAGE="freqtradeorg/freqtrade:stable"
PRUNE_IMAGES=false
TELEGRAM_NOTIFICATION=true

### Simple script that does the following:
## 1. Pull NFIX repo
## 2. Compare if have new commits
## 3. Send message to telegram if .env is configured
## 4. Stop and Start freqtrade via docker compose
######################################################

## FUNCTIONS
echo_timestamped() {
    printf '%s - %s\n' "$(date +"%Y-%m-%d %H:%M:%S")" "$*"
}

load_env() {
    env_file="${1:-.env}"
    if [ -f "$env_file" ]; then
        set -a
        . "$env_file"
        set +a
    else
        echo_timestamped "Error: $env_file not found"
        exit 1
    fi
}

escape_telegram_markdown() {
    printf '%s' "$1" | command sed \
        -e 's/\\/\\\\/g' \
        -e 's/[][(){}.*_~`>#\+=|.!-]/\\&/g'
}

send_telegram_notification() {
    freqtrade_telegram_enabled=${FREQTRADE__TELEGRAM__ENABLED:-false}
    if [ "$freqtrade_telegram_enabled" = "false" ] || [ "$TELEGRAM_NOTIFICATION" = "false" ]; then
        return 0
    fi

    telegram_message=$(escape_telegram_markdown "$1")
    if [ -z "$telegram_message" ]; then
        echo_timestamped "Error: message variable is empty"
        return 1
    fi

    if ! command -v curl >/dev/null 2>&1; then
        echo_timestamped "Error: curl not found, cannot send telegram notification"
        return 1
    fi

    if [ -n "$FREQTRADE__TELEGRAM__TOKEN" ] && [ -n "$FREQTRADE__TELEGRAM__CHAT_ID" ]; then
        curl_error=$(command curl -s -X POST \
            --data-urlencode "text=${telegram_message}" \
            --data-urlencode "parse_mode=MarkdownV2" \
            --data "chat_id=$FREQTRADE__TELEGRAM__CHAT_ID" \
            "https://api.telegram.org/bot${FREQTRADE__TELEGRAM__TOKEN}/sendMessage" 2>&1 1>/dev/null)
        if [ $? -ne 0 ]; then
            echo_timestamped "Error: failed to send telegram notification: $curl_error"
            return 1
        fi
    fi
}

######################################################

if [ -z "$NFI_PATH" ]; then
    echo_timestamped "Error: NFI_PATH variable is empty"
    exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
    nfi_path_hash=$(printf '%s' "$NFI_PATH" | command sha256sum | command cut -c1-10)
elif command -v md5sum >/dev/null 2>&1; then
    nfi_path_hash=$(printf '%s' "$NFI_PATH" | command md5sum | command cut -c1-10)
elif command -v shasum >/dev/null 2>&1; then
    nfi_path_hash=$(printf '%s' "$NFI_PATH" | command shasum -a 256 | command cut -c1-10)
else
    nfi_path_hash=$(printf '%s' "$NFI_PATH" | command sed -e 's/[^A-Za-z0-9]/_/g' | command cut -c1-10)
fi
LOCKFILE="/tmp/nfx-docker-update.${nfi_path_hash}.lock"
if [ -f "$LOCKFILE" ]; then
    echo_timestamped "Error: already running for ${NFI_PATH}"
    exit 1
fi
trap 'rm -f "$LOCKFILE"' 0 HUP INT TERM
touch "$LOCKFILE"

if [ -z "$ENV_PATH" ]; then
    ENV_PATH=$NFI_PATH
fi

if [ ! -d "$NFI_PATH" ]; then
    echo_timestamped "Error: NFI_PATH (${NFI_PATH}) is not a directory or does not exist"
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo_timestamped "Error: git not found in PATH"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo_timestamped "Error: docker not found in PATH"
    exit 1
fi

cd -- "$NFI_PATH" || exit 1

load_env "${ENV_PATH}/.env"

if ! command git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo_timestamped "Error: NFI_PATH (${NFI_PATH}) is not a git repository"
    exit 1
fi

echo_timestamped "Info: pulling updates from repo"
latest_local_commit=$(command git rev-parse HEAD)

command git stash push > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo_timestamped "Error: failed to stash changes in NFIX repo"
    exit 1
fi

git_pull_error=$(command git pull 2>&1 1>/dev/null)

if [ $? -ne 0 ]; then
    echo_timestamped "Error: failed to pull from NFIX repo: $git_pull_error"
    command git stash pop > /dev/null 2>&1
    exit 1
fi

command git stash pop > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo_timestamped "Error: failed to unstash changes in NFIX repo"
    exit 1
fi

need_restart=false

latest_remote_commit=$(command git rev-parse HEAD)
if [ "$latest_local_commit" != "$latest_remote_commit" ]; then
    need_restart=true
    latest_remote_commit_short=$(printf %s "$latest_remote_commit" | command cut -c1-7)
    message="NFI was updated to commit: *${latest_remote_commit_short}*. Please wait for reload..."
    echo_timestamped "Info: $message"
    send_telegram_notification "$message"
else
    echo_timestamped "Info: NFI is up to date"
fi

# check ft image and update if needed
if [ "$FREQTRADE_IMAGE_UPDATE" = "true" ]; then
    echo_timestamped "Info: docker image pull for ${FREQTRADE_IMAGE}"
    local_digest=$(command docker image inspect --format='{{.Id}}' "$FREQTRADE_IMAGE" 2>/dev/null || command echo "none")
    if ! command docker image pull --quiet "$FREQTRADE_IMAGE"; then
        echo_timestamped "Error: docker image pull failed for ${FREQTRADE_IMAGE}"
        exit 1
    fi
    remote_digest=$(command docker image inspect --format='{{.Id}}' "$FREQTRADE_IMAGE" 2>/dev/null || command echo "none")

    if [ "$local_digest" != "$remote_digest" ]; then
        need_restart=true
        message="docker image ${FREQTRADE_IMAGE} was updated (${local_digest} -> ${remote_digest}). Please wait for reload..."
        echo_timestamped "Info: $message"
        send_telegram_notification "$message"
    else
        echo_timestamped "Info: docker image ${FREQTRADE_IMAGE} is up to date"
    fi
fi

if [ "$need_restart" = "true" ]; then
    echo_timestamped "Info: restarting docker image ${FREQTRADE_IMAGE} with NFIX"
    if ! command docker compose --progress quiet down; then
        echo_timestamped "Error: docker compose down failed"
        exit 1
    fi
    if ! command docker compose --progress quiet up -d; then
        echo_timestamped "Error: docker compose up failed"
        exit 1
    fi
    echo_timestamped "Info: restarted docker image ${FREQTRADE_IMAGE} with NFIX"
    if [ "$PRUNE_IMAGES" = "true" ]; then
        echo_timestamped "Info: pruning unused docker images"
        command docker image prune -f >/dev/null 2>&1 || true
    fi
else
    echo_timestamped "Info: NFI and docker image ${FREQTRADE_IMAGE} are up to date, no restart needed"
fi

exit 0
