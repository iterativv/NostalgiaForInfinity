#!/bin/sh

### Prereqs:
## 1. A directory with the NFIX repo setup on the main branch to run via docker compose
## 2. Configure the localization from repo
## OPTIONAL: configure token and chatId on .env

NFI_PATH=

### Simple script that does the following:
## 1. Pull NFIX repo
## 2. Compare if have new commit
## 3. Send message to telegram if .env is configured
## 4. Stop and Start freqtrader via docker compose
######################################################

if [ -z "$NFI_PATH" ]; then
    echo "NFI_PATH variable is empty"
    exit 1
fi

cd $NFI_PATH

export $(grep -v '^#' .env | xargs)

# pull from NFIX repo
echo "Initianting update on $NFI_PATH"

latest_local_commit=$(git rev-parse HEAD)

git stash push > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "failed to stash changes in NFIX repo"
    exit 1
fi

git_pull_output=$(git pull)

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
    if [ -n "$FREQTRADE__TELEGRAM__TOKEN" ] && [ -n "$FREQTRADE__TELEGRAM__CHAT_ID" ]; then
        # Compose the main message send by the bot
        curl -s --data "text=NFI is updated to commit: *${latest_remote_commit}* . Please wait for reload..." \
            --data "parse_mode=markdown" \
            --data "chat_id=$FREQTRADE__TELEGRAM__CHAT_ID" \
            "https://api.telegram.org/bot${FREQTRADE__TELEGRAM__TOKEN}/sendMessage"
    fi

    echo "\nrestarting freqtrade with NFIX"

    docker compose stop
    docker compose up -d
fi

exit 0
