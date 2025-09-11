#!/usr/bin/env sh
set -eu

### Prereqs:
## 1. A directory with the NFIX repo setup on the main branch to run via docker compose
## 2. Configure the localization from repo
## OPTIONAL: configure token and chatId on .env

NFI_PATH=
ENV_PATH=
FREQTRADE_IMAGE_UPDATE=false
FREQTRADE_IMAGE="freqtradeorg/freqtrade:stable"
PRUNE_IMAGES=false
TELEGRAM_NOTIFICATION=true

### Simple script that does the following:
## 1. Pull NFIX repo
## 2. Compare if have new commits
## 3. Send message to telegram if .env is configured
## 4. Stop and Start freqtrade via docker compose
######################################################

## FUNCTIONS
echo_timestamped() {
    printf '%s - %s\n' "$(date +"%Y-%m-%d %H:%M:%S")" "$*"
}

load_env() {
    env_file="${1:-.env}"
    if [ -f "$env_file" ]; then
        set -a
        . "$env_file"
        set +a
    else
        echo_timestamped "Error: $env_file not found"
        exit 1
    fi
}

escape_telegram_markdown() {
    printf '%s' "$1" | \
    command sed \
        -e 's/\\\([][_*()~`>#+=|{}.!-]\)/MDV2ESC\1/g' | \
    command sed \
        -e 's/`\([^`]*\)`/MDV2COPEN\1MDV2CCLOSE/g' \
        -e 's/\[\([^]]*\)\](\([^)]*\))/MDV2LOPEN\1MDV2LMID\2MDV2LCLOSE/g' \
        -e 's/!\[\([^]]*\)\](\([^)]*\))/MDV2EOPEN\1MDV2EMID\2MDV2ECLOSE/g' \
        -e 's/__\([^_]*\)__/MDV2UOPEN\1MDV2UCLOSE/g' \
        -e 's/\*\([^*]*\)\*/MDV2BOPEN\1MDV2BCLOSE/g' \
        -e 's/_\([^_]*\)_/MDV2IOPEN\1MDV2ICLOSE/g' \
        -e 's/~\([^~]*\)~/MDV2SOPEN\1MDV2SCLOSE/g' \
        -e 's/||\([^|]*\)||/MDV2POPEN\1MDV2PCLOSE/g' | \
    command sed \
        -e 's/\\/\\\\/g' \
        -e 's/[][_*()~`>#+=|{}.!-]/\\&/g' | \
    command sed \
        -e 's/MDV2COPEN/`/g'      -e 's/MDV2CCLOSE/`/g' \
        -e 's/MDV2LOPEN/[/g'      -e 's/MDV2LMID/](/g'     -e 's/MDV2LCLOSE/)/g' \
        -e 's/MDV2EOPEN/!\[/g'    -e 's/MDV2EMID/](/g'     -e 's/MDV2ECLOSE/)/g' \
        -e 's/MDV2UOPEN/__/g'     -e 's/MDV2UCLOSE/__/g' \
        -e 's/MDV2BOPEN/*/g'      -e 's/MDV2BCLOSE/*/g' \
        -e 's/MDV2IOPEN/_/g'      -e 's/MDV2ICLOSE/_/g' \
        -e 's/MDV2SOPEN/~/g'      -e 's/MDV2SCLOSE/~/g' \
        -e 's/MDV2POPEN/||/g'     -e 's/MDV2PCLOSE/||/g' \
        -e 's/MDV2ESC\\\([][_*()~`>#+=|{}.!-]\)/\\\1/g'
}

