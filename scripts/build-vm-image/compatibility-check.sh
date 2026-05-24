#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$SCRIPT_DIR/versions.env"

APP_VERSION="${1:-$VERSION}"
IMAGE_DIR="${2:-$PROJECT_ROOT/desktop/resources/vm-images}"

echo "=== DeerFlow Image Compatibility Check ==="
echo "App version: $APP_VERSION"
echo "Image directory: $IMAGE_DIR"
echo ""

ERRORS=0
WARNINGS=0

check_manifest() {
    local manifest_file="$1"
    local platform="$2"

    if [[ ! -f "$manifest_file" ]]; then
        echo "[SKIP] No manifest found for $platform at $manifest_file"
        return
    fi

    echo "--- Checking $platform manifest ---"

    local version compat_version min_app_version
    version=$(python3 -c "import json; print(json.load(open('$manifest_file')).get('version', 'unknown'))" 2>/dev/null || echo "unknown")
    compat_version=$(python3 -c "import json; print(json.load(open('$manifest_file')).get('compat_version', 0))" 2>/dev/null || echo "0")
    min_app_version=$(python3 -c "import json; print(json.load(open('$manifest_file')).get('min_app_version', '0.0.0'))" 2>/dev/null || echo "0.0.0")

    echo "  Image version: $version"
    echo "  Compat version: $compat_version"
    echo "  Min app version: $min_app_version"

    if [[ "$compat_version" != "$COMPAT_VERSION" ]]; then
        echo "  [ERROR] COMPAT_VERSION mismatch: image=$compat_version, expected=$COMPAT_VERSION"
        echo "  Action: You must update the VM image to a compatible version"
        ERRORS=$((ERRORS + 1))
    else
        echo "  [OK] COMPAT_VERSION matches"
    fi

    local app_major app_minor app_patch min_major min_minor min_patch
    IFS='.' read -r app_major app_minor app_patch <<< "$APP_VERSION"
    IFS='.' read -r min_major min_minor min_patch <<< "$min_app_version"

    if [[ $app_major -lt $min_major ]] || \
       [[ $app_major -eq $min_major && $app_minor -lt $min_minor ]] || \
       [[ $app_major -eq $min_major && $app_minor -eq $min_minor && $app_patch -lt $min_patch ]]; then
        echo "  [ERROR] App version $APP_VERSION is below minimum required $min_app_version"
        echo "  Action: Please update the application"
        ERRORS=$((ERRORS + 1))
    else
        echo "  [OK] App version satisfies minimum requirement"
    fi

    local image_file
    image_file=$(python3 -c "
import json
m = json.load(open('$manifest_file'))
files = m.get('files', {})
if 'rootfs' in files:
    print(files['rootfs'].get('name', ''))
elif 'file' in m:
    print(m['file'])
else:
    print('')
" 2>/dev/null || echo "")

    if [[ -n "$image_file" && -f "$IMAGE_DIR/$image_file" ]]; then
        local expected_sha256 actual_sha256
        expected_sha256=$(python3 -c "
import json
m = json.load(open('$manifest_file'))
files = m.get('files', {})
if 'rootfs' in files:
    print(files['rootfs'].get('sha256', ''))
elif 'sha256' in m:
    print(m['sha256'])
else:
    print('')
" 2>/dev/null || echo "")

        if command -v shasum &>/dev/null; then
            actual_sha256=$(shasum -a 256 "$IMAGE_DIR/$image_file" | cut -d' ' -f1)
        elif command -v sha256sum &>/dev/null; then
            actual_sha256=$(sha256sum "$IMAGE_DIR/$image_file" | cut -d' ' -f1)
        fi

        if [[ -n "$expected_sha256" && "$expected_sha256" != "$actual_sha256" ]]; then
            echo "  [ERROR] SHA256 mismatch for $image_file"
            echo "    Expected: $expected_sha256"
            echo "    Actual:   $actual_sha256"
            ERRORS=$((ERRORS + 1))
        elif [[ -n "$expected_sha256" ]]; then
            echo "  [OK] SHA256 verified for $image_file"
        fi
    else
        echo "  [WARN] Image file not found: $IMAGE_DIR/$image_file"
        WARNINGS=$((WARNINGS + 1))
    fi

    local size_bytes max_bytes
    size_bytes=$(python3 -c "
import json
m = json.load(open('$manifest_file'))
files = m.get('files', {})
if 'rootfs' in files:
    print(files['rootfs'].get('size_bytes', 0))
elif 'size_bytes' in m:
    print(m['size_bytes'])
else:
    print(0)
" 2>/dev/null || echo "0")

    local size_mb=$((size_bytes / 1024 / 1024))
    local max_mb
    case "$platform" in
        macos) max_mb=100 ;;
        wsl2) max_mb=80 ;;
        firecracker) max_mb=50 ;;
        *) max_mb=200 ;;
    esac

    if [[ $size_mb -gt $max_mb ]]; then
        echo "  [ERROR] Image size ${size_mb}MB exceeds maximum ${max_mb}MB"
        ERRORS=$((ERRORS + 1))
    else
        echo "  [OK] Image size ${size_mb}MB within limit ${max_mb}MB"
    fi

    echo ""
}

for manifest in "$IMAGE_DIR"/deerflow-*.manifest.json; do
    if [[ -f "$manifest" ]]; then
        platform=$(python3 -c "import json; print(json.load(open('$manifest')).get('platform', 'unknown'))" 2>/dev/null || echo "unknown")
        check_manifest "$manifest" "$platform"
    fi
done

echo "========================================="
echo "  Compatibility Check Summary"
echo "========================================="
echo "  Errors: $ERRORS"
echo "  Warnings: $WARNINGS"
echo ""

if [[ $ERRORS -gt 0 ]]; then
    echo "  RESULT: FAIL - Compatibility issues found"
    exit 1
else
    echo "  RESULT: PASS - All compatibility checks passed"
    exit 0
fi
