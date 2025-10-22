#!/bin/bash

# What this script does:
# This script automates the process of checking for updates for NFI repository, downloading the latest release,
# extracting and updating specified files, cleaning up old files, and optionally restarting a Docker container.
# It also supports sending Telegram notifications and can be configured to run periodically via a cron job.

# How to automate the update process:
# 1. First run the script manually to create the config file.
# 2. After the config file is created, you can set up a cron job to run this script periodically.
# 3. To set up a cron job, run `crontab -e` and add a line like: 0 * * * * /path/to/your/script/checkupdates.sh // to run the script every hour.
set -e  # Exit immediately if a command exits with a non-zero status

# Constants
SCRIPT_DIR=$(dirname "$0")
CONFIG_FILE="$SCRIPT_DIR/config.cfg"
LOCAL_VERSION_FILE="$SCRIPT_DIR/version.txt"
LOG_FILE="$SCRIPT_DIR/update.log"
GITHUB_USER="iterativv"
GITHUB_REPO="NostalgiaForInfinity"

# Functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        log "Dependency '$1' is not installed. Please install it first."
        exit 1
    fi
}

update_files() {
    local file_type="$1"
    local files="$2"
    local destination="$3"

    log "Processing $file_type files: $files"
    log "Destination directory: $destination"

    # Normalize input to handle space-separated or newline-separated values
    files=$(echo "$files" | tr ' ' ',' | tr '\n' ',')

    IFS=',' read -r -a files_array <<< "$files"
    for file in "${files_array[@]}"; do
        # Search for the file in the extracted release directory
        local source_file
        source_file=$(find "$EXTRACTED_DIR" -type f -name "$file" 2>/dev/null | head -n 1)

        if [ -n "$source_file" ]; then
            cp "$source_file" "$destination/$(basename "$file")"
            log "$file_type file copied successfully: $file"
        else
            log "Error: $file_type file not found in the extracted release: $file"
        fi
    done
}

validate_file_extension() {
    local files="$1"
    local extension="$2"

    IFS=',' read -r -a files_array <<< "$files"
    for file in "${files_array[@]}"; do
        if [[ ! "$file" == *"$extension" ]]; then
            log "Error: File '$file' does not end with '$extension'."
            return 1
        fi
    done
    return 0
}

# Main Script
log "=== Starting update script ==="

# Check dependencies
for dependency in jq curl unzip; do
    check_dependency "$dependency"
done

# Initialize config if not found
if [ ! -f "$CONFIG_FILE" ]; then
    log "Config file not found. Creating a new one at $CONFIG_FILE."

    # Prompt user for configuration values
    echo "Enter strategy files (default: NostalgiaForInfinityX7.py)."
    echo "You can use commas, spaces, or press Enter to accept the default value:"
    read -p "Strategy files: " strategy_file
    strategy_file=${strategy_file:-NostalgiaForInfinityX7.py}
    validate_file_extension "$strategy_file" ".py" || { log "Invalid strategy file extension."; exit 1; }

    echo "Enter blacklist file(s) (default: blacklist-binance.json)."
    echo "You can use commas, spaces, or press Enter to accept the default value:"
    read -p "Blacklist files: " blacklist_file
    blacklist_file=${blacklist_file:-blacklist-binance.json}
    validate_file_extension "$blacklist_file" ".json" || { log "Invalid blacklist file extension."; exit 1; }

    read -p "Enable cleanup of extracted and downloaded folders? (y/n, default: y): " cleanup_old_files
    cleanup_old_files=${cleanup_old_files:-y}

    read -p "Enter Telegram bot token (leave blank to skip): " telegram_bot_token
    read -p "Enter Telegram chat ID (leave blank to skip): " telegram_chat_id

    # Save configuration to file
    cat <<EOF > "$CONFIG_FILE"
strategy_file="$strategy_file"
blacklist_file="$blacklist_file"
cleanup_old_files="$cleanup_old_files"
telegram_bot_token="$telegram_bot_token"
telegram_chat_id="$telegram_chat_id"
EOF

    log "Configuration saved to $CONFIG_FILE."
fi

log "Reading configuration from $CONFIG_FILE"
source "$CONFIG_FILE"

# Initialize version file if not found
if [ ! -f "$LOCAL_VERSION_FILE" ]; then
    log "Version file not found. Creating a new one."
    echo "0" > "$LOCAL_VERSION_FILE"
fi

# Fetch latest release data
RELEASE_DATA=$(curl --silent "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/releases/latest")
LATEST_RELEASE=$(echo "$RELEASE_DATA" | jq -r .tag_name)
LATEST_VERSION=${LATEST_RELEASE#*v}
LOCAL_VERSION=$(cat "$LOCAL_VERSION_FILE")

# Compare versions using sort -V
if [ "$(printf "%s\n%s" "$LOCAL_VERSION" "$LATEST_VERSION" | sort -V | head -n 1)" != "$LATEST_VERSION" ]; then
    log "A new version ($LATEST_VERSION) is available. Current version: $LOCAL_VERSION."
    log "Updating to the latest version..."

    # Download and unzip the latest release
    ZIP_URL=$(echo "$RELEASE_DATA" | jq -r .zipball_url)
    ZIP_FILE="$SCRIPT_DIR/$LATEST_RELEASE.zip"
    curl -L -o "$ZIP_FILE" "$ZIP_URL"
    unzip -oqq "$ZIP_FILE" -d "$SCRIPT_DIR"
    # Determine the extracted release directory
    EXTRACTED_DIR=$(find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 -type d -name "iterativv-*" | head -n 1)
    if [ -z "$EXTRACTED_DIR" ]; then
        log "Error: Could not determine the extracted release directory."
        exit 1
    fi
    log "Extracted release directory: $EXTRACTED_DIR"

    # Update local version file
    echo "$LATEST_VERSION" > "$LOCAL_VERSION_FILE"
    log "Updated to version $LATEST_VERSION."

    # Update files based on configuration
    [[ -n "$strategy_file" ]] && update_files "Strategy" "$strategy_file" "$SCRIPT_DIR/.."
    [[ -n "$blacklist_file" ]] && update_files "Blacklist" "$blacklist_file" "$SCRIPT_DIR/../configs"

    # Cleanup old files
    if [[ "$cleanup_old_files" == "y" ]]; then
        find "$SCRIPT_DIR" -name "*.zip" -type f -delete
        log "Old .zip files deleted."

        if [ -d "$EXTRACTED_DIR" ]; then
            rm -rf "$EXTRACTED_DIR"
            log "Extracted folder deleted: $EXTRACTED_DIR"
        fi

        log "Cleanup of extracted and downloaded folders completed."
    else
        log "Cleanup of extracted and downloaded folders skipped."
    fi

    # Send Telegram notification
    if [[ -n "$telegram_bot_token" && -n "$telegram_chat_id" ]]; then
        curl -s -X POST "https://api.telegram.org/bot$telegram_bot_token/sendMessage" \
            -d "chat_id=$telegram_chat_id&text=Updated to version $LATEST_VERSION of $GITHUB_REPO." || \
            log "Failed to send Telegram notification."
    fi

    # Restart Docker container if docker-compose.yml exists
    if [ -f "$SCRIPT_DIR/../docker-compose.yml" ]; then
        log "Restarting Docker container..."
        docker compose -f "$SCRIPT_DIR/../docker-compose.yml" down
        docker compose -f "$SCRIPT_DIR/../docker-compose.yml" up -d
        log "Docker container restarted."
    else
        log "Docker Compose file not found. Skipping Docker restart."
    fi
else
    log "You are already using the latest version ($LATEST_VERSION)."
fi
