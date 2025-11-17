#!/bin/bash

###############################################################################
# NostalgiaForInfinity Git-based Update Script
###############################################################################
#
# This script automates the process of checking for updates from the main
# branch of the NFI repository (not releases), downloading changes,
# updating specified files, and optionally restarting a Docker container.
# It also supports sending Telegram notifications and can be configured to
# run periodically via a cron job.
#
# Features:
# - Monitors main branch for changes (not releases)
# - Only updates when actual file changes are detected
# - Saves user configuration for reuse
# - Optional Telegram notifications
# - Docker Compose integration for container restart
# - Comprehensive logging
#
# Initial setup:
# 1. Run the script manually to create the config file: ./check_branch_and_update.sh
# 2. The script will prompt you for configuration values
# 3. After config creation, set up a cron job: crontab -e
# 4. Add a line like: 0 * * * * /path/to/your/script/check_branch_and_update.sh
#    (runs every hour)
#
###############################################################################

# Do NOT exit on errors during config - only during runtime
set +e

# ============================================================================
# Get absolute script directory (works with cron and relative paths)
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# Color Codes
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# ============================================================================
# Constants and Variables
# ============================================================================

CONFIG_FILE="$SCRIPT_DIR/config.cfg"
LOCAL_COMMIT_FILE="$SCRIPT_DIR/commit.txt"
LOG_FILE="$SCRIPT_DIR/update.log"
GITHUB_USER="iterativv"
GITHUB_REPO="NostalgiaForInfinity"
GITHUB_BRANCH="main"
TEMP_DIR="$SCRIPT_DIR/.nfi_temp"
UPDATED_FILES_ARRAY=()
OLD_COMMIT=""
NEW_COMMIT=""

# Enable strict mode for runtime (after config)
RUNTIME_MODE=false

# ============================================================================
# Logging Functions
# ============================================================================

# Function: Print log message with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

# Function: Print error message and exit
log_error() {
    log "ERROR: $1"
    exit 1
}

# ============================================================================
# Dependency Check Functions
# ============================================================================

# Function: Check if a command/tool is installed
check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        log "Dependency '$1' is not installed. Please install it first."
        exit 1
    fi
}

# ============================================================================
# File Validation Functions
# ============================================================================

# Function: Validate file extensions
validate_file_extension() {
    local files="$1"
    local extension="$2"

    files=$(echo "$files" | tr ' ' ',')

    IFS=',' read -r -a files_array <<< "$files"
    for file in "${files_array[@]}"; do
        file=$(echo "$file" | xargs)
        if [[ ! "$file" == *"$extension" ]]; then
            return 1
        fi
    done
    return 0
}

# ============================================================================
# Resolve path to absolute if relative
# ============================================================================

