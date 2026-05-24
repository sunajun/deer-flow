#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$SCRIPT_DIR/versions.env"

IMAGE_NAME="${IMAGE_NAME:-deerflow-macos-vm}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/desktop/resources/vm-images}"
VERSION="${VERSION:-$VERSION}"
DISK_SIZE_MB="${DISK_SIZE_MB:-8192}"
ARCH="${ARCH:-$(uname -m)}"

if [[ "$ARCH" == "arm64" ]]; then
    IMAGE_SUFFIX="arm64"
else
    IMAGE_SUFFIX="x86_64"
fi

OUTPUT_FILE="$OUTPUT_DIR/deerflow-macos-${IMAGE_SUFFIX}.img.gz"
MANIFEST_FILE="$OUTPUT_DIR/deerflow-macos-${IMAGE_SUFFIX}.manifest.json"

echo "=== Building DeerFlow macOS Virtualization.framework Image ==="
echo "Version: $VERSION"
echo "Architecture: $ARCH ($IMAGE_SUFFIX)"
echo "Output: $OUTPUT_FILE"
echo ""

mkdir -p "$OUTPUT_DIR"

echo "--- Building Docker image ---"
docker build \
    -t "$IMAGE_NAME:$VERSION" \
    -t "$IMAGE_NAME:latest" \
    -f "$SCRIPT_DIR/Dockerfile" \
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
echo "--- Exporting container filesystem ---"
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR; docker rm -f $CONTAINER_ID 2>/dev/null || true" EXIT

docker export "$CONTAINER_ID" | tar -x -C "$TMPDIR"

echo ""
echo "--- Creating disk image (${DISK_SIZE_MB}MB) ---"
DISK_FILE="$OUTPUT_DIR/deerflow-macos-${IMAGE_SUFFIX}.img"

if [[ "$ARCH" == "arm64" ]]; then
    dd if=/dev/zero of="$DISK_FILE" bs=1M count="$DISK_SIZE_MB" status=progress
else
    dd if=/dev/zero of="$DISK_FILE" bs=1M count="$DISK_SIZE_MB" status=progress
fi

if command -v mkfs.ext4 &>/dev/null; then
    mkfs.ext4 -F -q "$DISK_FILE"
else
    echo "Warning: mkfs.ext4 not found, using raw tar.gz format"
    cd "$TMPDIR"
    tar -czf "$OUTPUT_FILE" .
    cd "$SCRIPT_DIR"
    rm -rf "$TMPDIR"

    echo ""
    echo "--- Build complete (tar.gz format) ---"
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo "File: $OUTPUT_FILE"
    echo "Size: $FILE_SIZE"

    SIZE_BYTES=$(stat -f%z "$OUTPUT_FILE" 2>/dev/null || stat -c%s "$OUTPUT_FILE" 2>/dev/null || echo 0)
    SIZE_MB=$((SIZE_BYTES / 1024 / 1024))

    if [[ $SIZE_MB -gt 100 ]]; then
        echo "WARNING: Image size (${SIZE_MB}MB) exceeds 100MB maximum"
        exit 1
    else
        echo "Image size (${SIZE_MB}MB) is within 100MB maximum"
    fi

    echo ""
    echo "--- SHA256 ---"
    if command -v shasum &>/dev/null; then
        shasum -a 256 "$OUTPUT_FILE"
    elif command -v sha256sum &>/dev/null; then
        sha256sum "$OUTPUT_FILE"
    fi

    exit 0
fi

MOUNT_DIR=$(mktemp -d)
trap "umount $MOUNT_DIR 2>/dev/null || true; rm -rf $TMPDIR $MOUNT_DIR; rm -f $DISK_FILE; docker rm -f $CONTAINER_ID 2>/dev/null || true" EXIT

sudo mount -o loop "$DISK_FILE" "$MOUNT_DIR"
sudo cp -a "$TMPDIR"/. "$MOUNT_DIR"/

sudo umount "$MOUNT_DIR"
rmdir "$MOUNT_DIR"
MOUNT_DIR=""

echo ""
echo "--- Compressing image ---"
gzip -9 -c "$DISK_FILE" > "$OUTPUT_FILE"
rm -f "$DISK_FILE"

echo ""
echo "--- Build complete ---"
FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo "File: $OUTPUT_FILE"
echo "Size: $FILE_SIZE"

SIZE_BYTES=$(stat -f%z "$OUTPUT_FILE" 2>/dev/null || stat -c%s "$OUTPUT_FILE" 2>/dev/null || echo 0)
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))

if [[ $SIZE_MB -gt 100 ]]; then
    echo "WARNING: Image size (${SIZE_MB}MB) exceeds 100MB maximum"
    exit 1
else
    echo "Image size (${SIZE_MB}MB) is within 100MB maximum"
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
  "platform": "macos",
  "architecture": "$IMAGE_SUFFIX",
  "format": "img.gz",
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
