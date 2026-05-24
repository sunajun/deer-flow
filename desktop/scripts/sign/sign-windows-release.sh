#!/bin/bash
set -euo pipefail

CERT_FILE="${WIN_CERT_FILE:?WIN_CERT_FILE environment variable is required}"
CERT_PASSWORD="${WIN_CERT_PASSWORD:?WIN_CERT_PASSWORD environment variable is required}"
TIMESTAMP_SERVER="http://timestamp.digicert.com"

sign_binary() {
    local binary="$1"
    if [ -f "$binary" ]; then
        echo "Signing: $binary"
        signtool sign /fd SHA256 \
            /tr "$TIMESTAMP_SERVER" /td SHA256 \
            /f "$CERT_FILE" /p "$CERT_PASSWORD" \
            "$binary"
    fi
}

sign_directory() {
    local dir="$1"
    if [ -d "$dir" ]; then
        echo "Signing binaries in: $dir"
        find "$dir" -type f \( -name "*.exe" -o -name "*.dll" \) | while read -r binary; do
            sign_binary "$binary"
        done
    fi
}

DIST_DIR="${1:?Usage: $0 <path-to-dist-directory>}"

echo "=== Signing Python backend ==="
PYTHON_BACKEND=$(find "$DIST_DIR" -name "deerflow-backend.exe" -print -quit 2>/dev/null || true)
if [ -n "$PYTHON_BACKEND" ]; then
    sign_binary "$PYTHON_BACKEND"
fi

echo "=== Signing app binaries ==="
sign_directory "$DIST_DIR"

echo "=== Signing NSIS installer ==="
INSTALLER=$(find "$DIST_DIR" -name "DeerFlow-Setup-*.exe" -print -quit 2>/dev/null || true)
if [ -n "$INSTALLER" ]; then
    sign_binary "$INSTALLER"
    echo "Installer signed: $INSTALLER"
else
    echo "Warning: No installer found to sign"
fi

echo "=== Signing complete ==="
