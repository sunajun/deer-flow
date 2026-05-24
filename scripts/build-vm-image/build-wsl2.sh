#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-deerflow-rootfs}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/desktop/resources/vm-images}"
OUTPUT_FILE="$OUTPUT_DIR/deerflow-rootfs.tar.gz"
VERSION="${VERSION:-0.1.0}"
DOCKERFILE="${DOCKERFILE:-$SCRIPT_DIR/Dockerfile.wsl2}"

echo "=== Building DeerFlow WSL2 Rootfs ==="
echo "Version: $VERSION"
echo "Output: $OUTPUT_FILE"
echo ""

mkdir -p "$OUTPUT_DIR"

echo "--- Building Docker image ---"
docker build \
  -t "$IMAGE_NAME:$VERSION" \
  -t "$IMAGE_NAME:latest" \
  -f "$DOCKERFILE" \
  --build-arg DEERFLOW_VERSION="$VERSION" \
  "$SCRIPT_DIR"

echo ""
echo "--- Creating container ---"
CONTAINER_ID=$(docker create "$IMAGE_NAME:$VERSION")
trap "docker rm -f $CONTAINER_ID 2>/dev/null || true" EXIT

echo ""
echo "--- Exporting rootfs ---"
docker export "$CONTAINER_ID" | gzip > "$OUTPUT_FILE.tmp"

mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"

echo ""
echo "--- Build complete ---"
FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo "File: $OUTPUT_FILE"
echo "Size: $FILE_SIZE"

SIZE_BYTES=$(stat -f%z "$OUTPUT_FILE" 2>/dev/null || stat -c%s "$OUTPUT_FILE" 2>/dev/null || echo 0)
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))

if [[ $SIZE_MB -gt 70 ]]; then
  echo "WARNING: Rootfs size (${SIZE_MB}MB) exceeds 70MB target"
else
  echo "Rootfs size (${SIZE_MB}MB) is within 70MB target"
fi

echo ""
echo "--- SHA256 ---"
if command -v shasum &>/dev/null; then
  shasum -a 256 "$OUTPUT_FILE"
elif command -v sha256sum &>/dev/null; then
  sha256sum "$OUTPUT_FILE"
fi