send_telegram_notification() {
    if ! command -v curl >/dev/null 2>&1; then
        echo_timestamped "Warning: curl not found, skipping telegram notification"
        return 0
    fi

    freqtrade_telegram_enabled=${FREQTRADE__TELEGRAM__ENABLED:-false}
    if [ "$freqtrade_telegram_enabled" = "false" ] || [ "$TELEGRAM_NOTIFICATION" = "false" ]; then
        return 0
    fi

    telegram_message=$(escape_telegram_markdown "$1")
    if [ -z "$telegram_message" ]; then
        echo_timestamped "Warning: message variable is empty, skipping telegram notification"
        return 0
    fi

    if [ -n "$FREQTRADE__TELEGRAM__TOKEN" ] && [ -n "$FREQTRADE__TELEGRAM__CHAT_ID" ]; then
        set +e
        curl_error=$({ command curl -sS --max-time 10 -X POST \
            --data-urlencode "text=${telegram_message}" \
            --data-urlencode "parse_mode=MarkdownV2" \
            --data "chat_id=${FREQTRADE__TELEGRAM__CHAT_ID}" \
            "https://api.telegram.org/bot${FREQTRADE__TELEGRAM__TOKEN}/sendMessage" 1>/dev/null; } 2>&1)
        rc=$?
        set -e
        if [ $rc -ne 0 ]; then
            echo_timestamped "Warning: failed to send telegram message: $curl_error"
            return 0
        fi
    fi
}

is_pid_running() {
    _pid="$1"
    [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null
}

short_digest() {
    _d="$1"
    if [ -z "$_d" ] || [ "$_d" = "none" ]; then
        printf '%s\n' "$_d"
        return 0
    fi
    case "$_d" in
        sha256:*) _h=${_d#sha256:} ;;
        *) _h="$_d" ;;
    esac
    printf '%s' "$_h" | LC_ALL=C command cut -c1-12
    printf '\n'
}

short_path_hash() {
    _in="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$_in" | command sha256sum | command cut -c1-10
        return 0
    fi
    if command -v md5sum >/dev/null 2>&1; then
        printf '%s' "$_in" | command md5sum | command cut -c1-10
        return 0
    fi
    if command -v shasum >/dev/null 2>&1; then
        printf '%s' "$_in" | command shasum -a 256 | command cut -c1-10
        return 0
    fi
    printf '%s' "$_in" | command sed -e 's/[^A-Za-z0-9]/_/g' | command cut -c1-10
}

create_lock() {
    _dir="$1"
    umask 077
    if command mkdir "$_dir" 2>/dev/null; then
        if ! printf '%d\n' "$$" >"$_dir/pid"; then
            rm -rf "$_dir" 2>/dev/null || true
            return 1
        fi
        return 0
    fi
    return 1
}

######################################################

if [ -z "$NFI_PATH" ]; then
    echo_timestamped "Error: NFI_PATH variable is empty"
    exit 1
fi

nfi_path_hash=$(short_path_hash "$NFI_PATH")
LOCKDIR="${TMPDIR:-/tmp}/nfx-docker-update.${nfi_path_hash}.lock.d"

if [ -d "$LOCKDIR" ]; then
    _oldpid=$(command sed -n '1p' "$LOCKDIR/pid" 2>/dev/null | tr -cd '0-9' || true)
    if [ -n "$_oldpid" ] && is_pid_running "$_oldpid"; then
        echo_timestamped "Error: already running for ${FREQTRADE_IMAGE} (pid ${_oldpid})"
        exit 1
    fi
    echo_timestamped "Warning: removing stale lock ${LOCKDIR} (pid ${_oldpid:-unknown})"
    rm -rf "$LOCKDIR" || true
fi

trap 'rm -rf "$LOCKDIR"' 0 HUP INT TERM QUIT

if ! create_lock "$LOCKDIR"; then
    echo_timestamped "Error: already running for ${FREQTRADE_IMAGE}"
    exit 1
fi

if [ -z "$ENV_PATH" ]; then
    ENV_PATH=$NFI_PATH
fi

if [ ! -d "$NFI_PATH" ]; then
    echo_timestamped "Error: NFI_PATH (${NFI_PATH}) is not a directory or does not exist"
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo_timestamped "Error: git not found in PATH"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo_timestamped "Error: docker not found in PATH"
    exit 1
fi

cd -- "$NFI_PATH" || exit 1

load_env "${ENV_PATH}/.env"

