#!/bin/bash
set -euo pipefail

echo "=== macOS Code Signing Setup ==="

if [ -z "${DEVELOPER_ID_P12:-}" ]; then
    echo "Error: DEVELOPER_ID_P12 environment variable not set"
    echo "Set it to the path of your Developer ID Application .p12 certificate file"
    exit 1
fi

if [ -z "${CERT_PASSWORD:-}" ]; then
    echo "Error: CERT_PASSWORD environment variable not set"
    echo "Set it to the password for your .p12 certificate"
    exit 1
fi

KEYCHAIN_PATH="$HOME/Library/Keychains/build.keychain"
KEYCHAIN_PASSWORD="deerflow-build-$(date +%s)"

echo "Creating build keychain..."
security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"

echo "Importing Developer ID certificate..."
security import "$DEVELOPER_ID_P12" \
    -k "$KEYCHAIN_PATH" \
    -P "$CERT_PASSWORD" \
    -T /usr/bin/codesign \
    -T /usr/bin/productsign

echo "Setting partition list..."
security set-key-partition-list \
    -S apple-tool:,apple:,codesign: \
    -s -k "$KEYCHAIN_PASSWORD" \
    "$KEYCHAIN_PATH"

echo ""
echo "Verifying certificate..."
security find-identity -v -p codesigning "$KEYCHAIN_PATH"

echo ""
echo "Certificate imported successfully."
echo ""
echo "To sign a binary, run:"
echo "  codesign --force --deep --options=runtime --entitlements assets/entitlements.mac.plist --sign 'Developer ID Application: DeerFlow Team (XXXXXXXXXX)' <binary>"
echo ""
echo "To verify a signature:"
echo "  codesign --verify --deep --strict --verbose=2 <binary>"
echo "  codesign -dvvv <binary>"
