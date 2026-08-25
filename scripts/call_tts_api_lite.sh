#!/usr/bin/env bash
set -euo pipefail

HOST="127.0.0.1"
PORT="9090"
TEXT=""
FILENAME=""
SOUND_EFFECT=""
HEALTH_ONLY=0

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Send a TTS request to the multilingual-tts lite API (supertonic-api-lite).
Voice/speed/quality/language are fixed server-side defaults — not configurable here.

Required:
  -t, --text TEXT           Text to synthesize
  -f, --filename NAME       Output WAV filename (without path)

Optional:
  -e, --sound-effect N      Bell wav repeats prepended before tts audio (0~10, default 0)
                            0: none, 1~5: captain_bell_1x.wav x N, 6~10: captain_bell_2x.wav x (N-5)
      --host HOST           API host (default: 127.0.0.1)
  -p, --port PORT           API port (default: 9090)
      --health              Check /api/health only
  -h, --help                Show this help

Examples:
  $(basename "$0") -t "안녕하세요" -f greeting
  $(basename "$0") -t "함장승함" -f bell -e 2
  $(basename "$0") --health
EOF
}

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -t|--text) TEXT="$2"; shift 2 ;;
        -f|--filename) FILENAME="$2"; shift 2 ;;
        -e|--sound-effect) SOUND_EFFECT="$2"; shift 2 ;;
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

BASE_URL="http://${HOST}:${PORT}"

if [ "$HEALTH_ONLY" -eq 1 ]; then
    echo "[GET] ${BASE_URL}/api/health"
    curl -sS "${BASE_URL}/api/health"
    echo
    exit 0
fi

if [ -z "$TEXT" ]; then
    echo "[error] --text is required" >&2
    usage
    exit 1
fi

if [ -z "$FILENAME" ]; then
    echo "[error] --filename is required" >&2
    usage
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "[error] curl is required" >&2
    exit 1
fi

JSON="{\"text\":\"$(json_escape "$TEXT")\",\"filename\":\"$(json_escape "$FILENAME")\""
[ -n "$SOUND_EFFECT" ] && JSON+=",\"soundEffect\":$SOUND_EFFECT"
JSON+="}"

echo "[POST] ${BASE_URL}/api/tts"
echo "       ${JSON}"

HTTP_CODE="$(curl -sS -w "%{http_code}" -o /tmp/call_tts_api_lite_response.json \
    -X POST "${BASE_URL}/api/tts" \
    -H "Content-Type: application/json; charset=utf-8" \
    -d "$JSON")"

echo "HTTP ${HTTP_CODE}"
cat /tmp/call_tts_api_lite_response.json
echo

if [ "$HTTP_CODE" != "200" ]; then
    exit 1
fi
