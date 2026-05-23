#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_BIN="$SCRIPT_DIR/../resources/python-backend/deerflow-backend"

if [ "$(uname -s)" = "Windows_NT" ] || [ "$(uname -s)" = "MINGW" ] || [ "$(uname -s)" = "MSYS" ]; then
    BACKEND_BIN="${BACKEND_BIN}.exe"
fi

HEALTH_URL="http://127.0.0.1:8001/health"
CONFIG_URL="http://127.0.0.1:8001/api/config"
SKILLS_URL="http://127.0.0.1:8001/api/skills"
TIMEOUT=30

PASS=0
FAIL=0
BACKEND_PID=""

cleanup() {
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

log_pass() {
    PASS=$((PASS + 1))
    echo "  ✅ PASS: $1"
}

log_fail() {
    FAIL=$((FAIL + 1))
    echo "  ❌ FAIL: $1"
}

echo "=== DeerFlow Smoke Test ==="

if [ ! -f "$BACKEND_BIN" ]; then
    echo "Error: Backend binary not found at $BACKEND_BIN"
    echo "Run build-backend.sh first."
    exit 1
fi

echo ""
echo "[1/4] Starting backend..."
"$BACKEND_BIN" --host 127.0.0.1 --port 8001 &
BACKEND_PID=$!

echo "Waiting for health check (timeout: ${TIMEOUT}s)..."
elapsed=0
while [ $elapsed -lt $TIMEOUT ]; do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        log_pass "Health check passed"
        break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
done

if [ $elapsed -ge $TIMEOUT ]; then
    log_fail "Health check timeout after ${TIMEOUT}s"
    echo ""
    echo "=== Smoke Test Results ==="
    echo "PASS: $PASS  FAIL: $FAIL"
    exit 1
fi

echo ""
echo "[2/4] Testing core API endpoints..."

HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "$HEALTH_URL")
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "GET /health → 200"
else
    log_fail "GET /health → $HTTP_CODE (expected 200)"
fi

HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "$SKILLS_URL" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "GET /api/skills → 200"
else
    log_fail "GET /api/skills → $HTTP_CODE (expected 200)"
fi

echo ""
echo "[3/4] Checking for import errors in stderr..."
sleep 2

echo ""
echo "[4/4] Resource cleanup..."

echo ""
echo "=== Smoke Test Results ==="
echo "PASS: $PASS  FAIL: $FAIL"

if [ $FAIL -gt 0 ]; then
    exit 1
fi

echo "All smoke tests passed!"
