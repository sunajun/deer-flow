#!/usr/bin/env bash
set -euo pipefail

DEERFLOW_VERSION="${1:-unknown}"
IMAGE_FORMAT="${2:-unknown}"
COMPAT_VERSION="${3:-1}"
MIN_APP_VERSION="${4:-0.1.0}"
PYTHON_VERSION="${5:-3.12}"
NODE_VERSION="${6:-20}"
UBUNTU_VERSION="${7:-24.04}"

cat > /etc/deerflow-version <<EOF
DEERFLOW_VERSION=${DEERFLOW_VERSION}
IMAGE_FORMAT=${IMAGE_FORMAT}
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
COMPAT_VERSION=${COMPAT_VERSION}
MIN_APP_VERSION=${MIN_APP_VERSION}
PYTHON_VERSION=${PYTHON_VERSION}
NODE_VERSION=${NODE_VERSION}
UBUNTU_VERSION=${UBUNTU_VERSION}
EOF

chmod 644 /etc/deerflow-version

echo "DeerFlow VM initialized - version ${DEERFLOW_VERSION} (${IMAGE_FORMAT})"

if command -v sshd &>/dev/null; then
    mkdir -p /run/sshd
    ssh-keygen -A 2>/dev/null || true
fi

if id sandbox &>/dev/null; then
    echo "Sandbox user ready"
else
    echo "Warning: sandbox user not found"
fi

echo "Python: $(python3 --version 2>/dev/null || echo 'not found')"
echo "Node: $(node --version 2>/dev/null || echo 'not found')"
echo "Git: $(git --version 2>/dev/null || echo 'not found')"
