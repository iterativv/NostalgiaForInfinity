#!/bin/bash

# What this script does:
# This script automates checking the NFI repository for updates, downloading the latest release or branch commit,
# extracting the archive, updating strategy files, and automatically updating all blacklist JSON files.
# It cleans up downloaded and extracted files, optionally restarts a Docker container, and can send Telegram notifications.
# It supports two update modes:
#   1. releases - Use official GitHub releases and update to the latest stable release
#   2) commits  - Use the latest commit from the main branch

# How to automate the update process:
# 1. First run the script manually to create the config file and select your preferred update mode.
# 2. After the config file is created, you can set up a cron job to run this script periodically.
# 3. To set up a cron job, run `crontab -e` and add a line like: 0 * * * * /path/to/your/script/checkupdates.sh // to run the script every hour.
set -eE  # Exit immediately if a command exits with a non-zero status and inherit ERR traps

# Constants
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONFIG_FILE="$SCRIPT_DIR/config.cfg"
LOCAL_VERSION_FILE="$SCRIPT_DIR/version.txt"
LOG_FILE="$SCRIPT_DIR/update.log"
GITHUB_USER="iterativv"
GITHUB_REPO="NostalgiaForInfinity"
DEFAULT_BRANCH="main"
git_branch="$DEFAULT_BRANCH"
LOCK_DIR="$SCRIPT_DIR/.checkupdates.lock"
CURRENT_STAGE="starting up"

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

ensure_strategy_symlink() {
    local target="$SCRIPT_DIR/../NostalgiaForInfinityX8.py"
    local link="$SCRIPT_DIR/../user_data/strategies/NostalgiaForInfinityX8.py"

    # The target as stored inside the symlink
    local relative_target="../../NostalgiaForInfinityX8.py"

    # Symlink already exists and points to the correct relative target
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$relative_target" ]; then
        log "Strategy symlink already exists and is correct."
        return 0
    fi

    # Something exists at the link location, but it's wrong
    if [ -e "$link" ] || [ -L "$link" ]; then
        log "Incorrect strategy symlink/file found. Fixing it..."
        rm -f "$link"
    fi

    ln -s "$relative_target" "$link"

    log "Created strategy symlink: $link -> $relative_target"
}

check_x8_migration() {
    local env_file="$SCRIPT_DIR/../.env"
    local configured_strategy

    if [ ! -f "$env_file" ]; then
        log ".env file not found. Skipping X8 migration check."
        return 0
    fi

    # Read Freqtrade's actual configured strategy without sourcing .env
    configured_strategy=$(grep -E '^FREQTRADE__STRATEGY=' "$env_file" | head -n 1 | cut -d '=' -f2-)

    log "Freqtrade strategy: $configured_strategy"
    log "Updater strategy: $strategy_file"

    # User has migrated Freqtrade to X8,
    # but updater is still configured for X7
    if [[ "$configured_strategy" == "NostalgiaForInfinityX8" ]] && [[ "$strategy_file" == "NostalgiaForInfinityX7.py" ]]; then
        log "X8 is configured in .env, but config.cfg is still using X7."

        # Telegram notification here
        if [[ -n "$telegram_bot_token" && -n "$telegram_chat_id" ]]; then
            curl -s -X POST "https://api.telegram.org/bot$telegram_bot_token/sendMessage" \
                -d "chat_id=$telegram_chat_id&text=Warning: Freqtrade is configured for X8, but updater is still using X7. Please update config.cfg." || \
                log "Failed to send Telegram notification."
        fi
    fi
}

