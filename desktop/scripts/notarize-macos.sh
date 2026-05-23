#!/bin/bash
set -euo pipefail

echo "=== macOS Notarization ==="

DMG_PATH="${1:-}"
APPLE_ID="${APPLE_ID:-}"
APPLE_APP_PASSWORD="${APPLE_APP_PASSWORD:-}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-}"

if [ -z "$DMG_PATH" ]; then
    echo "Usage: $0 <path-to-dmg>"
    exit 1
fi

if [ -z "$APPLE_ID" ] || [ -z "$APPLE_APP_PASSWORD" ] || [ -z "$APPLE_TEAM_ID" ]; then
    echo "Error: Required environment variables not set"
    echo "  APPLE_ID          - Your Apple ID email"
    echo "  APPLE_APP_PASSWORD - App-specific password"
    echo "  APPLE_TEAM_ID     - Your Apple Team ID"
    exit 1
fi

if [ ! -f "$DMG_PATH" ]; then
    echo "Error: DMG not found at $DMG_PATH"
    exit 1
fi

echo "Verifying code signature before notarization..."
codesign --verify --deep --strict --verbose=2 "$DMG_PATH" || {
    echo "Error: Code signature verification failed"
    exit 1
}
echo "Signature OK"

echo "Submitting for notarization..."
xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait

echo "Stapling notarization ticket..."
xcrun stapler staple "$DMG_PATH"

echo "Verifying notarization..."
spctl --assess --type install "$DMG_PATH" && echo "Notarization PASSED" || echo "Notarization FAILED"

echo "Done."
