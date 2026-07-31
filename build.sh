#!/usr/bin/env bash
# 소스코드를 노출하지 않는 배포용 패키지를 만든다.
# PyInstaller로 tts.py / api.py를 각각 단일 실행파일로 컴파일한 뒤,
# 실행에 필요한 설정/스크립트/리소스와 함께 dist/ 아래에 배치한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PY=".venv/bin/python"
BUILD_DIR="build_pkg"
SPEC_FILE="$BUILD_DIR/supertonic.spec"
PKG_DIR="dist/supertonic-tts-pkg"
VERSION="$(date +%Y%m%d)"

if [ ! -x "$VENV_PY" ]; then
    echo "[오류] .venv 가 없습니다. 먼저 'bash setup.sh' 를 실행하세요." >&2
    exit 1
fi

echo "[1/4] PyInstaller 설치 확인..."
"$VENV_PY" -m pip show pyinstaller >/dev/null 2>&1 || "$VENV_PY" -m pip install -q pyinstaller

echo "[2/4] 바이너리 빌드 (supertonic-tts, supertonic-api)..."
"$VENV_PY" -m PyInstaller "$SPEC_FILE" --clean --noconfirm \
    --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/work"

echo "[3/4] 배포 패키지 구성 → $PKG_DIR"
# 실행파일은 패키지 루트에 직접 둔다 (base_dir()이 실행파일 위치 기준으로
# config.yaml/output/logs 를 찾으므로, 하위 폴더에 넣으면 안 됨).
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/scripts" "$PKG_DIR/sounds" "$PKG_DIR/output" "$PKG_DIR/logs"

cp "$BUILD_DIR/dist/supertonic-tts" "$PKG_DIR/"
cp "$BUILD_DIR/dist/supertonic-api" "$PKG_DIR/"
cp config.yaml "$PKG_DIR/"
cp run_api.sh "$PKG_DIR/"
cp scripts/call_tts_api.sh "$PKG_DIR/scripts/"
cp scripts/*.txt "$PKG_DIR/scripts/" 2>/dev/null || true
cp -r sounds/. "$PKG_DIR/sounds/" 2>/dev/null || true
# cp docs/INSTALL.md docs/OPERATIONS.md "$PKG_DIR/" 2>/dev/null || true
chmod +x "$PKG_DIR/supertonic-tts" "$PKG_DIR/supertonic-api" "$PKG_DIR/run_api.sh" "$PKG_DIR/scripts/call_tts_api.sh"

echo "[4/4] 아카이브 생성..."
TARBALL="dist/supertonic-tts-${VERSION}.tar.gz"
tar -C dist -czf "$TARBALL" "$(basename "$PKG_DIR")"

echo ""
echo "=== 빌드 완료 ==="
echo "패키지 디렉터리: $PKG_DIR"
echo "배포용 아카이브: $TARBALL"
echo "(.py 소스 파일은 포함되지 않았습니다 — 컴파일된 실행파일만 배포하세요)"
