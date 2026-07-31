#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

HOST="127.0.0.1"
PORT=""
TEXT=""
FILENAME=""
VOICE=""
SPEED=""
GAP=""
SOUND_EFFECT=""
LANG="ko"
HEALTH_ONLY=0
AUDIO_ONLY=0
OUTPUT_FILE=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Send a TTS request to the multilingual-tts API.

Required:
  -t, --text TEXT           Text to synthesize

For file-save mode (default):
  -f, --filename NAME       Output WAV filename (without path)

For audio response mode:
  -a, --audio [FILE]        Return WAV in HTTP response (optional output file)

Optional:
  -v, --voice VOICE         Voice id (F1~F5 / M1~M5)
  -s, --speed SPEED         Speech speed (0.5 ~ 2.0)
  -g, --gap GAP             Silence between lines/segments in seconds (default 0.4)
  -e, --sound-effect N      Bell wav repeats prepended before tts audio (0~5, default 0)
  -l, --lang LANG           Language code (default: ko)
      --host HOST           API host (default: 127.0.0.1)
  -p, --port PORT           API port (default: config.yaml api.port)
      --health              Check /api/health only
  -h, --help                Show this help

Examples:
  $(basename "$0") -t "안녕하세요" -f greeting
  $(basename "$0") -t "Hello" -f hello_en -l en -v F3 -s 1.05
  $(basename "$0") -t "안녕하세요" --audio greeting.wav
  $(basename "$0") --health
EOF
}

read_port_from_config() {
    local cfg="config.yaml"
    local port=""
    if [ -f "$cfg" ]; then
        port="$(sed -n '/^api:/,/^[^[:space:]]/{/port:/{s/.*port:[[:space:]]*\([0-9]\+\).*/\1/p}}' "$cfg" | head -1)"
    fi
    echo "${port:-9090}"
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
        -v|--voice) VOICE="$2"; shift 2 ;;
        -s|--speed) SPEED="$2"; shift 2 ;;
        -g|--gap) GAP="$2"; shift 2 ;;
        -e|--sound-effect) SOUND_EFFECT="$2"; shift 2 ;;
        -l|--lang) LANG="$2"; shift 2 ;;
        --host) HOST="$2"; shift 2 ;;
        -p|--port) PORT="$2"; shift 2 ;;
        --health) HEALTH_ONLY=1; shift ;;
        -a|--audio)
            AUDIO_ONLY=1
            if [ $# -gt 1 ] && [[ "$2" != -* ]]; then
                OUTPUT_FILE="$2"
                shift 2
            else
                shift
            fi
            ;;
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

if [ -z "$TEXT" ]; then
    echo "[error] --text is required" >&2
    usage
    exit 1
fi

if [ "$AUDIO_ONLY" -eq 0 ] && [ -z "$FILENAME" ]; then
    echo "[error] --filename is required unless --audio is used" >&2
    usage
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "[error] curl is required" >&2
    exit 1
fi

JSON="{\"text\":\"$(json_escape "$TEXT")\",\"lang\":\"$(json_escape "$LANG")\""
[ -n "$VOICE" ] && JSON+=",\"voice\":\"$(json_escape "$VOICE")\""
[ -n "$SPEED" ] && JSON+=",\"speed\":$SPEED"
[ -n "$GAP" ] && JSON+=",\"gap\":$GAP"
[ -n "$SOUND_EFFECT" ] && JSON+=",\"soundEffect\":$SOUND_EFFECT"
[ -n "$FILENAME" ] && JSON+=",\"filename\":\"$(json_escape "$FILENAME")\""
JSON+="}"

if [ "$AUDIO_ONLY" -eq 1 ]; then
    if [ -z "$OUTPUT_FILE" ]; then
        if [ -n "$FILENAME" ]; then
            OUTPUT_FILE="${FILENAME%.wav}.wav"
        else
            OUTPUT_FILE="tts.wav"
        fi
    fi

    echo "[POST] ${BASE_URL}/api/tts/audio"
    echo "       ${JSON}"

    HTTP_CODE="$(curl -sS -w "%{http_code}" -o "$OUTPUT_FILE" \
        -X POST "${BASE_URL}/api/tts/audio" \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "$JSON")"

    echo "HTTP ${HTTP_CODE}"
    if [ "$HTTP_CODE" = "200" ]; then
        echo "saved: ${OUTPUT_FILE}"
    else
        cat "$OUTPUT_FILE"
        echo
        exit 1
    fi
    exit 0
fi

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
