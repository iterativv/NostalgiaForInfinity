#!/bin/bash
# Sidecar that keeps the NFI strategy file in sync: installs a cron schedule from
# NFI_UPDATE_CRON, runs crond for daily pulls, performs one update at container
# start, then execs the watcher so the main process stays alive and can react to
# further changes.
set -e

echo "================================================"
echo " NFI Updater starting"
echo " Strategy  : ${STRATEGY:-NostalgiaForInfinityX8}"
echo " Exchange  : ${EXCHANGE:-binance}"
echo " Cron      : ${NFI_UPDATE_CRON:-0 10 * * *}"
echo " Timezone  : ${TZ:-UTC}"
echo "================================================"

echo "${NFI_UPDATE_CRON:-0 10 * * *} /scripts/update_nfi.sh >> /proc/1/fd/1 2>&1" | crontab -
crond -l 8

echo "Running initial update check..."
/scripts/update_nfi.sh

exec /scripts/nfi_watcher.sh
