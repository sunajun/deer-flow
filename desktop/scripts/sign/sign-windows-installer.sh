#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

WIN_CERT_FILE="${WIN_CERT_FILE:-}"
WIN_CERT_PASSWORD="${WIN_CERT_PASSWORD:-}"
SIGNING_HASH="${SIGNING_HASH:-SHA256}"
TIMESTAMP_SERVER="${TIMESTAMP_SERVER:-http://timestamp.digicert.com}"

if [[ -z "$WIN_CERT_FILE" ]]; then
  echo "ERROR: WIN_CERT_FILE environment variable is not set"
  echo "Set it to the path of your code signing certificate (.pfx/.p12)"
  exit 1
fi

if [[ ! -f "$WIN_CERT_FILE" ]]; then
  echo "ERROR: Certificate file not found: $WIN_CERT_FILE"
  exit 1
fi

sign_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "WARNING: File not found, skipping: $file"
    return 0
  fi

  echo "Signing: $file"
  signtool sign \
    /fd "$SIGNING_HASH" \
    /tr "$TIMESTAMP_SERVER" \
    /td "$SIGNING_HASH" \
    /f "$WIN_CERT_FILE" \
    ${WIN_CERT_PASSWORD:+/p "$WIN_CERT_PASSWORD"} \
    "$file"

  if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to sign: $file"
    return 1
  fi

  echo "Verifying: $file"
  signtool verify /pa "$file"
  if [[ $? -ne 0 ]]; then
    echo "ERROR: Signature verification failed: $file"
    return 1
  fi

  echo "OK: $file"
  return 0
}

DIST_DIR="$PROJECT_ROOT/desktop/dist"

echo "=== DeerFlow Windows Code Signing ==="
echo "Certificate: $WIN_CERT_FILE"
echo "Hash algorithm: $SIGNING_HASH"
echo "Timestamp server: $TIMESTAMP_SERVER"
echo ""

FAILED=0

echo "--- Signing executables and DLLs ---"
while IFS= read -r -d '' file; do
  sign_file "$file" || FAILED=$((FAILED + 1))
done < <(find "$DIST_DIR" -type f \( -name "*.exe" -o -name "*.dll" \) -print0 2>/dev/null)

echo ""
echo "--- Signing NSIS installer ---"
for installer in "$DIST_DIR"/DeerFlow-Setup-*.exe; do
  if [[ -f "$installer" ]]; then
    sign_file "$installer" || FAILED=$((FAILED + 1))
  fi
done

echo ""
if [[ $FAILED -eq 0 ]]; then
  echo "=== All files signed successfully ==="
  exit 0
else
  echo "=== $FAILED file(s) failed to sign ==="
  exit 1
fi
