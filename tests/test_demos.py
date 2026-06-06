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
    # demos/rust/* use lang="rust" and compile callbacks with rustc (and cargo
    # for the Fraction-valued ones).
    if "rust" in vit.parts and not (_have("rustc") and _have("cargo")):
        pytest.skip("rustc/cargo not on PATH (required by lang='rust' demos)")
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


# Rust demos whose whole point is to be the lang="rust" counterpart of a Python
# demo: the SVG on stdout must be byte-for-byte identical to the Python demo's.
RUST_PARITY = [
    "basics/nim.vit",
    "basics/collatz.vit",
    "basics/reverse_collatz.vit",
    "basics/golden_ratio.vit",
    "basics/string_iteration.vit",
    "applications/water_jugs.vit",
]


def _strip_host_noise(svg):
    # Drop the one build-host-dependent line (graphviz version comment).
    return "\n".join(ln for ln in svg.splitlines()
                     if "graphviz version" not in ln)


@pytest.mark.skipif(not (_have("rustc") and _have("cargo")),
                    reason="rustc/cargo not on PATH (required by lang='rust')")
@pytest.mark.parametrize("rel", RUST_PARITY)
def test_rust_demo_matches_python_svg(rel):
    """Each rust/ demo renders the same SVG as its python/ counterpart."""
    env = {**os.environ, "PATH": AUGMENTED_PATH}

    def _svg(path):
        r = subprocess.run(["viter", str(path)], env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{path} failed:\n{r.stderr}"
        return _strip_host_noise(r.stdout)

    py = _svg(DEMOS / "python" / rel)
    rs = _svg(DEMOS / "rust" / rel)
    assert py == rs, f"rust/{rel} SVG diverges from python/{rel}"
