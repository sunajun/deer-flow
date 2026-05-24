import logging
import os
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KVMStatus:
    available: bool
    reason: str = ""
    can_fix: bool = False
    fix_description: str = ""
    kvm_group_exists: bool = False
    user_in_kvm_group: bool = False
    kvm_module_loaded: bool = False
    cpu_type: str = ""


def _detect_cpu_type() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            content = f.read()
        if "GenuineIntel" in content:
            return "intel"
        if "AuthenticAMD" in content:
            return "amd"
    except OSError:
        pass
    return "unknown"


def _try_load_module(module_name: str) -> bool:
    try:
        result = subprocess.run(
            ["modprobe", module_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_group_exists(group_name: str) -> bool:
    try:
        result = subprocess.run(
            ["getent", "group", group_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_user_in_group(group_name: str) -> bool:
    try:
        result = subprocess.run(
            ["id", "-nG"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return group_name in result.stdout.split()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def _is_kvm_module_loaded() -> bool:
    try:
        result = subprocess.run(
            ["lsmod"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("kvm"):
                    return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def _is_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _is_in_cloud_vm() -> bool:
    try:
        result = subprocess.run(
            ["systemd-detect-virt"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            virt_type = result.stdout.strip()
            return virt_type in ("kvm", "qemu", "xen", "vmware", "microsoft", "oracle")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def _check_nested_virtualization() -> bool:
    cpu_type = _detect_cpu_type()
    if cpu_type == "intel":
        nested_path = "/sys/module/kvm_intel/parameters/nested"
    elif cpu_type == "amd":
        nested_path = "/sys/module/kvm_amd/parameters/nested"
    else:
        return False
    try:
        with open(nested_path, encoding="utf-8") as f:
            value = f.read().strip().lower()
        return value in ("1", "y", "yes")
    except OSError:
        return False


def check_kvm_available() -> KVMStatus:
    cpu_type = _detect_cpu_type()
    module_loaded = _is_kvm_module_loaded()

    if not os.path.exists("/dev/kvm"):
        if module_loaded:
            return KVMStatus(
                available=False,
                reason="/dev/kvm does not exist despite KVM module being loaded",
                can_fix=False,
                cpu_type=cpu_type,
                kvm_module_loaded=module_loaded,
            )

        if cpu_type in ("intel", "amd"):
            module_name = f"kvm_{cpu_type}"
            if _try_load_module(module_name):
                if os.path.exists("/dev/kvm"):
                    return KVMStatus(available=True, cpu_type=cpu_type, kvm_module_loaded=True)
                return KVMStatus(
                    available=False,
                    reason="KVM module loaded but /dev/kvm still not present",
                    can_fix=False,
                    cpu_type=cpu_type,
                    kvm_module_loaded=True,
                )
            return KVMStatus(
                available=False,
                reason="KVM module not loaded and cannot be auto-loaded",
                can_fix=True,
                fix_description=f"Try: sudo modprobe kvm_{cpu_type}",
                cpu_type=cpu_type,
                kvm_module_loaded=False,
            )

        if _is_in_docker():
            return KVMStatus(
                available=False,
                reason="Running inside Docker container without /dev/kvm",
                can_fix=True,
                fix_description="Restart container with: docker run --device /dev/kvm ...",
                cpu_type=cpu_type,
                kvm_module_loaded=module_loaded,
            )

        return KVMStatus(
            available=False,
            reason="/dev/kvm does not exist and CPU type is unknown",
            can_fix=False,
            cpu_type=cpu_type,
            kvm_module_loaded=module_loaded,
        )

    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        kvm_group_exists = _check_group_exists("kvm")
        user_in_kvm_group = _check_user_in_group("kvm")

        if _is_in_docker():
            return KVMStatus(
                available=False,
                reason="No read/write access to /dev/kvm inside Docker",
                can_fix=True,
                fix_description="Restart container with: docker run --device /dev/kvm ...",
                kvm_group_exists=kvm_group_exists,
                user_in_kvm_group=user_in_kvm_group,
                kvm_module_loaded=module_loaded,
                cpu_type=cpu_type,
            )

        if _is_in_cloud_vm() and not _check_nested_virtualization():
            return KVMStatus(
                available=False,
                reason="Running in a cloud VM without nested virtualization",
                can_fix=True,
                fix_description="Enable nested virtualization on your cloud provider, or use Docker/Podman sandbox as fallback",
                kvm_group_exists=kvm_group_exists,
                user_in_kvm_group=user_in_kvm_group,
                kvm_module_loaded=module_loaded,
                cpu_type=cpu_type,
            )

        fix_parts = []
        if not kvm_group_exists:
            fix_parts.append("sudo groupadd kvm")
        if not user_in_kvm_group:
            fix_parts.append("sudo usermod -aG kvm $USER (then re-login)")
        fix_parts.append("sudo chmod 666 /dev/kvm (temporary)")

        return KVMStatus(
            available=False,
            reason="No read/write access to /dev/kvm",
            can_fix=True,
            fix_description="; ".join(fix_parts),
            kvm_group_exists=kvm_group_exists,
            user_in_kvm_group=user_in_kvm_group,
            kvm_module_loaded=module_loaded,
            cpu_type=cpu_type,
        )

    return KVMStatus(
        available=True,
        cpu_type=cpu_type,
        kvm_module_loaded=module_loaded,
    )