update_files() {
    local file_type="$1"
    local files="$2"
    local destination="$3"
    local source_file
    local file
    local i
    local -a files_array
    local -a source_files=()

    log "Processing $file_type files: $files"
    log "Destination directory: $destination"

    # Normalize input to handle space-separated or newline-separated values
    files=$(echo "$files" | tr ' ' ',' | tr '\n' ',')

    IFS=',' read -r -a files_array <<< "$files"
    for file in "${files_array[@]}"; do
        if [[ -z "$file" ]]; then
            source_files+=("")
            continue
        fi

        # Search for the file in the extracted release directory
        source_file=$(find "$EXTRACTED_DIR" -type f -name "$file" 2>/dev/null | head -n 1)

        if [ -z "$source_file" ]; then
            log "Error: $file_type file not found in the extracted release: $file"
            return 1
        fi
        source_files+=("$source_file")
    done
    for i in "${!files_array[@]}"; do
        file="${files_array[$i]}"
        [[ -z "$file" ]] && continue
        cp "${source_files[$i]}" "$destination/$(basename "$file")"
        log "$file_type file copied successfully: $file"
    done
}

update_blacklists() {
    local destination="$1"
    local blacklist_files
    local source_file

    mkdir -p "$destination"
    blacklist_files=$(find "$EXTRACTED_DIR" -type f -name 'blacklist*.json' | sort)

    if [ -z "$blacklist_files" ]; then
        log "No blacklist files found in the extracted release."
        return 1
    fi

    while IFS= read -r source_file; do
        cp "$source_file" "$destination/$(basename "$source_file")"
        log "Blacklist file copied successfully: $(basename "$source_file")"
    done <<< "$blacklist_files"
}

send_telegram() {
    local message="$1"

    [[ -n "${telegram_bot_token:-}" && -n "${telegram_chat_id:-}" ]] || return 0
    curl -sS -X POST "https://api.telegram.org/bot$telegram_bot_token/sendMessage" \
        --data-urlencode "chat_id=$telegram_chat_id" \
        --data-urlencode "text=$message" || \
        log "Failed to send Telegram notification."
}

# Use for explicit failures (exit 1 bypasses the ERR trap).
die() {
    trap - ERR
    log "Error: $*"
    send_telegram "Update failed during '$CURRENT_STAGE' for $GITHUB_REPO: $*"
    exit 1
}

handle_update_error() {
    local status="$1"
    local line="$2"

    trap - ERR
    log "Update failed during '$CURRENT_STAGE' at line $line (exit status $status)."
    send_telegram "Update failed during '$CURRENT_STAGE' at line $line (exit status $status) for $GITHUB_REPO."
    exit "$status"
}