resolve_path() {
    local path="$1"
    if [[ "$path" == /* ]]; then
        # Already absolute
        echo "$path"
    else
        # Make it absolute relative to script directory
        echo "$SCRIPT_DIR/$path"
    fi
}

# ============================================================================
# UI Helper Functions
# ============================================================================

# Function: Print colored text
cecho() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function: Print a separator line
print_sep() {
    cecho "$BLUE" "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Function: Print a small separator
print_sep_small() {
    cecho "$GRAY" "─────────────────────────────────────────────────────────────────────"
}

# Function: Print a section header
print_header() {
    local step=$1
    local title=$2
    echo ""
    print_sep
    cecho "$CYAN" "  ▶ STEP $step: $title"
    print_sep_small
}

# Function: Print a success message
print_ok() {
    cecho "$GREEN" "  ✓ $1"
}

# Function: Print a warning message
print_warn() {
    cecho "$YELLOW" "  ⚠ $1"
}

# Function: Print an info message
print_info() {
    cecho "$BLUE" "  ℹ $1"
}

# Function: Print input instruction
print_input() {
    cecho "$WHITE" "$1"
}

# Function: Yes/No prompt - FIXED VERSION
yes_no_prompt() {
    local prompt="$1"
    local default="$2"
    local response

    echo ""
    if [[ "$default" == "y" ]]; then
        read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE "$prompt (Y/n): ")" response
    else
        read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE "$prompt (y/N): ")" response
    fi

    # Trim whitespace and convert to lowercase
    response="$(echo "$response" | xargs | tr '[:upper:]' '[:lower:]')"

    # If empty, use default
    if [[ -z "$response" ]]; then
        response="$default"
    fi

    # Return 0 if yes, 1 if no
    if [[ "$response" == "y" ]]; then
        return 0
    else
        return 1
    fi
}

# ============================================================================
# Configuration Functions
# ============================================================================

# Function: Initialize configuration file interactively
create_config() {
    log "Config file not found. Creating a new one at $CONFIG_FILE."

    clear
    echo ""
    cecho "$MAGENTA" "╔════════════════════════════════════════════════════════════════════╗"
    cecho "$MAGENTA" "║                                                                    ║"
    cecho "$MAGENTA" "║        NostalgiaForInfinity Update Script Setup Wizard             ║"
    cecho "$MAGENTA" "║                                                                    ║"
    cecho "$MAGENTA" "╚════════════════════════════════════════════════════════════════════╝"

    echo ""

    # Step 1: Strategy Files (MULTIPLE ALLOWED)
    print_header "1/6" "REQUIRED - Strategy Files"
    print_input "  Which strategy files do you want to update?"
    print_info "Examples: NostalgiaForInfinityX7.py"
    print_warn "IMPORTANT: Separate with commas, NO SPACES! (e.g., file1.py,file2.py)"
    echo ""
    read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Strategy files (default: NostalgiaForInfinityX7.py): ')" strategy_file
    strategy_file=${strategy_file:-NostalgiaForInfinityX7.py}

    if ! validate_file_extension "$strategy_file" ".py"; then
        print_warn "Invalid file extension - must be .py"
        strategy_file="NostalgiaForInfinityX7.py"
    fi
    print_ok "Configured: $strategy_file"

    echo ""
    read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Destination directory (default: ../): ')" strategy_dest
    strategy_dest=${strategy_dest:-../}
    print_ok "Will save to: $strategy_dest"

    # Step 2: Configuration Files (MULTIPLE ALLOWED)
    print_header "2/6" "REQUIRED - Configuration JSON Files"
    print_input "  Which configuration files do you want to update?"
    print_info "Examples: blacklist-binance.json,pairlist-volume-binance-usdt.json"
    print_warn "IMPORTANT: Separate with commas, NO SPACES! (e.g., file1.json,file2.json)"
    print_info "All these files are stored in the configs/ folder"
    echo ""
    read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Config files (default: blacklist-binance.json): ')" config_files
    config_files=${config_files:-blacklist-binance.json}

    if ! validate_file_extension "$config_files" ".json"; then
        print_warn "Invalid file extension - must be .json"
        config_files="blacklist-binance.json"
    fi
    print_ok "Configured: $config_files"

    echo ""
    read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Destination directory (default: ../configs): ')" config_dest
    config_dest=${config_dest:-../configs}
    print_ok "Will save to: $config_dest"

    # Step 3: Ask if user wants Additional Files
    print_header "3/6" "OPTIONAL - Additional Files"
    print_input "  Do you want to monitor additional files?"

    cecho "$RED" "╔════════════════════════════════════════════════════════════════════╗"
    cecho "$RED" "║  IMPORTANT for Additional Files                                    ║"
    cecho "$RED" "╚════════════════════════════════════════════════════════════════════╝"
    print_warn "Your local file paths MUST EXACTLY MATCH the Git repository structure!"
    print_warn "IMPORTANT: Separate with commas ONLY, NO SPACES! (e.g., file1,file2)"
    print_warn "Example: If Git has 'tools/update.sh', you must add exactly 'tools/update.sh'"
    print_warn "         Root '../' + 'tools/update.sh' = '../tools/update.sh'"

    print_info "Examples: tools/update_nfx.sh"

    local additional_files=""
    local additional_root="../"

    if yes_no_prompt "Monitor additional files?" "n"; then
        # Set root directory
        echo ""
        print_input "  Set a root directory for additional files"
        print_info "Examples: ../ (parent directory - default)"
        print_info "All additional files will be relative to this directory"
        print_info "Example: if root is '../' and you add 'tools/update.sh'"
        print_info "         it will update '../tools/update.sh'"
        echo ""
        read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Root directory (default: ../): ')" additional_root
        additional_root=${additional_root:-../}
        print_ok "Root directory set to: $additional_root"

        # Add files
        echo ""
        print_input "  Add files relative to the root directory"
        print_warn "REMEMBER: Comma-separated, NO SPACES! (e.g., file1,file2,file3)"
        print_warn "WARNING: Do not add this update script itself!"
        print_info "Leave blank and press Enter when done"
        echo ""

        local file_count=0

        while true; do
            read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE "Additional file #$((file_count + 1)) (or press Enter to skip): ")" additional_file

            if [[ -z "$additional_file" ]]; then
                break
            fi

            if [[ -n "$additional_files" ]]; then
                additional_files+=",$additional_file"
            else
                additional_files="$additional_file"
            fi

            print_ok "Added: $additional_file"
            ((file_count++))
        done

        if [[ -n "$additional_files" ]]; then
            print_ok "Total additional files: $file_count"
            print_ok "All files: $additional_files"
        else
            print_info "No additional files added"
            additional_files=""
        fi
    else
        print_info "Additional files disabled"
        additional_files=""
    fi

    # Step 4: Docker Compose
    print_header "4/6" "OPTIONAL - Docker Compose"

    local docker_compose_path=""
    if yes_no_prompt "Do you want to restart Docker containers on update?" "y"; then
        echo ""
        read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Docker Compose file path (default: ../docker-compose.yml): ')" docker_compose_path
        docker_compose_path=${docker_compose_path:-../docker-compose.yml}
        print_ok "Docker path set to: $docker_compose_path"
    else
        print_info "Docker integration disabled"
    fi

    # Step 5: Cleanup
    print_header "5/6" "OPTIONAL - Cleanup"

    local cleanup_old_files="n"
    if yes_no_prompt "Clean up temporary files after update?" "y"; then
        cleanup_old_files="y"
        print_ok "Cleanup: Enabled"
    else
        cleanup_old_files="n"
        print_ok "Cleanup: Disabled"
    fi

    # Step 6: Telegram
    print_header "6/6" "OPTIONAL - Telegram Notifications"

    local telegram_bot_token=""
    local telegram_chat_id=""

    if yes_no_prompt "Enable Telegram notifications?" "n"; then
        echo ""
        print_input "  Enter your Telegram credentials:"
        read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Bot token: ')" telegram_bot_token

        if [[ -n "$telegram_bot_token" ]]; then
            read -p "$(cecho $CYAN '  ➜ ')$(cecho $WHITE 'Chat ID: ')" telegram_chat_id
            print_ok "Telegram notifications enabled"
        else
            print_warn "Token empty - Telegram disabled"
        fi
    else
        print_info "Telegram notifications disabled"
    fi

    # Save configuration
    cat <<EOF > "$CONFIG_FILE"
# NostalgiaForInfinity Update Script Configuration
# Generated: $(date)

# REQUIRED: Strategy files
strategy_file="$strategy_file"
strategy_dest="$strategy_dest"

# REQUIRED: Configuration JSON files
config_files="$config_files"
config_dest="$config_dest"

# OPTIONAL: Additional files
additional_files="$additional_files"
additional_root="$additional_root"

# OPTIONAL: Docker Compose
docker_compose_path="$docker_compose_path"

# OPTIONAL: Cleanup
cleanup_old_files="$cleanup_old_files"

# OPTIONAL: Telegram
telegram_bot_token="$telegram_bot_token"
telegram_chat_id="$telegram_chat_id"
EOF

    # Print Configuration Summary
    echo ""
    cecho "$MAGENTA" "╔════════════════════════════════════════════════════════════════════╗"
    cecho "$MAGENTA" "║                                                                    ║"
    cecho "$MAGENTA" "║                  CONFIGURATION SUMMARY                             ║"
    cecho "$MAGENTA" "║                                                                    ║"
    cecho "$MAGENTA" "╚════════════════════════════════════════════════════════════════════╝"

    echo ""
    cecho "$CYAN" "  📋 STRATEGY FILES"
    print_sep_small
    print_info "Files: $strategy_file"
    print_info "Destination: $strategy_dest"

    echo ""
    cecho "$CYAN" "  📋 CONFIG FILES (JSON)"
    print_sep_small
    print_info "Files: $config_files"
    print_info "Destination: $config_dest"

    echo ""
    cecho "$CYAN" "  📋 ADDITIONAL FILES"
    print_sep_small
    if [[ -n "$additional_files" ]]; then
        print_ok "Enabled"
        print_info "Files: $additional_files"
        print_info "Root Directory: $additional_root"
    else
        print_warn "Disabled"
    fi

    echo ""
    cecho "$CYAN" "  🐳 DOCKER COMPOSE"
    print_sep_small
    if [[ -n "$docker_compose_path" ]]; then
        print_ok "Enabled"
        print_info "Path: $docker_compose_path"
    else
        print_warn "Disabled"
    fi

    echo ""
    cecho "$CYAN" "  🧹 CLEANUP"
    print_sep_small
    if [[ "$cleanup_old_files" == "y" ]]; then
        print_ok "Enabled - Temp files will be deleted"
    else
        print_warn "Disabled - Temp files will be kept"
    fi

    echo ""
    cecho "$CYAN" "  📱 TELEGRAM NOTIFICATIONS"
    print_sep_small
    if [[ -n "$telegram_bot_token" && -n "$telegram_chat_id" ]]; then
        print_ok "Enabled"
        print_info "Bot Token: ${telegram_bot_token:0:10}..."
        print_info "Chat ID: $telegram_chat_id"
    else
        print_warn "Disabled"
    fi

    echo ""
    print_sep
    print_ok "Configuration saved to $CONFIG_FILE"
    print_info "To edit manually: nano $CONFIG_FILE"
    print_sep
    echo ""
}

# ============================================================================
# File Comparison Functions
# ============================================================================

files_are_identical() {
    local file1="$1"
    local file2="$2"

    if [ ! -f "$file1" ] || [ ! -f "$file2" ]; then
        return 1
    fi

    cmp -s "$file1" "$file2" 2>/dev/null
    return $?
}

# ============================================================================
# Telegram Notification Functions
# ============================================================================

add_updated_file() {
    local file="$1"

    for existing_file in "${UPDATED_FILES_ARRAY[@]}"; do
        if [[ "$existing_file" == "$file" ]]; then
            return 0
        fi
    done

    UPDATED_FILES_ARRAY+=("$file")
}

send_telegram_notification() {
    local message="$1"

    if [[ -z "$telegram_bot_token" || -z "$telegram_chat_id" ]]; then
        return 0
    fi

    log "Sending Telegram notification..."

    # disable_web_page_preview=true removes link previews
    curl -s -X POST "https://api.telegram.org/bot$telegram_bot_token/sendMessage" \
        -d "chat_id=$telegram_chat_id&text=$message&parse_mode=HTML&disable_web_page_preview=true" 2>/dev/null
}

# ============================================================================
# Git and Repository Functions
# ============================================================================

init_or_update_git_repo() {
    log "Setting up git repository..."

    if [ ! -d "$TEMP_DIR/.git" ]; then
        log "Cloning $GITHUB_REPO repository..."
        git clone --branch "$GITHUB_BRANCH" --depth 1 \
            "https://github.com/$GITHUB_USER/$GITHUB_REPO.git" "$TEMP_DIR" 2>&1 | tee -a "$LOG_FILE"

        if [ ! -d "$TEMP_DIR/.git" ]; then
            log_error "Failed to clone repository"
        fi
        log "Repository cloned successfully."
    else
        log "Updating repository..."
        # Fix git safe.directory issue - mark temp directory as safe
        git config --global --add safe.directory "$TEMP_DIR" 2>/dev/null || true
        (cd "$TEMP_DIR" && git fetch origin "$GITHUB_BRANCH" 2>&1 | tee -a "$LOG_FILE")

        if [ $? -ne 0 ]; then
            log "WARNING: Git fetch failed. Removing temp directory and retrying..."
            rm -rf "$TEMP_DIR" 2>/dev/null || true
            git clone --branch "$GITHUB_BRANCH" --depth 1 \
                "https://github.com/$GITHUB_USER/$GITHUB_REPO.git" "$TEMP_DIR" 2>&1 | tee -a "$LOG_FILE"

            if [ ! -d "$TEMP_DIR/.git" ]; then
                log_error "Failed to clone repository after retry"
            fi
        else
            log "Repository updated successfully."
        fi
    fi
}

get_remote_commit() {
    local commit_hash
    commit_hash=$(cd "$TEMP_DIR" && git rev-parse origin/"$GITHUB_BRANCH" 2>/dev/null)

    if [[ -z "$commit_hash" ]]; then
        commit_hash=$(cd "$TEMP_DIR" && git rev-parse HEAD 2>/dev/null)
    fi

    if [[ -z "$commit_hash" ]]; then
        log_error "Failed to retrieve commit hash"
    fi

    echo "$commit_hash"
}

get_changed_files() {
    local old_commit="$1"
    local new_commit="$2"

    if [[ "$old_commit" == "0" ]]; then
        log "First run detected - downloading all monitored files..."
        CHANGED_FILES=$(cd "$TEMP_DIR" && git ls-tree -r --name-only "$new_commit" 2>/dev/null)
    else
        log "Comparing commits: ${old_commit:0:8} -> ${new_commit:0:8}"
        # For shallow clones, use git show to get file list from each commit
        local old_files=$(cd "$TEMP_DIR" && git ls-tree -r --name-only "$old_commit" 2>/dev/null)
        local new_files=$(cd "$TEMP_DIR" && git ls-tree -r --name-only "$new_commit" 2>/dev/null)

        # Find differences between the two file lists
        CHANGED_FILES=$(comm -23 <(echo "$new_files" | sort) <(echo "$old_files" | sort))

        # If no additions, try to find modified files
        if [[ -z "$CHANGED_FILES" ]]; then
            CHANGED_FILES=$(comm -2 <(echo "$new_files" | sort) <(echo "$old_files" | sort))
        fi
    fi

    if [[ -z "$CHANGED_FILES" ]]; then
        return 1
    fi

    return 0
}

has_monitored_files_changed() {
    local monitored_files="$1"

    if [[ -z "$monitored_files" ]]; then
        return 1
    fi

    monitored_files=$(echo "$monitored_files" | tr ',' ' ')

    while IFS= read -r changed_file; do
        [[ -z "$changed_file" ]] && continue

        for monitored_file in $monitored_files; do
            monitored_file=$(echo "$monitored_file" | xargs)
            [[ -z "$monitored_file" ]] && continue

            if [[ "$changed_file" == *"$monitored_file" ]]; then
                return 0
            fi
        done
    done <<< "$CHANGED_FILES"

    return 1
}

copy_updated_files() {
    local monitored_files="$1"
    local destination="$2"
    local is_first_run="$3"

    if [[ -z "$monitored_files" ]]; then
        return
    fi

    monitored_files=$(echo "$monitored_files" | tr ',' ' ')

    # Resolve destination to absolute path
    destination=$(resolve_path "$destination")

    log "Copying updated files to: $destination"

    while IFS= read -r changed_file; do
        [[ -z "$changed_file" ]] && continue

        for monitored_file in $monitored_files; do
            monitored_file=$(echo "$monitored_file" | xargs)
            [[ -z "$monitored_file" ]] && continue

            if [[ "$changed_file" == *"$monitored_file" ]]; then
                local source_file="$TEMP_DIR/$changed_file"
                # Keep directory structure - don't use basename
                local dest_file="$destination/$monitored_file"

                if [ -f "$source_file" ]; then
                    # Create directory structure if needed
                    mkdir -p "$(dirname "$dest_file")" 2>/dev/null || true

                    # On first run, always update regardless of file content
                    if [[ "$is_first_run" == "yes" ]]; then
                        cp "$source_file" "$dest_file" 2>/dev/null || true
                        log "✓ Updated (first run): $monitored_file"
                        add_updated_file "$monitored_file"
                    # On subsequent runs, only update if files differ
                    elif [ -f "$dest_file" ] && files_are_identical "$source_file" "$dest_file"; then
                        log "  ○ Unchanged: $monitored_file"
                    else
                        cp "$source_file" "$dest_file" 2>/dev/null || true
                        log "✓ Updated: $monitored_file"
                        add_updated_file "$monitored_file"
                    fi
                fi
            fi
        done
    done <<< "$CHANGED_FILES"
}

# ============================================================================
# Docker Functions
# ============================================================================

stop_docker_compose() {
    local docker_file="$1"

    if [[ -z "$docker_file" ]]; then
        return 0
    fi

    # Resolve to absolute path
    docker_file=$(resolve_path "$docker_file")

    if [ ! -f "$docker_file" ]; then
        log "WARNING: Docker file not found: $docker_file"
        return 1
    fi

    log "Stopping Docker Compose..."

    docker compose -f "$docker_file" down 2>&1 | tee -a "$LOG_FILE"
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        log "✓ Docker stopped."
        return 0
    else
        log "WARNING: Docker stop failed"
        return 1
    fi
}

start_docker_compose() {
    local docker_file="$1"

    if [[ -z "$docker_file" ]]; then
        return 0
    fi

    # Resolve to absolute path
    docker_file=$(resolve_path "$docker_file")

    if [ ! -f "$docker_file" ]; then
        return 0
    fi

    log "Starting Docker Compose..."

    docker compose -f "$docker_file" up -d 2>&1 | tee -a "$LOG_FILE"
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        log "✓ Docker started."
        return 0
    else
        log "WARNING: Docker start failed"
        return 1
    fi
}

# ============================================================================
# Cleanup Functions
# ============================================================================

cleanup_temp_files() {
    if [[ "$cleanup_old_files" == "y" ]]; then
        log "Cleaning up temporary files..."

        if [ -d "$TEMP_DIR" ]; then
            rm -rf "$TEMP_DIR" 2>/dev/null || true
            log "✓ Cleanup complete."
        fi
    fi
}

# ============================================================================
# Main Script Logic
# ============================================================================

main() {
    log "========================================================================"
    log "NostalgiaForInfinity Git-based Update Script - Starting"
    log "========================================================================"

    # Check dependencies - only git and curl needed
    for dependency in git curl; do
        check_dependency "$dependency"
    done
    log "✓ All dependencies available."

    # Initialize config
    if [ ! -f "$CONFIG_FILE" ]; then
        create_config
        log "Configuration created. Please run the script again."
        exit 0
    fi

    log "Loading configuration..."
    source "$CONFIG_FILE" || log_error "Failed to load config"

    # Enable strict mode now that we have config
    set -e
    RUNTIME_MODE=true

    # Initialize commit file if not found
    local is_first_run="no"
    if [ ! -f "$LOCAL_COMMIT_FILE" ]; then
        log "Commit file not found. Creating a new one - FIRST RUN."
        echo "0" > "$LOCAL_COMMIT_FILE"
        is_first_run="yes"
    fi

    # Setup git
    init_or_update_git_repo

    # Get commits
    local_commit=$(cat "$LOCAL_COMMIT_FILE")
    remote_commit=$(get_remote_commit)
    OLD_COMMIT="$local_commit"
    NEW_COMMIT="$remote_commit"

    log "Local commit: ${local_commit:0:8}"
    log "Remote commit: ${remote_commit:0:8}"

    # On first run, always proceed with update
    if [[ "$local_commit" == "0" ]]; then
        log "FIRST RUN - Downloading all monitored files from remote..."
        is_first_run="yes"
    elif [ "$local_commit" == "$remote_commit" ]; then
        log "✓ No changes detected. Already on the latest commit."
        cleanup_temp_files
        exit 0
    fi

    log "Update needed - checking files..."

    # Get changed files
    if ! get_changed_files "$local_commit" "$remote_commit"; then
        log "No files found in changes."
        cleanup_temp_files
        exit 0
    fi

    # Check monitored files
    local all_monitored_files="$strategy_file $config_files $additional_files"

    if ! has_monitored_files_changed "$all_monitored_files"; then
        log "No monitored files found in changes."
        echo "$remote_commit" > "$LOCAL_COMMIT_FILE"
        cleanup_temp_files
        exit 0
    fi

    # Start update process
    log "========================================================================"
    log "UPDATE PROCESS STARTING"
    log "========================================================================"

    docker_stopped=false
    if [[ -n "$docker_compose_path" ]]; then
        if stop_docker_compose "$docker_compose_path"; then
            docker_stopped=true
        fi
    fi

    UPDATED_FILES_ARRAY=()

    # Update files
    [[ -n "$strategy_file" ]] && has_monitored_files_changed "$strategy_file" && \
        copy_updated_files "$strategy_file" "$strategy_dest" "$is_first_run"

    [[ -n "$config_files" ]] && has_monitored_files_changed "$config_files" && \
        copy_updated_files "$config_files" "$config_dest" "$is_first_run"

    [[ -n "$additional_files" ]] && has_monitored_files_changed "$additional_files" && \
        copy_updated_files "$additional_files" "$additional_root" "$is_first_run"

    # Update commit reference
    echo "$remote_commit" > "$LOCAL_COMMIT_FILE"
    log "✓ Commit reference updated to: ${remote_commit:0:8}"

    # Start docker again
    if [[ "$docker_stopped" == "true" ]]; then
        start_docker_compose "$docker_compose_path"
    fi

    # Send telegram
    if [[ -n "$telegram_bot_token" && -n "$telegram_chat_id" && ${#UPDATED_FILES_ARRAY[@]} -gt 0 ]]; then
        local msg="<b>NostalgiaForInfinity Update ✅</b>%0A"
        msg+="━━━━━━━━━━━━━━━━━━━━━━━━━━%0A"
        msg+="<b>Repository:</b> $GITHUB_REPO%0A"
        msg+="<b>Branch:</b> $GITHUB_BRANCH%0A"
        msg+="<b>Time:</b> $(date '+%Y-%m-%d %H:%M:%S')%0A"
        msg+="%0A"
        msg+="<b>📁 Updated Files:</b>%0A"

        for file in "${UPDATED_FILES_ARRAY[@]}"; do
            msg+="✅ $file%0A"
        done

        msg+="%0A"

        # Show diff link only on updates, not on first run
        if [[ "$is_first_run" != "yes" ]]; then
            msg+="🔗 https://github.com/$GITHUB_USER/$GITHUB_REPO/compare/${OLD_COMMIT:0:8}...${NEW_COMMIT:0:8}"
        fi

        send_telegram_notification "$msg"
    fi

    # Cleanup
    cleanup_temp_files

    log "========================================================================"
    log "✓ Update complete!"
    log "========================================================================"
}

# ============================================================================
# Script Entry Point
# ============================================================================

main

exit 0
