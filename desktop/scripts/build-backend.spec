# -*- mode: python ; coding: utf-8 -*-
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(SPECPATH))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "../.."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
HIDDEN_IMPORTS_FILE = os.path.join(SCRIPT_DIR, "hidden-imports.txt")

hidden_imports = []
if os.path.isfile(HIDDEN_IMPORTS_FILE):
    with open(HIDDEN_IMPORTS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                hidden_imports.append(line)
else:
    print(f"Warning: {HIDDEN_IMPORTS_FILE} not found, using empty hidden imports", file=sys.stderr)

block_cipher = None

a = Analysis(
    [os.path.join(BACKEND_DIR, "app/gateway/app.py")],
    pathex=[BACKEND_DIR],
    binaries=[],
    datas=[
        (os.path.join(BACKEND_DIR, "packages"), "packages"),
        (os.path.join(PROJECT_ROOT, "skills/public"), "skills"),
        (os.path.join(PROJECT_ROOT, "config.example.yaml"), "."),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "docs", "__pycache__", ".git", "pytest", "ruff"],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="deerflow-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
