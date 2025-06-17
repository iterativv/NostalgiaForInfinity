#!/bin/sh

### Prereqs:
## 1. A directory with the NFIX repo setup on the main branch to run via docker compose
## 2. Configure the localization from repo
## OPTIONAL: configure token and chatId on .env

NFI_PATH=
ENV_PATH=$NFI_PATH
FREQTRADE_IMAGE_UPDATE=false

### Simple script that does the following:
## 1. Pull NFIX repo
## 2. Compare if have new commit
## 3. Send message to telegram if .env is configured
## 4. Stop and Start freqtrader via docker compose
######################################################

## FUNCTIONS
load_env() {
    local env_file="${1:-.env}"
    
    if [[ -f "$env_file" ]]; then
        set -a
        source grep -v '^#' "$env_file" | grep -v '^[[:space:]]*$' | sed 's/^/export /'
        set +a
    else
        echo "$env_file not found"
        exit 1
    fi
}

send_telegram_notification() {
    local message="${1}"

    if [ -z "$message" ]; then
        echo "message variable is empty"
        exit 1
    fi

    if [ -n "$FREQTRADE__TELEGRAM__TOKEN" ] && [ -n "$FREQTRADE__TELEGRAM__CHAT_ID" ]; then
        response=$(curl -s -X POST \
            --data-urlencode "text=${message}" \
            --data-urlencode "parse_mode=markdown" \
            --data "chat_id=$FREQTRADE__TELEGRAM__CHAT_ID" \
            "https://api.telegram.org/bot${FREQTRADE__TELEGRAM__TOKEN}/sendMessage" 2>/dev/null)
            
        if [[ $? -ne 0 ]]; then
            echo "Error: failed to send telegram notification."
            exit 1
        fi
    fi
}

######################################################

if [ -z "$NFI_PATH" ]; then
    echo "NFI_PATH variable is empty"
    exit 1
fi

echo "starting update on path $NFI_PATH"
cd $NFI_PATH


# pull from NFIX repo
echo "Pulling updates from repo"
latest_local_commit=$(git rev-parse HEAD)

git stash push > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "failed to stash changes in NFIX repo"
    exit 1
fi

git_pull_output=$(git pull > /dev/null 2>&1)

if [ $? -ne 0 ]; then
    echo "failed to pull from NFIX repo: $git_pull_output"
    exit 1
fi

git stash pop > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "failed to unstash changes in NFIX repo"
    exit 1
fi

latest_remote_commit=$(git rev-parse HEAD)

if [ "$latest_local_commit" != "$latest_remote_commit" ]; then
    load_env "${ENV_PATH}/.env"

    echo "text=NFI was updated to commit: *${latest_remote_commit}* . Please wait for reload..."
    send_telegram_notification "text=NFI was updated to commit: *${latest_remote_commit}* . Please wait for reload..."

    echo "\nrestarting freqtrade with NFIX"
    if [[ "$FREQTRADE_IMAGE_UPDATE" == "true" ]]; then
        if docker pull; then
            echo "Pulling new Freqtrade image"
            send_telegram_notification "Pulling new Freqtrade image"
        else
            echo "Error when pulling new Freqtrade image" >&2
            exit 1
        fi
    fi

    docker compose stop
    docker compose up -d
fi

exit 0