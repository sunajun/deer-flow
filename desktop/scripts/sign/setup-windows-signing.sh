#!/bin/bash
set -euo pipefail

echo "=== Windows Code Signing Setup ==="

if [ -z "${WIN_CERT_FILE:-}" ]; then
    echo "Error: WIN_CERT_FILE environment variable not set"
    echo "Set it to the path of your Windows code signing certificate (.pfx)"
    exit 1
fi

if [ -z "${WIN_CERT_PASSWORD:-}" ]; then
    echo "Error: WIN_CERT_PASSWORD environment variable not set"
    echo "Set it to the password for your .pfx certificate"
    exit 1
fi

SIGNTOOL="${SIGNTOOL_PATH:-signtool.exe}"

echo "Certificate file: $WIN_CERT_FILE"
echo ""

sign_binary() {
    local binary="$1"
    echo "Signing: $binary"
    "$SIGNTOOL" sign \
        /fd SHA256 \
        /tr http://timestamp.digicert.com \
        /td SHA256 \
        /f "$WIN_CERT_FILE" \
        /p "$WIN_CERT_PASSWORD" \
        "$binary"

    if [ $? -eq 0 ]; then
        echo "  ✅ Signed successfully"
    else
        echo "  ❌ Signing failed"
        return 1
    fi
}

verify_binary() {
    local binary="$1"
    echo "Verifying: $binary"
    "$SIGNTOOL" verify /pa "$binary"

    if [ $? -eq 0 ]; then
        echo "  ✅ Signature verified"
    else
        echo "  ❌ Verification failed"
        return 1
    fi
}

echo ""
echo "To sign a binary manually:"
echo "  signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f cert.pfx /p PASSWORD binary.exe"
echo ""
echo "To verify a signature:"
echo "  signtool verify /pa binary.exe"
