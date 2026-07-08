"""Base directory resolution that works both from source and as a PyInstaller binary.

When frozen by PyInstaller, __file__ points into the temporary extraction
directory (sys._MEIPASS), not the actual install location. Config, scripts,
sounds, and output must live next to the executable so operators can edit
them without rebuilding.
"""
import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
