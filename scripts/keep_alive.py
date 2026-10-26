#!/usr/bin/env python3
"""
Legacy wrapper: delegates directly to keep_alive_render.py
"""
import sys
from pathlib import Path

scripts_dir = Path(__file__).parent
keep_alive_render = scripts_dir / "keep_alive_render.py"

if __name__ == "__main__":
    import subprocess
    cmd = [sys.executable, str(keep_alive_render)] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))
