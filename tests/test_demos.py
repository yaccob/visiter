"""Smoke tests for demos/*.sh.

Each demo script is run end-to-end and required to exit 0. Skipped when
either `dot` (Graphviz) or `bash` is missing. The `visiter` console
script is invoked via the same Python that runs pytest, so an editable
install of the project is enough — no PATH gymnastics required beyond
ensuring the venv's `bin` is on PATH.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEMOS = REPO / "demos"


VENV_BIN = os.path.dirname(sys.executable)
AUGMENTED_PATH = VENV_BIN + os.pathsep + os.environ.get("PATH", "")


def _have(cmd):
    return shutil.which(cmd, path=AUGMENTED_PATH) is not None


pytestmark = [
    pytest.mark.skipif(not _have("bash"), reason="bash not available"),
    pytest.mark.skipif(not _have("dot"), reason="Graphviz `dot` not on PATH"),
    pytest.mark.skipif(not _have("visiter"),
                       reason="`visiter` console script not installed "
                              "(install with `pip install -e .[dev]`)"),
]


@pytest.mark.parametrize("script", sorted(DEMOS.glob("*.sh")),
                         ids=lambda p: p.name)
def test_demo_runs(script, tmp_path):
    # Run demos against a tmp out-dir so concurrent runs / stale outputs
    # don't interfere. Each script `cd`s into its own location and writes
    # to ./out — symlink that into a tmp dir.
    work_demos = tmp_path / "demos"
    shutil.copytree(DEMOS, work_demos)
    (work_demos / "out").mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = AUGMENTED_PATH
    result = subprocess.run(["bash", str(work_demos / script.name)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"demo failed: {script.name}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    # Each demo prints at least one "wrote …" line.
    assert "wrote" in result.stdout
