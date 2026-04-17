"""Tests for the top-level `visiter` and `viter` CLI surfaces."""

import os
import subprocess
import sys

import pytest

VENV_BIN = os.path.dirname(sys.executable)
ENV = {**os.environ, "PATH": VENV_BIN + os.pathsep + os.environ.get("PATH", "")}


def run(*args, input_=None):
    return subprocess.run(["visiter", *args], capture_output=True, text=True,
                          input=input_, env=ENV)


def run_viter(*args, input_=None):
    return subprocess.run(["viter", *args], capture_output=True, text=True,
                          input=input_, env=ENV)


# ---- visiter top-level -------------------------------------------------------

def test_top_level_version_flag():
    from visiter import __version__
    r = run("--version")
    assert r.returncode == 0, r.stderr
    assert __version__ in r.stdout


def test_top_level_help_describes_tool_and_lists_subcommands():
    r = run("--help")
    assert r.returncode == 0
    out = r.stdout
    assert "build" in out
    assert "to-dot" in out
    assert "validate" in out
    assert "analyze" in out
    assert "render" in out
    assert "iteration" in out.lower() or "graph" in out.lower()


@pytest.mark.parametrize("sub", ["build", "to-dot", "validate", "analyze",
                                  "render"])
def test_subcommand_help_works(sub):
    r = run(sub, "--help")
    assert r.returncode == 0, r.stderr
    assert "Usage" in r.stdout or "usage" in r.stdout


# ---- visiter build (stdin / file) -------------------------------------------

def test_build_reads_from_stdin():
    expr = ('range(1,8), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], '
            'Op(lambda x: x+2, label="+2")')
    r = run("build", input_=expr)
    assert r.returncode == 0, r.stderr
    assert '"schema_version": "1"' in r.stdout
    assert '"op_order"' in r.stdout


def test_build_reads_from_file(tmp_path):
    vit = tmp_path / "test.vit"
    vit.write_text("range(1,5), [], Op(lambda x: x+1, label=\"+1\"), "
                   "max_nodes=4, on_limit=\"stop\"")
    r = run("build", str(vit))
    assert r.returncode == 0, r.stderr
    assert '"schema_version": "1"' in r.stdout


def test_build_strips_comment_lines_from_file(tmp_path):
    vit = tmp_path / "commented.vit"
    vit.write_text("#!/usr/bin/env viter\n"
                   "# A comment line\n"
                   "range(1,5), [], Op(lambda x: x+1, label=\"+1\"), "
                   "max_nodes=4, on_limit=\"stop\"\n")
    r = run("build", str(vit))
    assert r.returncode == 0, r.stderr
    assert '"schema_version"' in r.stdout


def test_build_auto_labeled_ops_via_stdin():
    expr = ('range(1, 8), [Rule(lambda x: x % 3 == 0, '
            'Op(lambda x: x // 3))], Op(lambda x: x + 2)')
    r = run("build", input_=expr)
    assert r.returncode == 0, r.stderr
    assert '"x // 3"' in r.stdout
    assert '"x + 2"' in r.stdout


def test_build_multiline_stdin_auto_labels():
    expr = ('range(1, 8),\n'
            '[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],\n'
            'Op(lambda x: x + 2)')
    r = run("build", input_=expr)
    assert r.returncode == 0, r.stderr
    assert '"x + 2"' in r.stdout


def test_build_fraction_default_import():
    expr = ('[Fraction(1)], [Rule(lambda x: True, '
            'Op(lambda x: 1 + 1/x, label="step"))], None, '
            'max_depth=3, key_type="number"')
    r = run("build", input_=expr)
    assert r.returncode == 0, r.stderr
    assert '"key_type": "number"' in r.stdout
    assert '"3/2"' in r.stdout


def test_build_decimal_default_import():
    r = run("build", input_='[Decimal("1.5")], [], None')
    assert r.returncode == 0, r.stderr
    assert '"1.5"' in r.stdout


def test_build_import_option_binds_module_attribute():
    expr = ('[16], [Rule(lambda x: x > 2, '
            'Op(lambda x: int(sqrt(x)), label="sqrt"))], None, max_nodes=5')
    r = run("build", "--import", "math:sqrt", input_=expr)
    assert r.returncode == 0, r.stderr
    assert '"4"' in r.stdout


def test_build_import_option_multiple_names():
    expr = ('[10], [Rule(lambda x: x > 0, '
            'Op(lambda x: floor(sqrt(x)), label="floor sqrt"))], '
            'None, max_nodes=5')
    r = run("build", "--import", "math:sqrt,floor", input_=expr)
    assert r.returncode == 0, r.stderr


def test_build_import_option_module_itself():
    expr = ('[16], [Rule(lambda x: x > 2, '
            'Op(lambda x: int(math.sqrt(x)), label="sqrt"))], None, max_nodes=5')
    r = run("build", "--import", "math", input_=expr)
    assert r.returncode == 0, r.stderr


