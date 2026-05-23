#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
OUTPUT_DIR="$SCRIPT_DIR/../resources/python-backend"

echo "=== DeerFlow Backend Build (Nuitka) ==="
echo "Platform: $(uname -s) $(uname -m)"

mkdir -p "$OUTPUT_DIR"

cd "$BACKEND_DIR"

python -m nuitka \
    --standalone \
    --onefile \
    --lto=yes \
    --output-filename=deerflow-backend \
    --output-dir="$OUTPUT_DIR" \
    --include-data-dir="$BACKEND_DIR/packages=packages" \
    --include-data-dir="$PROJECT_ROOT/skills/public=skills" \
    --include-data-files="$PROJECT_ROOT/config.example.yaml=." \
    --enable-plugin=pydantic \
    --enable-plugin=anti-bloat \
    --follow-import-to=app \
    --follow-import-to=langchain \
    --follow-import-to=langgraph \
    --follow-import-to=langchain_core \
    --follow-import-to=langchain_community \
    --follow-import-to=uvicorn \
    --follow-import-to=starlette \
    --follow-import-to=fastapi \
    --follow-import-to=pydantic \
    --nofollow-import-to=tests \
    --nofollow-import-to=docs \
    --nofollow-import-to=pytest \
    --nofollow-import-to=ruff \
    "$BACKEND_DIR/app/gateway/app.py"

echo ""
echo "=== Nuitka build complete ==="
echo "Output: $OUTPUT_DIR"
echo ""
echo "Running smoke test..."
bash "$SCRIPT_DIR/smoke-test.sh"
