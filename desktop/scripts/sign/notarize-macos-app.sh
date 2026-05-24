#!/bin/bash
set -euo pipefail

APP_PATH="${1:?Usage: $0 <path-to-DeerFlow.app>}"
IDENTITY="${APPLE_SIGNING_IDENTITY:-Developer ID Application: DeerFlow Team}"
ENTITLEMENTS="${2:-$(dirname "$0")/../../assets/entitlements.mac.plist}"
ENTITLEMENTS_INHERIT="${3:-$(dirname "$0")/../../assets/entitlements.mac.inherit.plist}"
SANDBOX_ENTITLEMENTS="${4:-$(dirname "$0")/../../assets/entitlements.sandbox.plist}"

if [ ! -d "$APP_PATH" ]; then
    echo "Error: App not found at $APP_PATH"
    exit 1
fi

echo "=== Signing embedded binaries ==="
find "$APP_PATH/Contents/Resources" -type f \( -name "*.dylib" -o -name "*.so" -perm +111 \) \
    -exec codesign --force --options runtime \
    --entitlements "$ENTITLEMENTS_INHERIT" \
    --sign "$IDENTITY" {} \;

echo "=== Signing Swift CLI ==="
SWIFT_CLI="$APP_PATH/Contents/Resources/DeerFlowSandboxCLI"
if [ -f "$SWIFT_CLI" ]; then
    codesign --force --options runtime \
        --entitlements "$SANDBOX_ENTITLEMENTS" \
        --sign "$IDENTITY" \
        "$SWIFT_CLI"
fi

echo "=== Signing Python backend binary ==="
PYTHON_BACKEND="$APP_PATH/Contents/Resources/python-backend/deerflow-backend"
if [ -f "$PYTHON_BACKEND" ]; then
    codesign --force --options runtime \
        --sign "$IDENTITY" \
        "$PYTHON_BACKEND"
fi

echo "=== Signing main app ==="
codesign --force --options runtime \
    --entitlements "$ENTITLEMENTS" \
    --sign "$IDENTITY" \
    "$APP_PATH"

echo "=== Verifying signature ==="
codesign --verify --deep --strict "$APP_PATH"
echo "Signature verified successfully"

echo "=== Notarizing ==="
DMG_PATH="${APP_PATH%.app}.dmg"
if [ ! -f "$DMG_PATH" ]; then
    echo "Creating DMG for notarization..."
    hdiutil create "$DMG_PATH" -srcfolder "$APP_PATH" -volname "DeerFlow"
fi

echo "Submitting for notarization..."
xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait

echo "=== Stapling notarization ticket ==="
xcrun stapler staple "$DMG_PATH"

echo "=== Notarization complete ==="
spctl --assess --type open --context context:primary-signature "$APP_PATH" || true
