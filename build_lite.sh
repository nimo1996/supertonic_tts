#!/usr/bin/env bash
# config.yaml 없이 동작하는 최소 배포판을 만든다.
# PyInstaller로 api_lite.py를 단일 실행파일로 컴파일한 뒤,
# 실행파일 + sounds/ + 호출 스크립트만으로 dist/ 아래에 배치한다.
# (voice/speed/steps/sample_rate/gain 등은 api_lite.py에 고정값으로 박혀 있음)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PY=".venv/bin/python"
BUILD_DIR="build_pkg"
SPEC_FILE="$BUILD_DIR/supertonic-lite.spec"
PKG_DIR="dist/tts-lite-pkg"
VERSION="$(date +%Y%m%d)"

if [ ! -x "$VENV_PY" ]; then
    echo "[오류] .venv 가 없습니다. 먼저 'bash setup.sh' 를 실행하세요." >&2
    exit 1
fi

echo "[1/4] PyInstaller 설치 확인..."
"$VENV_PY" -m pip show pyinstaller >/dev/null 2>&1 || "$VENV_PY" -m pip install -q pyinstaller

echo "[2/4] 바이너리 빌드 (tts-api-lite)..."
"$VENV_PY" -m PyInstaller "$SPEC_FILE" --clean --noconfirm \
    --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/work"

echo "[3/4] 배포 패키지 구성 → $PKG_DIR"
# 실행파일은 패키지 루트에 직접 둔다 (base_dir()이 실행파일 위치 기준으로
# sounds/output 을 찾으므로, 하위 폴더에 넣으면 안 됨). config.yaml은 포함하지 않는다.
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/scripts" "$PKG_DIR/sounds"

cp "$BUILD_DIR/dist/tts-api-lite" "$PKG_DIR/"
cp scripts/call_tts_api_lite.sh "$PKG_DIR/scripts/"
cp -r sounds/. "$PKG_DIR/sounds/" 2>/dev/null || true
cp docs/LITE_사용법.txt "$PKG_DIR/사용법.txt" 2>/dev/null || true
chmod +x "$PKG_DIR/tts-api-lite" "$PKG_DIR/scripts/call_tts_api_lite.sh"

echo "[4/4] 아카이브 생성..."
TARBALL="dist/tts-lite-${VERSION}.tar.gz"
tar -C dist -czf "$TARBALL" "$(basename "$PKG_DIR")"

echo ""
echo "=== lite 빌드 완료 ==="
echo "패키지 디렉터리: $PKG_DIR"
echo "배포용 아카이브: $TARBALL"
echo "실행: $PKG_DIR/tts-api-lite  (foreground, 0.0.0.0:9090)"
echo "호출: $PKG_DIR/scripts/call_tts_api_lite.sh -t \"안녕하세요\" -f greeting"
