#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== multilingual-tts 설치 ==="

# venv 생성
if [ ! -f ".venv/bin/python3" ]; then
    echo "[1/3] 가상환경 생성..."
    python3 -m venv .venv
fi

# 패키지 설치
echo "[2/3] 패키지 설치..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "  완료"

# 모델 다운로드
echo "[3/3] Kokoro 모델 다운로드..."
mkdir -p models/kokoro

ONNX="models/kokoro/kokoro-v1.0.int8.onnx"
VOICES="models/kokoro/voices-v1.0.bin"
BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

if [ ! -f "$ONNX" ]; then
    echo "  kokoro-v1.0.int8.onnx 다운로드 중... (89MB)"
    wget -q --show-progress -O "$ONNX" "$BASE/kokoro-v1.0.int8.onnx"
else
    echo "  kokoro-v1.0.int8.onnx 이미 존재"
fi

if [ ! -f "$VOICES" ]; then
    echo "  voices-v1.0.bin 다운로드 중... (27MB)"
    wget -q --show-progress -O "$VOICES" "$BASE/voices-v1.0.bin"
else
    echo "  voices-v1.0.bin 이미 존재"
fi

echo ""
echo "=== 설치 완료 ==="
echo "사용법:"
echo "  .venv/bin/python tts.py --input scripts/korean.txt"
echo "  .venv/bin/python tts.py --text '안녕하세요' --lang ko"
echo "  .venv/bin/python tts.py --voices"
