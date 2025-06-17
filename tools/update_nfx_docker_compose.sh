#!/bin/sh

### Prereqs:
## 1. A directory with the NFIX repo setup on the main branch to run via docker compose
## 2. Configure the localization from repo
## OPTIONAL: configure token and chatId on .env

NFI_LOCAL_REPO=/opt/binance/NFI-10x

### Simple script that does the following:
## 1. Pull NFIX repo
## 2. Compare if have new commit
## 3. Send message to telegram if .env is configured
## 4. Stop and Start freqtrader via docker compose
######################################################

if [ -n "$NFI_LOCAL_REPO" ]; then
    echo "NFI LOCAL REPO variable empty"
    exit 1
fi

# pull from NFIX repo
echo "updating local NFIX repo"

cd $NFI_LOCAL_REPO

latest_local_commit=$(git rev-parse HEAD)

git stash push > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "failed to stash changes in NFIX repo"
    exit 1
fi

git_pull_output=$(git pull >/dev/null 2>&1)

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

export $(grep -v '^#' .env | xargs)

if [ "$latest_local_commit" != "$latest_remote_commit" ]; then
    if [ -n "$FREQTRADE__TELEGRAM__TOKEN" ] && [ -n "$FREQTRADE__TELEGRAM__CHAT_ID" ]; then
        # Compose the main message send by the bot
        curl -s --data "text=NFI is updated to commit: *${latest_remote_commit}* . Please wait for reload..." \
            --data "parse_mode=markdown" \
            --data "chat_id=$FREQTRADE__TELEGRAM__TOKEN" \
            "https://api.telegram.org/bot${FREQTRADE__TELEGRAM__CHAT_ID}/sendMessage"
    fi

    echo "\nrestarting freqtrade with NFIX"

    docker compose stop
    docker compose up -d
fi

exit 0
