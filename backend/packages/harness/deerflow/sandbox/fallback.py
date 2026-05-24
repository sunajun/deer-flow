import logging
from datetime import datetime

from deerflow.sandbox.base import CrossPlatformSandboxProvider
from deerflow.sandbox.exceptions import SandboxError
from deerflow.sandbox.local_sandbox import LocalSandboxProvider

logger = logging.getLogger(__name__)


class FallbackManager:
    PROVIDER_PRIORITY = ["vm", "docker", "local"]

    def __init__(self, config: dict):
        self.config = config
        self._providers: dict[str, CrossPlatformSandboxProvider] = {}
        self._active_provider: str = ""
        self._fallback_history: list[dict] = []
        self._vm_failure_count: int = 0
        self._vm_timeout_total: float = 0.0
        self._max_vm_failures: int = 3
        self._max_vm_timeout: float = 60.0

    def _create_provider(self, provider_type: str) -> CrossPlatformSandboxProvider | None:
        try:
            if provider_type == "vm":
                from deerflow.sandbox.vm_sandbox import VMSandboxProvider
                return VMSandboxProvider()
            elif provider_type == "docker":
                return None
            elif provider_type == "local":
                return LocalSandboxProvider()
        except Exception as e:
            logger.warning("创建沙箱提供者 %s 失败: %s", provider_type, e)
            return None
        return None

    async def initialize(self) -> None:
        for provider_type in self.PROVIDER_PRIORITY:
            provider = self._create_provider(provider_type)
            if provider is None:
                logger.info("沙箱提供者 %s 不可用，尝试下一个", provider_type)
                continue

            try:
                if await provider.is_available():
                    self._providers[provider_type] = provider
                    self._active_provider = provider_type
                    logger.info("沙箱提供者选择: %s", provider_type)
                    return
                else:
                    logger.info("沙箱提供者 %s 不可用，尝试下一个", provider_type)
            except Exception as e:
                logger.warning("检测沙箱提供者 %s 时出错: %s", provider_type, e)

        self._providers["local"] = LocalSandboxProvider()
        self._active_provider = "local"
        logger.warning("所有 VM 沙箱不可用，降级到本地模式")

    async def get_provider(self) -> CrossPlatformSandboxProvider:
        if self._active_provider not in self._providers:
            self._providers["local"] = LocalSandboxProvider()
            self._active_provider = "local"
        return self._providers[self._active_provider]

    async def fallback(self, reason: str) -> CrossPlatformSandboxProvider:
        try:
            current_idx = self.PROVIDER_PRIORITY.index(self._active_provider)
        except ValueError:
            current_idx = len(self.PROVIDER_PRIORITY) - 1

        for next_type in self.PROVIDER_PRIORITY[current_idx + 1:]:
            if next_type in self._providers:
                try:
                    if await self._providers[next_type].is_available():
                        self._fallback_history.append({
                            "from": self._active_provider,
                            "to": next_type,
                            "reason": reason,
                            "timestamp": datetime.now().isoformat(),
                        })
                        self._active_provider = next_type
                        logger.warning(
                            "沙箱降级: %s -> %s (原因: %s)",
                            self._fallback_history[-1]["from"],
                            next_type,
                            reason,
                        )
                        return self._providers[next_type]
                except Exception:
                    continue

            provider = self._create_provider(next_type)
            if provider is not None:
                try:
                    if await provider.is_available():
                        self._providers[next_type] = provider
                        self._fallback_history.append({
                            "from": self._active_provider,
                            "to": next_type,
                            "reason": reason,
                            "timestamp": datetime.now().isoformat(),
                        })
                        self._active_provider = next_type
                        logger.warning(
                            "沙箱降级: %s -> %s (原因: %s)",
                            self._fallback_history[-1]["from"],
                            next_type,
                            reason,
                        )
                        return self._providers[next_type]
                except Exception:
                    continue

        self._providers["local"] = LocalSandboxProvider()
        self._active_provider = "local"
        self._fallback_history.append({
            "from": self._active_provider,
            "to": "local",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })
        return self._providers["local"]

    def record_vm_failure(self) -> None:
        self._vm_failure_count += 1
        if self._vm_failure_count >= self._max_vm_failures:
            logger.warning(
                "VM 失败次数达到 %d 次，建议降级",
                self._vm_failure_count,
            )

    def record_vm_timeout(self, seconds: float) -> None:
        self._vm_timeout_total += seconds
        if self._vm_timeout_total >= self._max_vm_timeout:
            logger.warning(
                "VM 累计超时 %.1f 秒，建议降级",
                self._vm_timeout_total,
            )

    def should_auto_fallback(self) -> bool:
        return (
            self._vm_failure_count >= self._max_vm_failures
            or self._vm_timeout_total >= self._max_vm_timeout
        )

    async def try_recover(self, target: str = "vm") -> bool:
        provider = self._create_provider(target)
        if provider is None:
            return False
        try:
            if not await provider.is_available():
                return False
            self._providers[target] = provider
            self._active_provider = target
            self._vm_failure_count = 0
            self._vm_timeout_total = 0.0
            self._fallback_history.append({
                "from": "local",
                "to": target,
                "reason": "用户手动恢复",
                "timestamp": datetime.now().isoformat(),
            })
            logger.info("沙箱恢复到: %s", target)
            return True
        except Exception as e:
            logger.warning("恢复沙箱提供者 %s 失败: %s", target, e)
            return False

    def get_fallback_history(self) -> list[dict]:
        return list(self._fallback_history)

    @property
    def active_provider_type(self) -> str:
        return self._active_provider
