#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$SCRIPT_DIR/versions.env"

IMAGE_DIR="${1:-$PROJECT_ROOT/desktop/resources/vm-images}"

ERRORS=0
WARNINGS=0
CHECKS=0

pass() {
    CHECKS=$((CHECKS + 1))
    echo "  [PASS] $1"
}

fail() {
    ERRORS=$((ERRORS + 1))
    CHECKS=$((CHECKS + 1))
    echo "  [FAIL] $1"
}

warn() {
    WARNINGS=$((WARNINGS + 1))
    echo "  [WARN] $1"
}

echo "=== DeerFlow VM Image Verification ==="
echo "Image directory: $IMAGE_DIR"
echo ""

if [[ ! -d "$IMAGE_DIR" ]]; then
    echo "[ERROR] Image directory does not exist: $IMAGE_DIR"
    exit 1
fi

echo "--- Checking manifest files ---"
MANIFEST_FOUND=0
for manifest in "$IMAGE_DIR"/deerflow-*.manifest.json; do
    if [[ -f "$manifest" ]]; then
        MANIFEST_FOUND=$((MANIFEST_FOUND + 1))
        platform=$(python3 -c "import json; print(json.load(open('$manifest')).get('platform', 'unknown'))" 2>/dev/null || echo "unknown")
        echo "  Found manifest for: $platform"

        python3 -c "
import json, sys
try:
    with open('$manifest') as f:
        m = json.load(f)
    required = ['version', 'platform', 'compat_version', 'min_app_version', 'build_date']
    missing = [k for k in required if k not in m]
    if missing:
        print(f'  Missing fields: {missing}')
        sys.exit(1)
    print(f'  All required fields present')
except Exception as e:
    print(f'  Error reading manifest: {e}')
    sys.exit(1)
" 2>/dev/null && pass "Manifest $platform valid" || fail "Manifest $platform invalid"
    fi
done

if [[ $MANIFEST_FOUND -eq 0 ]]; then
    warn "No platform manifests found"
else
    pass "$MANIFEST_FOUND manifest(s) found"
fi

echo ""
echo "--- Checking macOS image ---"
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    SUFFIX="arm64"
else
    SUFFIX="x86_64"
fi

MACOS_IMG="$IMAGE_DIR/deerflow-macos-${SUFFIX}.img.gz"
if [[ -f "$MACOS_IMG" ]]; then
    SIZE_BYTES=$(stat -f%z "$MACOS_IMG" 2>/dev/null || stat -c%s "$MACOS_IMG" 2>/dev/null || echo 0)
    SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
    if [[ $SIZE_MB -gt 100 ]]; then
        fail "macOS image size ${SIZE_MB}MB exceeds 100MB"
    else
        pass "macOS image size ${SIZE_MB}MB within 100MB limit"
    fi
else
    warn "macOS image not found: $MACOS_IMG"
fi

echo ""
echo "--- Checking WSL2 image ---"
WSL2_IMG="$IMAGE_DIR/deerflow-rootfs.tar.gz"
if [[ -f "$WSL2_IMG" ]]; then
    SIZE_BYTES=$(stat -f%z "$WSL2_IMG" 2>/dev/null || stat -c%s "$WSL2_IMG" 2>/dev/null || echo 0)
    SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
    if [[ $SIZE_MB -gt 80 ]]; then
        fail "WSL2 image size ${SIZE_MB}MB exceeds 80MB"
    else
        pass "WSL2 image size ${SIZE_MB}MB within 80MB limit"
    fi
else
    warn "WSL2 image not found: $WSL2_IMG"
fi

echo ""
echo "--- Checking Firecracker image ---"
FC_ROOTFS="$IMAGE_DIR/rootfs.ext4.gz"
FC_KERNEL="$IMAGE_DIR/vmlinux"

if [[ -f "$FC_ROOTFS" ]]; then
    SIZE_BYTES=$(stat -f%z "$FC_ROOTFS" 2>/dev/null || stat -c%s "$FC_ROOTFS" 2>/dev/null || echo 0)
    SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
    if [[ $SIZE_MB -gt 50 ]]; then
        fail "Firecracker rootfs size ${SIZE_MB}MB exceeds 50MB"
    else
        pass "Firecracker rootfs size ${SIZE_MB}MB within 50MB limit"
    fi
else
    warn "Firecracker rootfs not found: $FC_ROOTFS"
fi

if [[ -f "$FC_KERNEL" ]]; then
    SIZE_BYTES=$(stat -f%z "$FC_KERNEL" 2>/dev/null || stat -c%s "$FC_KERNEL" 2>/dev/null || echo 0)
    SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
    if [[ $SIZE_MB -gt 30 ]]; then
        fail "Firecracker kernel size ${SIZE_MB}MB exceeds 30MB"
    else
        pass "Firecracker kernel size ${SIZE_MB}MB within 30MB limit"
    fi
else
    warn "Firecracker kernel not found: $FC_KERNEL"
fi

echo ""
echo "--- Checking combined manifest ---"
COMBINED="$IMAGE_DIR/manifest.json"
if [[ -f "$COMBINED" ]]; then
    pass "Combined manifest.json exists"
else
    warn "Combined manifest.json not found"
fi

echo ""
echo "--- Running compatibility check ---"
if "$SCRIPT_DIR/compatibility-check.sh" "$VERSION" "$IMAGE_DIR"; then
    pass "Compatibility check passed"
else
    fail "Compatibility check failed"
fi

echo ""
echo "========================================="
echo "  Verification Summary"
echo "========================================="
echo "  Total checks: $CHECKS"
echo "  Passed: $((CHECKS - ERRORS))"
echo "  Failed: $ERRORS"
echo "  Warnings: $WARNINGS"
echo ""

if [[ $ERRORS -gt 0 ]]; then
    echo "  RESULT: FAIL"
    exit 1
else
    echo "  RESULT: PASS"
    exit 0
fi