if ! command git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo_timestamped "Error: NFI_PATH (${NFI_PATH}) is not a git repository"
    exit 1
fi

echo_timestamped "Info: pulling updates from repo"
latest_local_commit=$(command git rev-parse HEAD)

stashed=false
if ! command git diff-index --quiet HEAD --; then
    stashed=true
    if ! command git stash push -u -m "nfi-update-$(date '+%Y%m%d%H%M%S')" >/dev/null 2>&1; then
        echo_timestamped "Error: failed to stash changes in NFIX repo"
        exit 1
    fi
fi

set +e
git_pull_error=$({ command git pull 1>/dev/null; } 2>&1)
rc=$?
set -e

if [ $rc -ne 0 ]; then
    echo_timestamped "Error: failed to pull from NFIX repo: $git_pull_error"
    if [ "$stashed" = "true" ]; then
        command git stash pop >/dev/null 2>&1 || true
    fi
    exit 1
fi

if [ "$stashed" = "true" ]; then
    set +e
    git_stash_error=$({ command git stash pop 1>/dev/null; } 2>&1)
    rc=$?
    set -e
    if [ $rc -ne 0 ]; then
        message="failed to unstash changes in NFIX repo: $git_stash_error"
        echo_timestamped "Error: $message"
        send_telegram_notification "$message"
        exit 1
    fi
fi

need_restart=false

latest_remote_commit=$(command git rev-parse HEAD)
if [ "$latest_local_commit" != "$latest_remote_commit" ]; then
    need_restart=true
    short_latest_remote_commit=$(printf %s "$latest_remote_commit" | command cut -c1-7)
    message="NFI was updated to commit: *${short_latest_remote_commit}*. Please wait for reload..."
    echo_timestamped "Info: $message"
    send_telegram_notification "$message"
else
    echo_timestamped "Info: NFI is up to date"
fi

# check ft image and update if needed
if [ "$FREQTRADE_IMAGE_UPDATE" = "true" ]; then
    echo_timestamped "Info: docker image pull for ${FREQTRADE_IMAGE}"
    local_digest=$(command docker image inspect --format='{{.Id}}' "$FREQTRADE_IMAGE" 2>/dev/null || printf '%s\n' 'none')
    if ! command docker image pull --quiet "$FREQTRADE_IMAGE" >/dev/null 2>&1; then
        echo_timestamped "Error: docker image pull failed for ${FREQTRADE_IMAGE}"
        exit 1
    fi
    remote_digest=$(command docker image inspect --format='{{.Id}}' "$FREQTRADE_IMAGE" 2>/dev/null || printf '%s\n' 'none')

    if [ "$local_digest" != "$remote_digest" ]; then
        need_restart=true
        short_local_digest=$(short_digest "$local_digest")
        short_remote_digest=$(short_digest "$remote_digest")
        message="docker image ${FREQTRADE_IMAGE} was updated (${short_local_digest} -> ${short_remote_digest}). Please wait for reload..."
        echo_timestamped "Info: $message"
        send_telegram_notification "$message"
    else
        echo_timestamped "Info: docker image ${FREQTRADE_IMAGE} is up to date"
    fi
fi

if [ "$need_restart" = "true" ]; then
    echo_timestamped "Info: restarting docker image ${FREQTRADE_IMAGE} with NFIX"
    if ! command docker compose --progress quiet down; then
        echo_timestamped "Error: docker compose down failed"
        exit 1
    fi
    if ! command docker compose --progress quiet up -d; then
        echo_timestamped "Error: docker compose up failed"
        exit 1
    fi
    echo_timestamped "Info: restarted docker image ${FREQTRADE_IMAGE} with NFIX"
    if [ "$PRUNE_IMAGES" = "true" ]; then
        echo_timestamped "Info: pruning unused docker images"
        command docker image prune -f >/dev/null 2>&1 || true
    fi
else
    echo_timestamped "Info: NFI and docker image ${FREQTRADE_IMAGE} are up to date, no restart needed"
fi

exit 0
