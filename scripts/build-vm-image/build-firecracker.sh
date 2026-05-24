#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-deerflow-firecracker-rootfs}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/desktop/resources/vm-images}"
ROOTFS_FILE="$OUTPUT_DIR/rootfs.ext4"
KERNEL_FILE="$OUTPUT_DIR/vmlinux"
VERSION="${VERSION:-0.1.0}"
ROOTFS_SIZE_MB="${ROOTFS_SIZE_MB:-512}"

echo "=== Building DeerFlow Firecracker Rootfs ==="
echo "Version: $VERSION"
echo "Output: $ROOTFS_FILE"
echo ""

mkdir -p "$OUTPUT_DIR"

echo "--- Building Docker image ---"
docker build \
    -t "$IMAGE_NAME:$VERSION" \
    -t "$IMAGE_NAME:latest" \
    -f "$SCRIPT_DIR/Dockerfile.firecracker" \
    --build-arg DEERFLOW_VERSION="$VERSION" \
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
echo "--- Creating ext4 image (${ROOTFS_SIZE_MB}MB) ---"
dd if=/dev/zero of="$ROOTFS_FILE.tmp" bs=1M count="$ROOTFS_SIZE_MB" status=progress
mkfs.ext4 -F -q "$ROOTFS_FILE.tmp"

echo ""
echo "--- Copying files to image ---"
MOUNT_DIR=$(mktemp -d)
trap "umount $MOUNT_DIR 2>/dev/null || true; rm -rf $TMPDIR $MOUNT_DIR; docker rm -f $CONTAINER_ID 2>/dev/null || true" EXIT

sudo mount -o loop "$ROOTFS_FILE.tmp" "$MOUNT_DIR"
sudo cp -a "$TMPDIR"/. "$MOUNT_DIR"/

sudo umount "$MOUNT_DIR"
rmdir "$MOUNT_DIR"
MOUNT_DIR=""

mv "$ROOTFS_FILE.tmp" "$ROOTFS_FILE"

echo ""
echo "--- Optimizing image size ---"
e2fsck -f -y "$ROOTFS_FILE" 2>/dev/null || true
resize2fs -M "$ROOTFS_FILE" 2>/dev/null || true

echo ""
echo "--- Downloading Firecracker kernel ---"
FC_RELEASE="${FC_RELEASE:-v1.8.0}"
KERNEL_URL="https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/vmlinuxs/vmlinux-5.10"

if [[ ! -f "$KERNEL_FILE" ]]; then
    echo "Downloading pre-built kernel from $KERNEL_URL"
    curl -fSL -o "$KERNEL_FILE" "$KERNEL_URL"
    chmod +x "$KERNEL_FILE"
else
    echo "Kernel already exists at $KERNEL_FILE"
fi

echo ""
echo "--- Build complete ---"
ROOTFS_SIZE=$(du -h "$ROOTFS_FILE" | cut -f1)
echo "Rootfs: $ROOTFS_FILE ($ROOTFS_SIZE)"

SIZE_BYTES=$(stat -c%s "$ROOTFS_FILE" 2>/dev/null || stat -f%z "$ROOTFS_FILE" 2>/dev/null || echo 0)
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))

if [[ $SIZE_MB -gt 50 ]]; then
    echo "WARNING: Rootfs size (${SIZE_MB}MB) exceeds 50MB target"
    echo "Consider removing unnecessary packages or using Alpine-based rootfs"
else
    echo "Rootfs size (${SIZE_MB}MB) is within 50MB target"
fi

if [[ -f "$KERNEL_FILE" ]]; then
    KERNEL_SIZE=$(du -h "$KERNEL_FILE" | cut -f1)
    echo "Kernel: $KERNEL_FILE ($KERNEL_SIZE)"
fi

echo ""
echo "--- SHA256 ---"
if command -v sha256sum &>/dev/null; then
    sha256sum "$ROOTFS_FILE"
    [[ -f "$KERNEL_FILE" ]] && sha256sum "$KERNEL_FILE"
elif command -v shasum &>/dev/null; then
    shasum -a 256 "$ROOTFS_FILE"
    [[ -f "$KERNEL_FILE" ]] && shasum -a 256 "$KERNEL_FILE"
fi
