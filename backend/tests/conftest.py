import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_BIN = Path(__file__).resolve().parent / "fake_bin"

sys.path.insert(0, str(ROOT))
# The fake CLI tools take precedence over any installed ones.
os.environ["PATH"] = f"{FAKE_BIN}{os.pathsep}{os.environ['PATH']}"
