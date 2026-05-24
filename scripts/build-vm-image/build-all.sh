#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$SCRIPT_DIR/versions.env"

PLATFORMS="${PLATFORMS:-macos,wsl2,firecracker}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/desktop/resources/vm-images}"
VERSION="${VERSION:-$VERSION}"

FAILED=()
BUILT=()

echo "========================================="
echo "  DeerFlow VM Image Builder - All Platforms"
echo "  Version: $VERSION"
echo "  Platforms: $PLATFORMS"
echo "========================================="
echo ""

mkdir -p "$OUTPUT_DIR"

IFS=',' read -ra PLATFORM_LIST <<< "$PLATFORMS"

for platform in "${PLATFORM_LIST[@]}"; do
    platform=$(echo "$platform" | xargs)
    echo ""
    echo ">>> Building platform: $platform"
    echo ""

    case "$platform" in
        macos)
            if "$SCRIPT_DIR/build-macos.sh"; then
                BUILT+=("macos")
                echo ">>> macOS build: SUCCESS"
            else
                FAILED+=("macos")
                echo ">>> macOS build: FAILED"
            fi
            ;;
        wsl2)
            if "$SCRIPT_DIR/build-wsl2.sh"; then
                BUILT+=("wsl2")
                echo ">>> WSL2 build: SUCCESS"
            else
                FAILED+=("wsl2")
                echo ">>> WSL2 build: FAILED"
            fi
            ;;
        firecracker)
            if "$SCRIPT_DIR/build-firecracker.sh"; then
                BUILT+=("firecracker")
                echo ">>> Firecracker build: SUCCESS"
            else
                FAILED+=("firecracker")
                echo ">>> Firecracker build: FAILED"
            fi
            ;;
        *)
            echo ">>> Unknown platform: $platform (skipping)"
            ;;
    esac
done

echo ""
echo "========================================="
echo "  Build Summary"
echo "========================================="

if [[ ${#BUILT[@]} -gt 0 ]]; then
    echo "  Successful: ${BUILT[*]}"
fi

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo "  Failed: ${FAILED[*]}"
    echo ""
    echo "  Some builds failed. Check output above for details."
    exit 1
fi

echo ""
echo "  All builds successful!"
echo ""

echo "--- Generating combined manifest ---"
COMBINED_MANIFEST="$OUTPUT_DIR/manifest.json"

python3 -c "
import json, glob, os

output_dir = '$OUTPUT_DIR'
manifests = {}
for f in sorted(glob.glob(os.path.join(output_dir, 'deerflow-*.manifest.json'))):
    with open(f) as fh:
        m = json.load(fh)
        platform = m.get('platform', 'unknown')
        manifests[platform] = m

combined = {
    'version': '$VERSION',
    'build_date': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'platforms': manifests
}

with open(os.path.join(output_dir, 'manifest.json'), 'w') as fh:
    json.dump(combined, fh, indent=2)

print('Combined manifest written to manifest.json')
" 2>/dev/null || echo "Warning: Could not generate combined manifest (python3 not available)"

echo ""
echo "--- Output files ---"
ls -lh "$OUTPUT_DIR"/ 2>/dev/null || true
