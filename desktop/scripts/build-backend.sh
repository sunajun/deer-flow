#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
OUTPUT_DIR="$SCRIPT_DIR/../resources/python-backend"
HIDDEN_IMPORTS_FILE="$SCRIPT_DIR/hidden-imports.txt"

echo "=== DeerFlow Backend Build Script ==="
echo "Platform: $(uname -s) $(uname -m)"
echo "Backend dir: $BACKEND_DIR"
echo "Output dir: $OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"

echo ""
echo "[1/3] Scanning hidden imports..."
cd "$PROJECT_ROOT"
python3 "$SCRIPT_DIR/scan-hidden-imports.py"

if [ ! -f "$HIDDEN_IMPORTS_FILE" ]; then
    echo "Error: hidden-imports.txt not found after scan"
    exit 1
fi

HIDDEN_IMPORT_COUNT=$(wc -l < "$HIDDEN_IMPORTS_FILE")
echo "Found $HIDDEN_IMPORT_COUNT hidden imports"

echo ""
echo "[2/3] Building with PyInstaller..."

SPEC_FILE="$SCRIPT_DIR/build-backend.spec"
cd "$BACKEND_DIR"

PYINSTALLER_ARGS=(
    --name deerflow-backend
    --onefile
    --distpath "$OUTPUT_DIR"
    --workpath "$SCRIPT_DIR/../build"
    --specpath "$SCRIPT_DIR/../build"
    --clean
)

while IFS= read -r module; do
    PYINSTALLER_ARGS+=(--hidden-import "$module")
done < "$HIDDEN_IMPORTS_FILE"

PYINSTALLER_ARGS+=(
    --add-data "$BACKEND_DIR/packages:packages"
    --add-data "$PROJECT_ROOT/skills/public:skills"
    --add-data "$PROJECT_ROOT/config.example.yaml:."
    --exclude-module tests
    --exclude-module docs
    --exclude-module __pycache__
    --exclude-module .git
    --noupx
)

if [ "$(uname -s)" = "Darwin" ]; then
    PYINSTALLER_ARGS+=(--target-architecture universal2)
fi

pyinstaller "${PYINSTALLER_ARGS]}" "$BACKEND_DIR/app/gateway/app.py"

echo ""
echo "[3/3] Running smoke test..."
bash "$SCRIPT_DIR/smoke-test.sh"

echo ""
echo "=== Build complete ==="
echo "Output: $OUTPUT_DIR"
