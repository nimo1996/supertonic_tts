# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds a single standalone binary with no config.yaml
# dependency — all synthesis settings (voice/speed/steps/sample_rate/gain)
# are hardcoded in api_lite.py's DEFAULTS.
#   - supertonic-api-lite  (server, entry: api_lite.py)
#
# Build with:  .venv/bin/python -m PyInstaller build_pkg/supertonic-lite.spec --clean --noconfirm
# Run from the project root so relative paths below resolve correctly.

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

api_lite_analysis = Analysis(
    [str(PROJECT_ROOT / "api_lite.py")],
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

api_lite_pyz = PYZ(api_lite_analysis.pure, api_lite_analysis.zipped_data, cipher=block_cipher)

api_lite_exe = EXE(
    api_lite_pyz,
    api_lite_analysis.scripts,
    api_lite_analysis.binaries,
    api_lite_analysis.zipfiles,
    api_lite_analysis.datas,
    [],
    name="tts-api-lite",
    console=True,
    onefile=True,
    strip=False,
    upx=False,
)
