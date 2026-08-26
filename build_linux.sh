#!/usr/bin/env bash
# 리눅스(x86_64) 서버 배포용 패키지를 만든다.
# macOS에서는 PyInstaller가 크로스 컴파일을 지원하지 않으므로,
# Dockerfile.linux-build 로 linux/amd64 컨테이너 안에서 바이너리를 빌드한 뒤
# build.sh 와 동일한 방식으로 배포 패키지를 구성한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE_TAG="supertonic-linux-build"
CONTAINER_NAME="supertonic-linux-extract"
PKG_DIR="dist/supertonic-tts-pkg-linux_x86_64"
VERSION="$(date +%Y%m%d)"

echo "[1/4] 리눅스(x86_64) 컨테이너에서 바이너리 빌드..."
docker build --platform linux/amd64 -f Dockerfile.linux-build -t "$IMAGE_TAG" .

echo "[2/4] 빌드 결과물 추출..."
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker create --platform linux/amd64 --name "$CONTAINER_NAME" "$IMAGE_TAG" >/dev/null
mkdir -p build_pkg/dist-linux
docker cp "$CONTAINER_NAME:/src/build_pkg/dist-linux/supertonic-tts" build_pkg/dist-linux/
docker cp "$CONTAINER_NAME:/src/build_pkg/dist-linux/supertonic-api" build_pkg/dist-linux/
docker rm -f "$CONTAINER_NAME" >/dev/null

echo "[3/4] 배포 패키지 구성 → $PKG_DIR"
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/scripts" "$PKG_DIR/sounds" "$PKG_DIR/output" "$PKG_DIR/logs"

cp "build_pkg/dist-linux/supertonic-tts" "$PKG_DIR/"
cp "build_pkg/dist-linux/supertonic-api" "$PKG_DIR/"
cp config.yaml "$PKG_DIR/"
cp run_api.sh "$PKG_DIR/"
cp scripts/call_tts_api.sh "$PKG_DIR/scripts/"
cp scripts/*.txt "$PKG_DIR/scripts/" 2>/dev/null || true
cp -r sounds/. "$PKG_DIR/sounds/" 2>/dev/null || true
chmod +x "$PKG_DIR/supertonic-tts" "$PKG_DIR/supertonic-api" "$PKG_DIR/run_api.sh" "$PKG_DIR/scripts/call_tts_api.sh"

echo "[4/4] 아카이브 생성..."
TARBALL="dist/supertonic-tts-linux_x86_64-${VERSION}.tar.gz"
tar -C dist -czf "$TARBALL" "$(basename "$PKG_DIR")"

echo ""
echo "=== 빌드 완료 ==="
echo "패키지 디렉터리: $PKG_DIR"
echo "배포용 아카이브: $TARBALL"
file "$PKG_DIR/supertonic-api"
