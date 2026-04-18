"""Smoke tests for demos/**/*.vit.

Each .vit demo is run end-to-end via ``viter`` and required to
complete successfully.  Skipped when ``dot`` (Graphviz) is missing.
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
    pytest.mark.skipif(not _have("dot"), reason="Graphviz `dot` not on PATH"),
    pytest.mark.skipif(not _have("viter"),
                       reason="`viter` console script not installed "
                              "(install with `pip install -e .[dev]`)"),
]


# Demos that need extra CLI args.
VIT_EXTRA_ARGS = {
    "tictactoe.vit": ["--depth", "3"],
}

# Demos that produce file output instead of SVG on stdout.
VIT_FILE_OUTPUT = {
    "ghost_stubs.vit",
    "color_stability.vit",
    "water_jugs.vit",
}

# Demos that produce text output (inspection), not SVG.
VIT_TEXT_OUTPUT = {
    "inspection.vit",
}


def _all_vit_files():
    return sorted(DEMOS.rglob("*.vit"))


@pytest.mark.parametrize("vit", _all_vit_files(),
                         ids=lambda p: str(p.relative_to(DEMOS)))
def test_vit_demo_runs(vit, tmp_path):
    """Each .vit demo runs successfully."""
    extra = VIT_EXTRA_ARGS.get(vit.name, [])
    env = {**os.environ, "PATH": AUGMENTED_PATH}
    result = subprocess.run(
        ["viter", str(vit)] + extra,
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"vit demo failed: {vit.relative_to(DEMOS)}\n"
        f"STDOUT (first 200):\n{result.stdout[:200]}\n"
        f"STDERR:\n{result.stderr}"
    )
    if vit.name in VIT_FILE_OUTPUT or vit.name in VIT_TEXT_OUTPUT:
        # These demos write to files or produce text, not SVG on stdout.
        pass
    else:
        assert "<svg" in result.stdout, (
            f"{vit.relative_to(DEMOS)}: expected SVG output on stdout"
        )
