from deerflow.marketplace.models import (
    MarketplaceConfig,
    SkillCategory,
    SkillIndex,
    SkillManifest,
    SkillRegistryEntry,
)

_LAZY_IMPORTS = {
    "SkillRegistry": "deerflow.marketplace.registry",
    "SkillUpdater": "deerflow.marketplace.updater",
    "compare_versions": "deerflow.marketplace.updater",
    "is_security_update": "deerflow.marketplace.updater",
    "is_update_available": "deerflow.marketplace.updater",
}


def __getattr__(name):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MarketplaceConfig",
    "SkillCategory",
    "SkillIndex",
    "SkillManifest",
    "SkillRegistry",
    "SkillRegistryEntry",
    "SkillUpdater",
    "compare_versions",
    "is_security_update",
    "is_update_available",
]
