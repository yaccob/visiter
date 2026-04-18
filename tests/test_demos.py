"""Smoke tests for demos/*.vit.

Each .vit demo is run end-to-end via ``viter`` and required to produce
valid SVG output on stdout.  Skipped when ``dot`` (Graphviz) is missing.
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


# Demos that need extra CLI args or special handling.
VIT_EXTRA_ARGS = {
    "tictactoe.vit": ["--depth", "3"],
}

# Demos that produce text output (inspection), not SVG.
VIT_TEXT_OUTPUT = {
    "analytics_cycles_and_centrality.vit",
}


@pytest.mark.parametrize("vit", sorted(DEMOS.glob("*.vit")),
                         ids=lambda p: p.name)
def test_vit_demo_renders(vit, tmp_path):
    """Each .vit demo runs successfully."""
    extra = VIT_EXTRA_ARGS.get(vit.name, [])
    env = {**os.environ, "PATH": AUGMENTED_PATH}
    result = subprocess.run(
        ["viter", str(vit)] + extra,
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"vit demo failed: {vit.name}\n"
        f"STDOUT (first 200):\n{result.stdout[:200]}\n"
        f"STDERR:\n{result.stderr}"
    )
    if vit.name not in VIT_TEXT_OUTPUT:
        assert "<svg" in result.stdout, (
            f"{vit.name}: expected SVG output on stdout"
        )
    else:
        assert len(result.stdout) > 0, (
            f"{vit.name}: expected text output on stdout"
        )
