#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${SCRIPT_DIR}/.venv/bin/python"

HOST="127.0.0.1"
PORT=""
TEXT=""
FILENAME=""
VOICE=""
SPEED=""
LANG="ko"
HEALTH_ONLY=0

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Send a TTS request to the multilingual-tts API.

Required:
  -t, --text TEXT           Text to synthesize
  -f, --filename NAME       Output WAV filename (without path)

Optional:
  -v, --voice VOICE         Voice id (F1~F5 / M1~M5)
  -s, --speed SPEED         Speech speed (0.5 ~ 2.0)
  -l, --lang LANG           Language code (default: ko)
      --host HOST           API host (default: 127.0.0.1)
  -p, --port PORT           API port (default: config.yaml api.port)
      --health              Check /api/health only
  -h, --help                Show this help

Examples:
  $(basename "$0") -t "안녕하세요" -f greeting
  $(basename "$0") -t "Hello" -f hello_en -l en -v F3 -s 1.05
  $(basename "$0") --health
EOF
}

read_port_from_config() {
    if [ ! -x "$PYTHON" ]; then
        echo "9090"
        return
    fi
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

while [ $# -gt 0 ]; do
    case "$1" in
        -t|--text) TEXT="$2"; shift 2 ;;
        -f|--filename) FILENAME="$2"; shift 2 ;;
        -v|--voice) VOICE="$2"; shift 2 ;;
        -s|--speed) SPEED="$2"; shift 2 ;;
        -l|--lang) LANG="$2"; shift 2 ;;
        --host) HOST="$2"; shift 2 ;;
        -p|--port) PORT="$2"; shift 2 ;;
        --health) HEALTH_ONLY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "[error] unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [ -z "$PORT" ]; then
    PORT="$(read_port_from_config)"
fi

BASE_URL="http://${HOST}:${PORT}"

if [ "$HEALTH_ONLY" -eq 1 ]; then
    echo "[GET] ${BASE_URL}/api/health"
    curl -sS "${BASE_URL}/api/health"
    echo
    exit 0
fi

if [ -z "$TEXT" ] || [ -z "$FILENAME" ]; then
    echo "[error] --text and --filename are required" >&2
    usage
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "[error] curl is required" >&2
    exit 1
fi

if [ ! -x "$PYTHON" ]; then
    echo "[error] venv not found. run: bash setup.sh" >&2
    exit 1
fi

JSON="$("$PYTHON" - <<PY
import json

payload = {
    "text": ${TEXT@Q},
    "filename": ${FILENAME@Q},
    "lang": ${LANG@Q},
}
voice = ${VOICE@Q}
speed = ${SPEED@Q}
if voice:
    payload["voice"] = voice
if speed:
    payload["speed"] = float(speed)

print(json.dumps(payload, ensure_ascii=False))
PY
)"

echo "[POST] ${BASE_URL}/api/tts"
echo "       ${JSON}"

HTTP_CODE="$(curl -sS -w "%{http_code}" -o /tmp/call_tts_api_response.json \
    -X POST "${BASE_URL}/api/tts" \
    -H "Content-Type: application/json; charset=utf-8" \
    -d "$JSON")"

echo "HTTP ${HTTP_CODE}"
cat /tmp/call_tts_api_response.json
echo

if [ "$HTTP_CODE" != "200" ]; then
    exit 1
fi
