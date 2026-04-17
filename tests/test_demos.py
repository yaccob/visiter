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
    # Invoke the demo with a *relative* path from tmp_path so printed
    # output paths must themselves be relative to the caller's cwd
    # (not absolute, not relative-to-script).
    rel_script = os.path.relpath(work_demos / script.name, start=tmp_path)
    result = subprocess.run(["bash", rel_script],
                            env=env, cwd=str(tmp_path),
                            capture_output=True, text=True)
    assert result.returncode == 0, (
        f"demo failed: {script.name}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    # Each demo prints at least one "wrote …" line.
    assert "wrote" in result.stdout

    # Every path mentioned on a "wrote …" line must
    #   (a) be relative (not absolute — user called with a relative
    #       script path, so output paths should match that style), and
    #   (b) resolve from the caller's cwd.
    for line in result.stdout.splitlines():
        if not line.startswith("wrote "):
            continue
        path_token = line.split(None, 2)[1]
        assert not os.path.isabs(path_token), (
            f"{script.name} reported 'wrote {path_token}' as an absolute "
            f"path, but the caller invoked the demo via a relative path; "
            f"output paths should be relative to the caller's cwd."
        )
        candidate = os.path.join(str(tmp_path), path_token)
        assert os.path.exists(candidate), (
            f"{script.name} reported 'wrote {path_token}' but the path "
            f"does not resolve from the caller's cwd "
            f"({tmp_path}); got: {candidate}"
        )


@pytest.mark.parametrize("vit", sorted(DEMOS.glob("*.vit")),
                         ids=lambda p: p.name)
def test_vit_demo_renders(vit, tmp_path):
    """Standalone .vit demos render successfully via viter."""
    out_svg = tmp_path / vit.with_suffix(".svg").name
    result = subprocess.run(
        ["viter", str(vit), "-o", str(out_svg)],
        env={**os.environ, "PATH": AUGMENTED_PATH},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"vit demo failed: {vit.name}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert out_svg.exists(), f"{vit.name}: expected {out_svg} to exist"
    assert out_svg.stat().st_size > 0, f"{vit.name}: output SVG is empty"
