#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$SCRIPT_DIR/versions.env"

IMAGE_NAME="${IMAGE_NAME:-deerflow-rootfs}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/desktop/resources/vm-images}"
OUTPUT_FILE="$OUTPUT_DIR/deerflow-rootfs.tar.gz"
MANIFEST_FILE="$OUTPUT_DIR/deerflow-wsl2.manifest.json"
VERSION="${VERSION:-$VERSION}"
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
  --build-arg COMPAT_VERSION="$COMPAT_VERSION" \
  --build-arg MIN_APP_VERSION="$MIN_APP_VERSION" \
  --build-arg PYTHON_VERSION="$PYTHON_VERSION" \
  --build-arg NODE_VERSION="$NODE_VERSION" \
  --build-arg UBUNTU_VERSION="$UBUNTU_VERSION" \
  "$SCRIPT_DIR"

echo ""
echo "--- Creating container ---"
CONTAINER_ID=$(docker create "$IMAGE_NAME:$VERSION")
trap "docker rm -f $CONTAINER_ID 2>/dev/null || true" EXIT

echo ""
echo "--- Exporting rootfs ---"
docker export "$CONTAINER_ID" | gzip -9 > "$OUTPUT_FILE.tmp"

mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"

echo ""
echo "--- Build complete ---"
FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo "File: $OUTPUT_FILE"
echo "Size: $FILE_SIZE"

SIZE_BYTES=$(stat -f%z "$OUTPUT_FILE" 2>/dev/null || stat -c%s "$OUTPUT_FILE" 2>/dev/null || echo 0)
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))

if [[ $SIZE_MB -gt 80 ]]; then
  echo "WARNING: Rootfs size (${SIZE_MB}MB) exceeds 80MB maximum"
  exit 1
else
  echo "Rootfs size (${SIZE_MB}MB) is within 80MB maximum"
fi

echo ""
echo "--- Generating manifest ---"
SHA256=$(
  if command -v shasum &>/dev/null; then
    shasum -a 256 "$OUTPUT_FILE" | cut -d' ' -f1
  elif command -v sha256sum &>/dev/null; then
    sha256sum "$OUTPUT_FILE" | cut -d' ' -f1
  fi
)

cat > "$MANIFEST_FILE" <<EOF
{
  "version": "$VERSION",
  "platform": "wsl2",
  "format": "tar.gz",
  "file": "$(basename "$OUTPUT_FILE")",
  "size_bytes": $SIZE_BYTES,
  "sha256": "$SHA256",
  "compat_version": $COMPAT_VERSION,
  "min_app_version": "$MIN_APP_VERSION",
  "python_version": "$PYTHON_VERSION",
  "node_version": "$NODE_VERSION",
  "ubuntu_version": "$UBUNTU_VERSION",
  "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "Manifest: $MANIFEST_FILE"

echo ""
echo "--- SHA256 ---"
echo "$SHA256  $(basename "$OUTPUT_FILE")"
