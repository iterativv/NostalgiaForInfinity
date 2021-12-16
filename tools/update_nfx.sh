#!/bin/bash

# Settings
url_nfi=https://api.github.com/repos/iterativv/NostalgiaForInfinity/releases/latest
bot_strategy_path=/bot/user_data/strategies # <- Replace this with your own path (e.g. /home/user/bot/user_data/strategies)
telegram_token=123123:123123 # <- Replace with your telegram bot token (e.g. 123123:123123)
telegram_chat_id=123123 # <- Replace with your telegram chat id (e.g. 123123)
##########

# Get latest release and copy it to bot_strategy_path
random_hash=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
version=$(curl -s ${url_nfi} | grep -o '"tag_name": ".*"' | sed 's/"tag_name": "//' | sed 's/"//')
url=$(curl -s ${url_nfi} | grep -o '"tarball_url": ".*"' | sed 's/"tarball_url": "//' | sed 's/"//')
foler_name=/tmp/nfx_${version}_${random_hash}
mkdir -p ${foler_name}
curl -s -L $url | tar xz -C ${foler_name} --strip-components 1
cp ${foler_name}/NostalgiaForInfinityX.py ${bot_strategy_path}/NostalgiaForInfinityX.py
rm -rf ${foler_name}

# Send message to telegram
curl -s -X "POST" "https://api.telegram.org/bot${telegram_token}/sendMessage" \
     -H 'Content-Type: application/json; charset=utf-8' \
     -d $'{
  "chat_id": "'$telegram_chat_id'",
  "text": "<b>Aktualizacja</b>\n<pre>Strategia <b>NostalgiaForInfinityX</b> została zaktualizowana do wersji <b>'$version'</b>.</pre>",
  "parse_mode": "HTML"
}'

# Restart bot
docker restart freqtrade