def test_build_import_rejects_unknown_module():
    r = run("build", "--import", "no_such_module_xyz",
            input_='[1], [], None')
    assert r.returncode != 0
    assert "cannot import module" in r.stderr
    assert "Traceback" not in r.stderr


def test_build_import_rejects_unknown_attribute():
    r = run("build", "--import", "math:not_a_math_function",
            input_='[1], [], None')
    assert r.returncode != 0
    assert "not_a_math_function" in r.stderr
    assert "Traceback" not in r.stderr


def test_validate_pipeline_still_works():
    expr = ('range(1,5), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], '
            'Op(lambda x: x+2, label="+2")')
    build = run("build", input_=expr)
    assert build.returncode == 0
    validate = run("validate", input_=build.stdout)
    assert validate.returncode == 0, validate.stderr


def test_unknown_subcommand_exits_nonzero():
    r = run("nonsense")
    assert r.returncode != 0


# ---- viter one-shot CLI (stdin / file) --------------------------------------

def test_viter_renders_svg_from_stdin():
    expr = ('range(1, 8), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], '
            'Op(lambda x: x+2, label="+2")')
    r = run_viter(input_=expr)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("<?xml")
    assert "<svg" in r.stdout


def test_viter_renders_svg_from_file(tmp_path):
    vit = tmp_path / "test.vit"
    vit.write_text("range(1, 8),\n"
                   "[Rule(lambda x: x%3==0, Op(lambda x: x//3))],\n"
                   "Op(lambda x: x+2)\n")
    out = tmp_path / "out.svg"
    r = run_viter(str(vit), "-o", str(out))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "<svg" in body


def test_viter_file_with_shebang_and_comments(tmp_path):
    vit = tmp_path / "demo.vit"
    vit.write_text("#!/usr/bin/env viter\n"
                   "# Descent graph\n"
                   "range(1, 8),\n"
                   "[Rule(lambda x: x%3==0, Op(lambda x: x//3))],\n"
                   "Op(lambda x: x+2)\n")
    r = run_viter(str(vit))
    assert r.returncode == 0, r.stderr
    assert "<svg" in r.stdout


def test_viter_help_shows_render_help_not_group_help():
    r = run_viter("--help")
    assert r.returncode == 0
    assert "FILE" in r.stdout
    assert "--max-nodes" in r.stdout


def test_viter_version_flag_reports_tool_version():
    from visiter import __version__
    r = run_viter("--version")
    assert r.returncode == 0, r.stderr
    assert __version__ in r.stdout


def test_viter_warns_on_node_cap_hit():
    expr = ('[0], [Rule(lambda x: True, '
            'Op(lambda x: x+1, label="+1"))], None')
    r = run_viter("--max-nodes", "5", input_=expr)
    assert r.returncode == 0, r.stderr
    assert "node count reached 5" in r.stderr


def test_viter_file_max_nodes_overrides_cli_flag():
    # When the .vit file carries its own max_nodes, the CLI flag
    # must not fight it — setdefault semantics.
    expr = ('[0], [Rule(lambda x: True, '
            'Op(lambda x: x+1, label="+1"))], None, '
            'max_nodes=20')
    r = run_viter("--max-nodes", "5", input_=expr)
    assert r.returncode == 0, r.stderr
    assert "node count reached 5" not in r.stderr


def test_viter_render_option_forwarded_to_to_dot(tmp_path):
    out = tmp_path / "factors.svg"
    expr = ('[6], [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], '
            'Op(lambda x: x+2, label="+2"), max_depth=3')
    r = run_viter("--render", "show_factors=True", "-o", str(out),
                  input_=expr)
    assert r.returncode == 0, r.stderr
    body = out.read_text(encoding="utf-8")
    assert "2" in body and "3" in body


def test_viter_format_dot_writes_plain_dot_to_stdout():
    expr = ('[1], [], Op(lambda x: x+1, label="+1"), '
            'max_nodes=3, on_limit="stop"')
    r = run_viter("-f", "dot", input_=expr)
    assert r.returncode == 0, r.stderr
    assert "digraph" in r.stdout


def test_viter_fraction_default_namespace():
    expr = ('[Fraction(1)], [Rule(lambda x: True, '
            'Op(lambda x: 1 + 1/x, label="step"))], '
            'None, max_depth=4, key_type="number"')
    r = run_viter(input_=expr)
    assert r.returncode == 0, r.stderr
    assert "3/2" in r.stdout


def test_viter_import_option_propagates(tmp_path):
    out = tmp_path / "sqrt.svg"
    expr = ('[16], [Rule(lambda x: x > 2, '
            'Op(lambda x: int(sqrt(x)), label="sqrt"))], '
            'None, max_nodes=5')
    r = run_viter("--import", "math:sqrt", "-o", str(out), input_=expr)
    assert r.returncode == 0, r.stderr
    assert out.exists()
