#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$SCRIPT_DIR/versions.env"

IMAGE_NAME="${IMAGE_NAME:-deerflow-firecracker-rootfs}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/desktop/resources/vm-images}"
ROOTFS_FILE="$OUTPUT_DIR/rootfs.ext4"
ROOTFS_GZ_FILE="$OUTPUT_DIR/rootfs.ext4.gz"
KERNEL_FILE="$OUTPUT_DIR/vmlinux"
MANIFEST_FILE="$OUTPUT_DIR/deerflow-firecracker.manifest.json"
VERSION="${VERSION:-$VERSION}"
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

echo ""
echo "--- Optimizing image size ---"
e2fsck -f -y "$ROOTFS_FILE.tmp" 2>/dev/null || true
resize2fs -M "$ROOTFS_FILE.tmp" 2>/dev/null || true

mv "$ROOTFS_FILE.tmp" "$ROOTFS_FILE"

echo ""
echo "--- Compressing rootfs ---"
gzip -9 -c "$ROOTFS_FILE" > "$ROOTFS_GZ_FILE"

echo ""
echo "--- Downloading Firecracker kernel ---"
KERNEL_URL="https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/vmlinuxs/vmlinux-${FIRECRACKER_KERNEL_VERSION}"

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
ROOTFS_GZ_SIZE=$(du -h "$ROOTFS_GZ_FILE" | cut -f1)
echo "Rootfs: $ROOTFS_FILE ($ROOTFS_SIZE)"
echo "Rootfs (compressed): $ROOTFS_GZ_FILE ($ROOTFS_GZ_SIZE)"

SIZE_BYTES=$(stat -c%s "$ROOTFS_GZ_FILE" 2>/dev/null || stat -f%z "$ROOTFS_GZ_FILE" 2>/dev/null || echo 0)
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))

if [[ $SIZE_MB -gt 50 ]]; then
    echo "WARNING: Compressed rootfs size (${SIZE_MB}MB) exceeds 50MB maximum"
    exit 1
else
    echo "Compressed rootfs size (${SIZE_MB}MB) is within 50MB maximum"
fi

if [[ -f "$KERNEL_FILE" ]]; then
    KERNEL_SIZE=$(du -h "$KERNEL_FILE" | cut -f1)
    echo "Kernel: $KERNEL_FILE ($KERNEL_SIZE)"

    KERNEL_BYTES=$(stat -c%s "$KERNEL_FILE" 2>/dev/null || stat -f%z "$KERNEL_FILE" 2>/dev/null || echo 0)
    KERNEL_MB=$((KERNEL_BYTES / 1024 / 1024))
    if [[ $KERNEL_MB -gt 30 ]]; then
        echo "WARNING: Kernel size (${KERNEL_MB}MB) exceeds 30MB maximum"
        exit 1
    fi
fi

echo ""
echo "--- Generating manifest ---"
ROOTFS_SHA256=$(
    if command -v sha256sum &>/dev/null; then
        sha256sum "$ROOTFS_GZ_FILE" | cut -d' ' -f1
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$ROOTFS_GZ_FILE" | cut -d' ' -f1
    fi
)

KERNEL_SHA256=""
if [[ -f "$KERNEL_FILE" ]]; then
    KERNEL_SHA256=$(
        if command -v sha256sum &>/dev/null; then
            sha256sum "$KERNEL_FILE" | cut -d' ' -f1
        elif command -v shasum &>/dev/null; then
            shasum -a 256 "$KERNEL_FILE" | cut -d' ' -f1
        fi
    )
fi

cat > "$MANIFEST_FILE" <<EOF
{
  "version": "$VERSION",
  "platform": "firecracker",
  "format": "rootfs.ext4.gz",
  "files": {
    "rootfs": {
      "name": "$(basename "$ROOTFS_GZ_FILE")",
      "size_bytes": $SIZE_BYTES,
      "sha256": "$ROOTFS_SHA256"
    },
    "kernel": {
      "name": "$(basename "$KERNEL_FILE")",
      "sha256": "$KERNEL_SHA256"
    }
  },
  "compat_version": $COMPAT_VERSION,
  "min_app_version": "$MIN_APP_VERSION",
  "python_version": "$PYTHON_VERSION",
  "node_version": "$NODE_VERSION",
  "ubuntu_version": "$UBUNTU_VERSION",
  "firecracker_version": "$FIRECRACKER_VERSION",
  "kernel_version": "$FIRECRACKER_KERNEL_VERSION",
  "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "Manifest: $MANIFEST_FILE"

echo ""
echo "--- SHA256 ---"
echo "$ROOTFS_SHA256  $(basename "$ROOTFS_GZ_FILE")"
if [[ -n "$KERNEL_SHA256" ]]; then
    echo "$KERNEL_SHA256  $(basename "$KERNEL_FILE")"
fi
