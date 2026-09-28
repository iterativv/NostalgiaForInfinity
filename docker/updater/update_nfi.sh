#!/bin/bash

# --- Configuration (all values come from environment variables set in docker-compose.yml) ---

STRATEGY="${STRATEGY:-NostalgiaForInfinityX8}"
EXCHANGE="${EXCHANGE:-binance}"

# Project root is mounted at /data inside this container
BASE_DIR="/data"
STRATEGY_FILE="$BASE_DIR/${STRATEGY}.py"
CONFIGS_DIR="$BASE_DIR/configs"

# Pairlist filename — override via NFI_PAIRLIST_FILE if your exchange uses a different name
PAIRLIST_FILE="${NFI_PAIRLIST_FILE:-pairlist-volume-${EXCHANGE}-usdt.json}"

TEMP_DIR="/tmp/nfi_update"
REPO_URL="https://raw.githubusercontent.com/iterativv/NostalgiaForInfinity/main"

mkdir -p "$TEMP_DIR" "$CONFIGS_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "------------------------------------------------"
echo "Date: $(date)"
echo "Checking for NFI updates..."

CHANGES_DETECTED=false

# Per-exchange state directory: each updater independently tracks what it has seen
# and what the bot has loaded. This avoids the race condition where multiple
# updaters sharing the same mount see a file already updated by another instance
# and skip their own restart.
STATE_DIR="$BASE_DIR/.updater_state_${EXCHANGE}"
mkdir -p "$STATE_DIR"

# --- Downloads a file from GitHub and replaces the local copy if it changed ---
check_and_update() {
    local remote_suffix=$1
    local local_path=$2
    local filename
    filename=$(basename "$local_path")
    local remote_url="$REPO_URL/$remote_suffix"
    local tmp_file="$TEMP_DIR/$filename"

    echo -n "Checking $filename ... "

    if ! wget -q -O "$tmp_file" "$remote_url"; then
        echo -e "${RED}[ERROR] Download failed for $remote_url${NC}"
        return
    fi

    STATE_FILE="$STATE_DIR/${filename}.hash"
    BOT_STATE_FILE="$STATE_DIR/.bot_${filename}.hash"

    REMOTE_HASH=$(md5sum "$tmp_file" | awk '{print $1}')

    if [ -f "$STATE_FILE" ]; then
        LAST_REMOTE_HASH=$(cat "$STATE_FILE")

        if [ "$LAST_REMOTE_HASH" != "$REMOTE_HASH" ]; then
            # Remote changed → download to disk, mark for restart
            echo -e "${GREEN}[UPDATED]${NC}"
            cp "$tmp_file" "$local_path"
            echo "$REMOTE_HASH" > "$STATE_FILE"
            CHANGES_DETECTED=true
        else
            # Remote unchanged — but is the bot actually running this code?
            LOCAL_HASH=$(md5sum "$local_path" 2>/dev/null | awk '{print $1}')
            if [ -f "$BOT_STATE_FILE" ]; then
                BOT_HASH=$(cat "$BOT_STATE_FILE")
                if [ "$BOT_HASH" != "$LOCAL_HASH" ]; then
                    # File on disk changed without bot restart (or bot missed a previous update)
                    echo -e "${YELLOW}[STALE] Bot running old code, will restart${NC}"
                    CHANGES_DETECTED=true
                else
                    echo -e "${YELLOW}[OK] Up to date${NC}"
                fi
            else
                # No bot-state recorded — can't verify what the bot is running
                echo -e "${YELLOW}[SYNC] First run with bot-state tracking, will restart${NC}"
                CHANGES_DETECTED=true
            fi
        fi
    else
        # First run — no state at all. Always restart to establish a known baseline.
        echo -e "${YELLOW}[INIT] First run, establishing baseline${NC}"
        cp "$tmp_file" "$local_path"
        echo "$REMOTE_HASH" > "$STATE_FILE"
        CHANGES_DETECTED=true
    fi

    rm -f "$tmp_file"
}

# --- Check all three files ---
check_and_update "${STRATEGY}.py"                      "$STRATEGY_FILE"
check_and_update "configs/blacklist-${EXCHANGE}.json"  "$CONFIGS_DIR/blacklist-${EXCHANGE}.json"
check_and_update "configs/${PAIRLIST_FILE}"            "$CONFIGS_DIR/${PAIRLIST_FILE}"

echo "------------------------------------------------"

if [ "$CHANGES_DETECTED" = true ]; then
    echo -e "${GREEN}Updates applied! Restarting freqtrade...${NC}"
    rm -rf "$TEMP_DIR"

    # Restart via Docker Compose using the mounted socket.
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-nostalgiaforinfinity}" \
        docker compose -f /data/docker-compose.yml restart freqtrade

    echo "Bot restarted successfully."

    # Record what the bot just loaded, so future checks can detect if the bot
    # is running stale code (e.g. file changed externally, or missed a restart).
    for f in "$STRATEGY_FILE" "$CONFIGS_DIR/blacklist-${EXCHANGE}.json" "$CONFIGS_DIR/${PAIRLIST_FILE}"; do
        fname=$(basename "$f")
        if [ -f "$f" ]; then
            md5sum "$f" | awk '{print $1}' > "$STATE_DIR/.bot_${fname}.hash"
        fi
    done
else
    echo -e "${GREEN}No updates found. System is up to date.${NC}"
    rm -rf "$TEMP_DIR"
fi
