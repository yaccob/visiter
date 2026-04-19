"""Tests for the ``viter`` CLI executor."""

import os
import subprocess
import sys

import pytest


# ---- pre-bound namespace exposes the new Builder API ----------------------

def test_cli_namespace_viter_returns_builder():
    from visiter.cli import _build_namespace
    from visiter import Builder
    ns = _build_namespace("/tmp/dummy.vit")
    result = ns["viter"](range(1, 5))
    assert isinstance(result, Builder)


def test_cli_namespace_exposes_match_and_onlimit_enums():
    from visiter.cli import _build_namespace
    from visiter import Match, OnLimit
    ns = _build_namespace("/tmp/dummy.vit")
    assert ns["Match"] is Match
    assert ns["OnLimit"] is OnLimit


VENV_BIN = os.path.dirname(sys.executable)
ENV = {**os.environ, "PATH": VENV_BIN + os.pathsep + os.environ.get("PATH", "")}


def run_viter(*args):
    return subprocess.run(["viter", *args], capture_output=True, text=True,
                          env=ENV)


# ---- basic flags ------------------------------------------------------------

def test_version_flag():
    from visiter import __version__
    r = run_viter("--version")
    assert r.returncode == 0, r.stderr
    assert __version__ in r.stdout


def test_help_flag():
    r = run_viter("--help")
    assert r.returncode == 0
    assert "viter" in r.stdout
    assert ".vit" in r.stdout


# ---- executing .vit files ---------------------------------------------------

def test_vit_file_renders_svg_to_stdout(tmp_path):
    vit = tmp_path / "simple.vit"
    vit.write_text(
        '(viter(range(1, 8))\n'
        ' .case(lambda x: x%3==0, lambda x: x//3, label="÷3")\n'
        ' .default(lambda x: x+2, label="+2")\n'
        ' .render())\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert "<svg" in r.stdout


def test_vit_file_renders_svg_to_file(tmp_path):
    vit = tmp_path / "to_file.vit"
    out = tmp_path / "out.svg"
    vit.write_text(
        '(viter(range(1, 8))\n'
        ' .case(lambda x: x%3==0, lambda x: x//3, label="÷3")\n'
        ' .default(lambda x: x+2, label="+2")\n'
        f' .render(file="{out}"))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "<svg" in body


def test_vit_file_writes_json_via_tap(tmp_path):
    vit = tmp_path / "json_out.vit"
    out = tmp_path / "graph.json"
    vit.write_text(
        '(viter(range(1, 5))\n'
        ' .default(lambda x: x+1, label="+1")\n'
        ' .build()\n'
        f' .tap(write(file="{out}")))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    import json
    data = json.loads(out.read_text())
    assert "schema_version" in data


def test_vit_file_writes_json_to_stdout(tmp_path):
    vit = tmp_path / "json_stdout.vit"
    vit.write_text(
        '(viter(range(1, 5))\n'
        ' .default(lambda x: x+1, label="+1")\n'
        ' .build()\n'
        ' .tap(write()))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert '"schema_version"' in r.stdout


def test_vit_file_dot_format(tmp_path):
    vit = tmp_path / "dot_fmt.vit"
    vit.write_text(
        '(viter([1], max_nodes=3)\n'
        ' .default(lambda x: x+1, label="+1")\n'
        ' .render(format="dot"))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert "digraph" in r.stdout


def test_vit_file_with_shebang(tmp_path):
    vit = tmp_path / "shebang.vit"
    vit.write_text(
        '#!/usr/bin/env viter\n'
        '# A comment\n'
        '(viter(range(1, 5))\n'
        ' .case(lambda x: x%3==0, lambda x: x//3, label="÷3")\n'
        ' .default(lambda x: x+2, label="+2")\n'
        ' .render())\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert "<svg" in r.stdout


# ---- namespace bindings -----------------------------------------------------

def test_fraction_in_namespace(tmp_path):
    vit = tmp_path / "fraction.vit"
    vit.write_text(
        '(viter([Fraction(1)], max_depth=4, key_type="number")\n'
        ' .case(lambda x: True, lambda x: 1 + 1/x, label="step")\n'
        ' .build()\n'
        ' .tap(write()))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert '"3/2"' in r.stdout


def test_decimal_in_namespace(tmp_path):
    vit = tmp_path / "decimal.vit"
    vit.write_text(
        'viter([Decimal("1.5")]).build().tap(write())\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert '"1.5"' in r.stdout


def test_custom_import_in_vit(tmp_path):
    vit = tmp_path / "custom_import.vit"
    vit.write_text(
        'import math\n'
        '(viter([16], max_nodes=5)\n'
        ' .case(lambda x: x > 2, lambda x: int(math.sqrt(x)), label="sqrt")\n'
        ' .build()\n'
        ' .tap(write()))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert '"4"' in r.stdout


# ---- sys.argv passthrough ---------------------------------------------------

def test_sys_argv_passthrough(tmp_path):
    vit = tmp_path / "args.vit"
    vit.write_text(
        'import sys\n'
        'n = int(sys.argv[1]) if len(sys.argv) > 1 else 5\n'
        'viter(range(1, n)).build().tap(write())\n'
    )
    r = run_viter(str(vit), "3")
    assert r.returncode == 0, r.stderr
    import json
    data = json.loads(r.stdout)
    assert set(data["nodes"].keys()) == {"1", "2"}


def test_sys_argv_with_argparse(tmp_path):
    vit = tmp_path / "argparse_demo.vit"
    vit.write_text(
        'import argparse\n'
        'p = argparse.ArgumentParser()\n'
        'p.add_argument("--start", type=int, default=5)\n'
        'args = p.parse_args()\n'
        'viter(range(1, args.start)).build().tap(write())\n'
    )
    r = run_viter(str(vit), "--start", "4")
    assert r.returncode == 0, r.stderr
    import json
    data = json.loads(r.stdout)
    assert set(data["nodes"].keys()) == {"1", "2", "3"}


# ---- __file__ binding -------------------------------------------------------

def test_dunder_file_is_bound(tmp_path):
    vit = tmp_path / "check_file.vit"
    vit.write_text(
        'import sys\n'
        'print(__file__, file=sys.stderr)\n'
        'viter([1]).build().tap(write())\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert str(vit.resolve()) in r.stderr


# ---- error handling ---------------------------------------------------------

def test_missing_file_exits_nonzero():
    r = run_viter("/nonexistent/file.vit")
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_syntax_error_shows_traceback(tmp_path):
    vit = tmp_path / "bad_syntax.vit"
    vit.write_text("viter((\n")
    r = run_viter(str(vit))
    assert r.returncode != 0
    assert "SyntaxError" in r.stderr


# ---- safety caps (warnings) ------------------------------------------------

def test_max_nodes_default_warns(tmp_path):
    vit = tmp_path / "warn_nodes.vit"
    vit.write_text(
        '(viter([0], max_nodes=5)\n'
        ' .case(lambda x: True, lambda x: x+1, label="+1")\n'
        ' .build()\n'
        ' .tap(write()))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert "max_nodes=5" in r.stderr


def test_max_depth_default_warns(tmp_path):
    vit = tmp_path / "warn_depth.vit"
    vit.write_text(
        '(viter([0], max_depth=3)\n'
        ' .case(lambda x: True, lambda x: x+1, label="+1")\n'
        ' .build()\n'
        ' .tap(write()))\n'
    )
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert "max_depth=3" in r.stderr
