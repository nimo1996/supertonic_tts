#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.api.pid"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/api.log"
PYTHON="$SCRIPT_DIR/.venv/bin/python"
API_SCRIPT="$SCRIPT_DIR/api.py"

usage() {
    cat <<EOF
Usage: $(basename "$0") {start|stop|status|restart}

  start    Run API server in background
  stop     Stop background API server (including untracked orphan)
  status   Show process and health check result
  restart  Stop then start

Logs:  $LOG_FILE
PID:   $PID_FILE
EOF
}

read_port() {
    "$PYTHON" - <<'PY'
import yaml
from pathlib import Path

cfg_path = Path("config.yaml")
port = 9090
if cfg_path.exists():
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    port = int((data.get("api") or {}).get("port", port))
print(port)
PY
}

get_port_pid() {
    local port="$1"
    local pid=""

    if command -v ss >/dev/null 2>&1; then
        pid="$(ss -tlnp 2>/dev/null | awk -v port=":${port}" '
            $4 ~ port {
                if (match($0, /pid=([0-9]+)/, m)) { print m[1]; exit }
            }
        ')"
    elif command -v lsof >/dev/null 2>&1; then
        pid="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
    elif command -v fuser >/dev/null 2>&1; then
        pid="$(fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' | head -1 || true)"
    fi

    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "$pid"
    fi
}

is_our_api_pid() {
    local pid="$1"
    [ -r "/proc/$pid/cmdline" ] || return 1

    local cmdline cwd
    cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
    [[ "$cmdline" == *"api.py"* ]] || return 1

    if [[ "$cmdline" == *"$SCRIPT_DIR"* ]]; then
        return 0
    fi

    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    [ "$cwd" = "$SCRIPT_DIR" ]
}

managed_pid() {
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi
    local pid
    pid="$(cat "$PID_FILE")"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "$pid"
        return 0
    fi
    return 1
}

find_api_pid() {
    local port pid managed
    port="$(read_port)"

    if managed="$(managed_pid)"; then
        echo "$managed"
        return 0
    fi

    pid="$(get_port_pid "$port")"
    if [ -n "$pid" ] && is_our_api_pid "$pid"; then
        echo "$pid"
        return 0
    fi

    return 1
}

port_in_use() {
    local port="$1"
    [ -n "$(get_port_pid "$port")" ]
}

health_check() {
    local port="$1"
    curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://127.0.0.1:${port}/api/health" 2>/dev/null || echo "000"
}

stop_pid() {
    local pid="$1"
    kill "$pid" 2>/dev/null || true

    for _ in $(seq 1 20); do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.5
    done

    kill -9 "$pid" 2>/dev/null || true
}

cmd_start() {
    if [ ! -x "$PYTHON" ]; then
        echo "[error] venv not found. run: bash setup.sh" >&2
        exit 1
    fi
    if [ ! -f "$API_SCRIPT" ]; then
        echo "[error] api.py not found: $API_SCRIPT" >&2
        exit 1
    fi

    local port existing_pid
    port="$(read_port)"

    if existing_pid="$(find_api_pid)"; then
        echo "$existing_pid" >"$PID_FILE"
        echo "[info] already running (pid $existing_pid, port $port)"
        exit 0
    fi

    if port_in_use "$port"; then
        echo "[error] port $port is already in use by another process" >&2
        echo "        check with: ss -tlnp | grep :$port" >&2
        exit 1
    fi

    mkdir -p "$LOG_DIR"

    nohup "$PYTHON" "$API_SCRIPT" >>"$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" >"$PID_FILE"
    sleep 1

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "[error] failed to start. see log: $LOG_FILE" >&2
        rm -f "$PID_FILE"
        exit 1
    fi

    echo "[ok] started (pid $pid, port $port)"
    echo "     log: $LOG_FILE"
}

cmd_stop() {
    local port pid
    port="$(read_port)"

    if pid="$(find_api_pid)"; then
        stop_pid "$pid"
        rm -f "$PID_FILE"
        echo "[ok] stopped (pid $pid)"
        return 0
    fi

    rm -f "$PID_FILE"
    echo "[info] not running"
}

cmd_status() {
    local port http_code pid managed=0 orphan=0
    port="$(read_port)"

    if pid="$(managed_pid)"; then
        managed=1
    elif pid="$(get_port_pid "$port")" && is_our_api_pid "$pid"; then
        orphan=1
    else
        echo "process: stopped"
        echo "port:    $port (configured)"
        rm -f "$PID_FILE"
        exit 1
    fi

    http_code="$(health_check "$port")"

    if [ "$managed" -eq 1 ]; then
        echo "process: running (pid $pid, managed)"
    else
        echo "process: running (pid $pid, orphan - not in $PID_FILE)"
        echo "hint:    run '$(basename "$0") stop' or '$(basename "$0") start' to adopt"
    fi
    echo "port:    $port"
    echo "health:  HTTP $http_code"
    echo "log:     $LOG_FILE"
}

cmd_restart() {
    cmd_stop || true
    cmd_start
}

case "${1:-}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    status) cmd_status ;;
    restart) cmd_restart ;;
    *)
        usage
        exit 1
        ;;
esac
