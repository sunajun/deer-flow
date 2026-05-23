#!/usr/bin/env python3
"""Scan hidden imports for PyInstaller packaging.

Automatically discovers implicit imports used by FastAPI, LangGraph,
LangChain, and other dynamically-loaded dependencies. Outputs a list
of hidden-import module names for the PyInstaller spec file.
"""

import importlib
import pkgutil
import sys
import os

KNOWN_HIDDEN_IMPORTS = [
    # FastAPI / Starlette
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "starlette.responses",
    "starlette.routing",
    "starlette.middleware",
    # LangChain
    "langchain_community",
    "langchain_core",
    "langchain_openai",
    "langchain_anthropic",
    "langchain_text_splitters",
    # LangGraph
    "langgraph",
    "langgraph.graph",
    "langgraph.prebuilt",
    "langgraph.checkpoint",
    "langgraph.pregel",
    # Pydantic
    "pydantic.deprecated.decorator",
    "pydantic._internal._generate_schema",
    # HTTP clients
    "httpx",
    "httpcore",
    "anyio",
    "sniffio",
    # YAML / config
    "yaml",
    "pyyaml",
    # Other
    "multidict",
    "yarl",
    "frozenlist",
    "aiosignal",
]

SKIP_PREFIXES = [
    "_frozen_importlib",
    "importlib",
    "encodings",
    "_io",
    "builtins",
    "_abc",
    "_signal",
    "_thread",
    "_weakref",
    "_collections",
    "_functools",
    "_operator",
    "_sre",
    "_codecs",
    "_struct",
    "_datetime",
    "_decimal",
    "_pickle",
    "_hashlib",
    "_sha",
    "_md5",
    "_random",
    "_socket",
    "_ssl",
    "_csv",
    "_json",
    "_multiprocessing",
    "_ctypes",
    "_curses",
    "_sqlite3",
    "_elementtree",
    "_lzma",
    "_bz2",
    "_zlib",
    "_opcode",
]


def scan_hidden_imports(package_path: str) -> list[str]:
    """Scan a package directory for all loaded modules.

    Args:
        package_path: Path to the backend package root.

    Returns:
        Sorted list of module names that should be hidden imports.
    """
    sys.path.insert(0, package_path)

    try:
        import app.gateway.app
        import app.gateway.config
    except ImportError as e:
        print(f"Warning: Could not import gateway modules: {e}", file=sys.stderr)

    modules = sorted(sys.modules.keys())

    hidden = []
    for m in modules:
        if any(m.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if m.startswith("_") and "." not in m:
            continue
        hidden.append(m)

    for known in KNOWN_HIDDEN_IMPORTS:
        if known not in hidden:
            hidden.append(known)

    hidden.sort()
    return hidden


def scan_subpackages(package_name: str) -> list[str]:
    """Discover sub-packages of a given package using pkgutil.

    Args:
        package_name: The dotted package name to scan.

    Returns:
        List of discovered sub-package names.
    """
    subpackages = []
    try:
        package = importlib.import_module(package_name)
        if hasattr(package, "__path__"):
            for importer, modname, ispkg in pkgutil.walk_packages(
                package.__path__, prefix=package_name + "."
            ):
                subpackages.append(modname)
    except ImportError:
        pass
    return subpackages


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_path = os.path.normpath(os.path.join(script_dir, "../../backend"))

    if not os.path.isdir(backend_path):
        print(f"Error: Backend directory not found at {backend_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning hidden imports from: {backend_path}")

    hidden = scan_hidden_imports(backend_path)

    for pkg in ["langchain", "langgraph", "langchain_core", "langchain_community", "uvicorn", "starlette", "pydantic"]:
        subs = scan_subpackages(pkg)
        for s in subs:
            if s not in hidden:
                hidden.append(s)

    hidden.sort()

    output_path = os.path.join(script_dir, "hidden-imports.txt")
    with open(output_path, "w") as f:
        for mod in hidden:
            f.write(mod + "\n")

    print(f"Found {len(hidden)} hidden imports")
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
