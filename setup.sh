#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== multilingual-tts 설치 ==="

# venv 생성
if [ ! -f ".venv/bin/python3" ]; then
    echo "[1/2] 가상환경 생성..."
    python3 -m venv .venv
fi

# 패키지 설치
echo "[2/2] 패키지 설치 (Supertonic 모델은 첫 실행 시 자동 다운로드)..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "  완료"

echo ""
echo "=== 설치 완료 ==="
echo "사용법:"
echo "  .venv/bin/python tts.py --input scripts/korean.txt"
echo "  .venv/bin/python tts.py --text '안녕하세요' --lang ko"
echo "  .venv/bin/python tts.py --voices"
