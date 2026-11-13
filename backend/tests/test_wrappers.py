"""Tests for the launcher scripts in backend/wrappers (no network, fake Blackbird)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "wrappers" / "blackbird"


def run_wrapper(home: Path, *args: str) -> list[str]:
    """Runs the wrapper against a fake blackbird.py that prints the arguments it received."""
    (home / "blackbird.py").write_text("import json, sys\nprint('ARGS=' + json.dumps(sys.argv[1:]))\n")
    env = {**os.environ, "BLACKBIRD_HOME": str(home), "BLACKBIRD_PYTHON": sys.executable}
    out = subprocess.run(["sh", str(WRAPPER), *args], capture_output=True, text=True, env=env, timeout=20)
    assert out.returncode == 0, out.stderr
    line = next(l for l in out.stdout.splitlines() if l.startswith("ARGS="))
    return json.loads(line[len("ARGS="):])


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper not found")
def test_blackbird_wrapper_drops_no_update_until_the_list_exists(tmp_path):
    args = ["--username", "mario rossi", "--timeout", "20", "--no-nsfw", "--no-update"]

    # Fresh install: no site list yet, so --no-update must be removed (Blackbird downloads the list).
    assert run_wrapper(tmp_path, *args) == ["--username", "mario rossi", "--timeout", "20", "--no-nsfw"]
    assert (tmp_path / "data").is_dir() and (tmp_path / "results").is_dir()

    # An empty file does not count as a downloaded list.
    (tmp_path / "data" / "wmn-data.json").write_text("")
    assert "--no-update" not in run_wrapper(tmp_path, *args)

    # Once the list is there, the arguments pass through untouched.
    (tmp_path / "data" / "wmn-data.json").write_text('{"sites": []}')
    assert run_wrapper(tmp_path, *args) == args


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper not found")
def test_blackbird_wrapper_without_no_update_flag_is_unchanged(tmp_path):
    args = ["--email", "a@b.com", "--timeout", "20"]
    assert run_wrapper(tmp_path, *args) == args
