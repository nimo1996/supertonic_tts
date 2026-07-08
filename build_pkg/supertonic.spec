# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds two standalone binaries (no .py source shipped)
#   - supertonic-tts  (CLI,  entry: tts.py)
#   - supertonic-api  (server, entry: api.py)
#
# Build with:  .venv/bin/python -m PyInstaller build_pkg/supertonic.spec --clean --noconfirm
# Run from the project root so relative paths below resolve correctly.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
PROJECT_ROOT = Path.cwd()

COLLECT_ALL_PACKAGES = [
    "supertonic",
    "onnxruntime",
    "huggingface_hub",
    "uvicorn",
    "starlette",
    "fastapi",
    "soundfile",
    "pydantic",
    "pydantic_core",
    "yaml",
]

datas = []
binaries = []
hiddenimports = []

for pkg in COLLECT_ALL_PACKAGES:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += ["engines", "engines.supertonic_engine", "paths"]

common_excludes = ["tkinter", "matplotlib", "test", "tests"]


def make_analysis(entry_script: str) -> Analysis:
    return Analysis(
        [str(PROJECT_ROOT / entry_script)],
        pathex=[str(PROJECT_ROOT)],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=common_excludes,
        noarchive=False,
        cipher=block_cipher,
    )


tts_analysis = make_analysis("tts.py")
api_analysis = make_analysis("api.py")

tts_pyz = PYZ(tts_analysis.pure, tts_analysis.zipped_data, cipher=block_cipher)
api_pyz = PYZ(api_analysis.pure, api_analysis.zipped_data, cipher=block_cipher)

tts_exe = EXE(
    tts_pyz,
    tts_analysis.scripts,
    tts_analysis.binaries,
    tts_analysis.zipfiles,
    tts_analysis.datas,
    [],
    name="supertonic-tts",
    console=True,
    onefile=True,
    strip=False,
    upx=False,
)

api_exe = EXE(
    api_pyz,
    api_analysis.scripts,
    api_analysis.binaries,
    api_analysis.zipfiles,
    api_analysis.datas,
    [],
    name="supertonic-api",
    console=True,
    onefile=True,
    strip=False,
    upx=False,
)
