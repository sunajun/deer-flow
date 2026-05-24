#!/bin/bash
set -euo pipefail

echo "=== DeerFlow KVM Permission Setup ==="

if [[ "$(uname)" != "Linux" ]]; then
    echo "Error: This script is only for Linux systems"
    exit 1
fi

CPU_TYPE=$(grep -m1 'vendor_id' /proc/cpuinfo 2>/dev/null | awk '{print $3}')
if [[ "$CPU_TYPE" == "GenuineIntel" ]]; then
    KVM_MODULE="kvm_intel"
elif [[ "$CPU_TYPE" == "AuthenticAMD" ]]; then
    KVM_MODULE="kvm_amd"
else
    echo "Unknown CPU type, cannot auto-detect KVM module"
    echo "Try: sudo modprobe kvm_intel  (for Intel)"
    echo "     sudo modprobe kvm_amd    (for AMD)"
    exit 1
fi

echo "Detected CPU type: $CPU_TYPE -> KVM module: $KVM_MODULE"

if ! lsmod 2>/dev/null | grep -q "^kvm"; then
    echo "Loading KVM module: $KVM_MODULE"
    sudo modprobe "$KVM_MODULE" || {
        echo "Failed to load KVM module. You may need to install it first."
        echo "On Ubuntu: sudo apt install cpu-checker && sudo kvm-ok"
        exit 1
    }
    echo "$KVM_MODULE" | sudo tee /etc/modules-load.d/kvm.conf > /dev/null
    echo "KVM module loaded and persisted"
else
    echo "KVM module already loaded"
fi

if [[ ! -e /dev/kvm ]]; then
    echo "Error: /dev/kvm does not exist even after loading KVM module"
    echo "This may indicate hardware virtualization is disabled in BIOS/UEFI"
    exit 1
fi

if ! getent group kvm > /dev/null 2>&1; then
    echo "Creating kvm group"
    sudo groupadd kvm
else
    echo "kvm group already exists"
fi

if ! groups 2>/dev/null | grep -q '\bkvm\b'; then
    echo "Adding user $USER to kvm group"
    sudo usermod -aG kvm "$USER"
    echo ""
    echo "============================================"
    echo "  IMPORTANT: You must log out and log back"
    echo "  in for the group change to take effect."
    echo "============================================"
    echo ""
    NEED_RELOGIN=1
else
    echo "User $USER is already in kvm group"
    NEED_RELOGIN=0
fi

if [[ -e /dev/kvm ]]; then
    CURRENT_PERMS=$(stat -c '%a' /dev/kvm 2>/dev/null || echo "unknown")
    if [[ "$CURRENT_PERMS" != "666" ]]; then
        echo "Setting /dev/kvm permissions (temporary, until reboot)"
        sudo chmod 666 /dev/kvm 2>/dev/null || echo "Could not change /dev/kvm permissions (may need udev rule)"
    fi
fi

echo ""
echo "=== Verification ==="
if [[ -e /dev/kvm ]] && [[ -r /dev/kvm ]] && [[ -w /dev/kvm ]]; then
    echo "SUCCESS: /dev/kvm is accessible"
else
    if [[ "$NEED_RELOGIN" == "1" ]]; then
        echo "PARTIAL: /dev/kvm exists but not yet accessible"
        echo "Please log out and log back in, then run this script again to verify."
    else
        echo "FAILURE: /dev/kvm exists but is not accessible"
        echo "Try: sudo chmod 666 /dev/kvm"
    fi
fi

echo ""
echo "KVM permission setup complete"
