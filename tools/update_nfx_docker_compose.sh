#!/bin/sh

### Prereqs:
## 1. A directory with the NFIX repo setup on the main branch to run via docker compose
## 2. Configure the localization from repo
## OPTIONAL: configure token and chatId on .env

NFI_PATH=
ENV_PATH=
FREQTRADE_IMAGE_UPDATE=false
FREQTRADE_IMAGE="freqtradeorg/freqtrade:stable"
TELEGRAM_NOTIFICATION=true

### Simple script that does the following:
## 1. Pull NFIX repo
## 2. Compare if have new commits
## 3. Send message to telegram if .env is configured
## 4. Stop and Start freqtrade via docker compose
######################################################

## FUNCTIONS
load_env() {
    local env_file="${1:-.env}"
    if [ -f "$env_file" ]; then
        set -a
        . "$env_file"
        set +a
    else
        echo "Error: $env_file not found"
        exit 1
    fi
}

send_telegram_notification() {
    local freqtrade_telegram_enabled=${FREQTRADE__TELEGRAM__ENABLED:-false}
    if [ "$freqtrade_telegram_enabled" = "false" ] || [ "$TELEGRAM_NOTIFICATION" = "false" ]; then
        return 0
    fi

    local message="$1"

    if [ -z "$message" ]; then
        echo "Error: message variable is empty"
        return 1
    fi

    if [ -n "$FREQTRADE__TELEGRAM__TOKEN" ] && [ -n "$FREQTRADE__TELEGRAM__CHAT_ID" ]; then
        local curl_error=$(curl -s -X POST \
            --data-urlencode "text=${message}" \
            --data-urlencode "parse_mode=markdown" \
            --data "chat_id=$FREQTRADE__TELEGRAM__CHAT_ID" \
            "https://api.telegram.org/bot${FREQTRADE__TELEGRAM__TOKEN}/sendMessage" 2>&1 1>/dev/null)
        if [ $? -ne 0 ]; then
            echo "Error: failed to send telegram notification: $curl_error"
            return 1
        fi
    fi
}

######################################################

if [ -z "$NFI_PATH" ]; then
    echo "Error: NFI_PATH variable is empty"
    exit 1
fi

if [ -z "$ENV_PATH" ]; then
    ENV_PATH=$NFI_PATH
fi


if [ ! -d "$NFI_PATH" ]; then
    echo "Error: NFI_PATH ($NFI_PATH) is not a directory or does not exist."
    exit 1
fi

cd "$NFI_PATH" || exit 1

if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "Error: NFI_PATH ($NFI_PATH) is not a git repository."
    exit 1
fi

# pull from NFIX repo
echo "Info: pulling updates from repo"
latest_local_commit=$(git rev-parse HEAD)

git stash push > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "Error: failed to stash changes in NFIX repo"
    exit 1
fi

git_pull_error=$(git pull 2>&1 1>/dev/null)

if [ $? -ne 0 ]; then
    echo "Error: failed to pull from NFIX repo: $git_pull_error"
    git stash pop > /dev/null 2>&1
    exit 1
fi

git stash pop > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "Error: failed to unstash changes in NFIX repo"
    exit 1
fi

latest_remote_commit=$(git rev-parse HEAD)

if [ "$latest_local_commit" != "$latest_remote_commit" ]; then
    load_env "${ENV_PATH}/.env"

    latest_remote_commit_short=$(echo "$latest_remote_commit" | cut -c1-7)
    message="NFI was updated to commit: *${latest_remote_commit_short}*. Please wait for reload..."

    echo "Info: $message"
    send_telegram_notification "$message"

    if [ "$FREQTRADE_IMAGE_UPDATE" = "true" ]; then
        echo "Info: checking new freqtrade image"
        local_digest=$(docker inspect --format='{{.Id}}' "$FREQTRADE_IMAGE" 2>/dev/null || echo "none")

        docker pull "$FREQTRADE_IMAGE" --quiet

        remote_digest=$(docker inspect --format='{{.Id}}' "$FREQTRADE_IMAGE" 2>/dev/null || echo "none")

        if [ "$local_digest" != "$remote_digest" ]; then
            message="freqtrade image version was updated"

            echo "Info: $message"
            send_telegram_notification "$message"
        fi
    fi

    echo "Info: restarting freqtrade with NFIX"
    docker compose stop
    docker compose up -d
fi

exit 0