clean_stale_downloads() {
    # Remove leftovers from a previously failed run so they cannot be picked up again.
    rm -f "$ZIP_FILE"
    rm -rf "$SCRIPT_DIR/$GITHUB_REPO-$git_branch" "$SCRIPT_DIR"/iterativv-*
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

# Portable lock (mkdir is atomic). The PID is stored so a lock left behind by a
# killed process or a reboot is detected as stale and removed.
acquire_lock() {
    local old_pid

    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo $$ > "$LOCK_DIR/pid"
        return 0
    fi

    old_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
    if [[ -z "$old_pid" ]]; then
        # The holder may not have written its PID yet.
        sleep 1
        old_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
    fi

    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
        return 1
    fi

    log "Removing stale lock (pid: ${old_pid:-unknown})."
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" 2>/dev/null || return 1
    echo $$ > "$LOCK_DIR/pid"
}

# Main Script
if ! acquire_lock; then
    log "Another updater instance is already running. Exiting."
    exit 1
fi
trap 'rm -rf "$LOCK_DIR"' EXIT
trap 'exit 1' HUP INT TERM

log "=== Starting update script ==="

# Ensure strategy symlink exists and is correct
ensure_strategy_symlink

# Check dependencies
for dependency in jq curl unzip; do
    check_dependency "$dependency"
done

# Initialize config if not found
if [ ! -f "$CONFIG_FILE" ]; then
    log "Config file not found. Creating a new one at $CONFIG_FILE."

    # Prompt user for update mode
    echo "Select update mode:"
    echo "  1) releases - Use official GitHub releases"
    echo "  2) commits  - Use latest commits from the repository"
    read -p "Enter your choice (1 or 2, default: 2): " update_mode_choice
    update_mode_choice=${update_mode_choice:-2}

    if [ "$update_mode_choice" = "2" ]; then
        update_mode="commits"
    else
        update_mode="releases"
    fi

    # Prompt user for configuration values
    echo "Enter strategy files (default: NostalgiaForInfinityX8.py)."
    echo "You can use commas, spaces, or press Enter to accept the default value:"
    read -p "Strategy files: " strategy_file
    strategy_file=${strategy_file:-NostalgiaForInfinityX8.py}
    validate_file_extension "$strategy_file" ".py" || { log "Invalid strategy file extension."; exit 1; }

    read -p "Enable cleanup of extracted and downloaded folders? (y/n, default: y): " cleanup_old_files
    cleanup_old_files=${cleanup_old_files:-y}

    read -p "Enter Telegram bot token (leave blank to skip): " telegram_bot_token
    read -p "Enter Telegram chat ID (leave blank to skip): " telegram_chat_id

    # Save configuration to file
    cat <<EOF > "$CONFIG_FILE"
update_mode="$update_mode"
strategy_file="$strategy_file"
cleanup_old_files="$cleanup_old_files"
telegram_bot_token="$telegram_bot_token"
telegram_chat_id="$telegram_chat_id"
EOF

    log "Configuration saved to $CONFIG_FILE."
fi

log "Reading configuration from $CONFIG_FILE"
source "$CONFIG_FILE"
trap 'handle_update_error "$?" "$LINENO"' ERR
CURRENT_STAGE="checking for updates"
check_x8_migration
# Set defaults if not configured
update_mode=${update_mode:-releases}

# Initialize version file if not found
if [ ! -f "$LOCAL_VERSION_FILE" ]; then
    log "Version file not found. Creating a new one."
    echo "0" > "$LOCAL_VERSION_FILE"
fi

# Fetch latest release data and compare versions
if [ "$update_mode" = "commits" ]; then
    log "Update mode: Using latest commits from branch '$git_branch'"

    # Fetch latest commit data
    COMMIT_DATA=$(curl --silent "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/commits?per_page=1&sha=$git_branch")
    LATEST_COMMIT=$(echo "$COMMIT_DATA" | jq -r '.[0].sha' 2>/dev/null | cut -c1-7 || true)
    COMMIT_DATE=$(echo "$COMMIT_DATA" | jq -r '.[0].commit.committer.date' 2>/dev/null || true)

    if [ -z "$LATEST_COMMIT" ] || [ "$LATEST_COMMIT" = "null" ]; then
        die "Could not fetch latest commit from branch '$git_branch' (check the branch name or GitHub rate limit)."
    fi

    LOCAL_VERSION=$(cat "$LOCAL_VERSION_FILE")
    LATEST_VERSION="$LATEST_COMMIT"

    log "Latest commit: $LATEST_VERSION (Date: $COMMIT_DATE)"
    log "Local version: $LOCAL_VERSION"

    # Compare versions
    if [ "$LOCAL_VERSION" != "$LATEST_VERSION" ]; then
        log "A new commit ($LATEST_VERSION) is available. Current version: $LOCAL_VERSION."
        log "Downloading from branch '$git_branch'..."

        # Download the latest code from the branch
        ZIP_URL="https://github.com/$GITHUB_USER/$GITHUB_REPO/archive/refs/heads/$git_branch.zip"
        ZIP_FILE="$SCRIPT_DIR/$LATEST_VERSION.zip"

        CURRENT_STAGE="downloading and extracting"
        clean_stale_downloads
        curl -L -o "$ZIP_FILE" "$ZIP_URL"
        unzip -oqq "$ZIP_FILE" -d "$SCRIPT_DIR"

        # Determine the extracted directory (for branch archives, it's {repo}-{branch})
        EXTRACTED_DIR=$(find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 -type d -name "$GITHUB_REPO-$git_branch" | head -n 1)
        if [ -z "$EXTRACTED_DIR" ]; then
            # Try alternative naming
            EXTRACTED_DIR=$(find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 -type d -name "*$GITHUB_REPO*" ! -name "iterativv-*" | head -n 1)
        fi
        if [ -z "$EXTRACTED_DIR" ]; then
            die "Could not determine the extracted release directory."
        fi

        log "Extracted directory: $EXTRACTED_DIR"
        UPDATE_AVAILABLE=true
    else
        log "You are already using the latest commit ($LATEST_VERSION) from branch '$git_branch'."
        UPDATE_AVAILABLE=false
    fi
else
    log "Update mode: Using official GitHub releases"

    # Fetch latest release data
    RELEASE_DATA=$(curl --silent "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/releases/latest")
    LATEST_RELEASE=$(echo "$RELEASE_DATA" | jq -r .tag_name)
    if [ -z "$LATEST_RELEASE" ] || [ "$LATEST_RELEASE" = "null" ]; then
        die "Could not fetch the latest release (possible GitHub rate limit)."
    fi
    LATEST_VERSION=${LATEST_RELEASE#*v}
    LOCAL_VERSION=$(cat "$LOCAL_VERSION_FILE")

    log "Latest release: $LATEST_RELEASE (Version: $LATEST_VERSION)"
    log "Local version: $LOCAL_VERSION"

    # Compare versions using sort -V
    if [ "$(printf "%s\n%s" "$LOCAL_VERSION" "$LATEST_VERSION" | sort -V | head -n 1)" != "$LATEST_VERSION" ]; then
        log "A new version ($LATEST_VERSION) is available. Current version: $LOCAL_VERSION."
        log "Updating to the latest version..."

        # Download and unzip the latest release
        ZIP_URL=$(echo "$RELEASE_DATA" | jq -r .zipball_url)
        ZIP_FILE="$SCRIPT_DIR/$LATEST_RELEASE.zip"

        CURRENT_STAGE="downloading and extracting"
        clean_stale_downloads
        curl -L -o "$ZIP_FILE" "$ZIP_URL"
        unzip -oqq "$ZIP_FILE" -d "$SCRIPT_DIR"

        # Determine the extracted release directory
        EXTRACTED_DIR=$(find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 -type d -name "iterativv-*" | head -n 1)
        if [ -z "$EXTRACTED_DIR" ]; then
            die "Could not determine the extracted release directory."
        fi

        log "Extracted release directory: $EXTRACTED_DIR"
        UPDATE_AVAILABLE=true
    else
        log "You are already using the latest version ($LATEST_VERSION)."
        UPDATE_AVAILABLE=false
    fi
fi

# Process update if available
if [ "$UPDATE_AVAILABLE" = "true" ]; then
    # Update files based on configuration
    CURRENT_STAGE="copying files"
    if [[ -n "$strategy_file" ]]; then
        update_files "Strategy" "$strategy_file" "$SCRIPT_DIR/.."
    fi
    update_blacklists "$SCRIPT_DIR/../configs"

    # Record the version only after every requested file has been copied.
    CURRENT_STAGE="recording version"
    printf '%s\n' "$LATEST_VERSION" > "$LOCAL_VERSION_FILE.tmp"
    mv -f "$LOCAL_VERSION_FILE.tmp" "$LOCAL_VERSION_FILE"
    log "Updated to version $LATEST_VERSION."

    # Cleanup old files
    CURRENT_STAGE="cleanup (files and version already updated)"
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
        CURRENT_STAGE="restarting Docker (files and version already updated)"
        log "Restarting Docker container..."
        docker compose -f "$SCRIPT_DIR/../docker-compose.yml" down
        docker compose -f "$SCRIPT_DIR/../docker-compose.yml" up -d
        log "Docker container restarted."
    else
        log "Docker Compose file not found. Skipping Docker restart."
    fi
fi
