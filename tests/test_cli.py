"""Tests for the top-level `visiter` CLI surface."""

import os
import subprocess
import sys

import pytest

VENV_BIN = os.path.dirname(sys.executable)
ENV = {**os.environ, "PATH": VENV_BIN + os.pathsep + os.environ.get("PATH", "")}


def run(*args, input_=None):
    return subprocess.run(["visiter", *args], capture_output=True, text=True,
                          input=input_, env=ENV)


def run_viter(*args):
    return subprocess.run(["viter", *args], capture_output=True, text=True,
                          env=ENV)


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
    # Help should describe the tool, not just dump usage.
    assert "iteration" in out.lower() or "graph" in out.lower()


@pytest.mark.parametrize("sub", ["build", "to-dot", "validate", "analyze",
                                  "render"])
def test_subcommand_help_works(sub):
    r = run(sub, "--help")
    assert r.returncode == 0, r.stderr
    assert "Usage" in r.stdout or "usage" in r.stdout


def test_top_level_help_mentions_render():
    # `render` is the one-shot shortcut; it must be discoverable from
    # the top-level help, same as the other pipe subcommands.
    r = run("--help")
    assert r.returncode == 0
    assert "render" in r.stdout


# ---- viter one-shot CLI ----------------------------------------------------


def test_viter_renders_svg_end_to_end(tmp_path):
    out = tmp_path / "descent.svg"
    expr = ('range(1, 8), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], '
            'default=Op(lambda x: x+2, label="+2")')
    r = run_viter(expr, "-o", str(out))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("<?xml")
    assert "<svg" in body


def test_viter_help_shows_render_help_not_group_help():
    # `viter --help` should jump straight to the render subcommand
    # help — group help would mention siblings (build, to-dot, …)
    # which viter deliberately hides.
    r = run_viter("--help")
    assert r.returncode == 0
    assert "ARGSTRING" in r.stdout
    assert "--max-nodes" in r.stdout


def test_viter_version_flag_reports_tool_version():
    from visiter import __version__
    r = run_viter("--version")
    assert r.returncode == 0, r.stderr
    assert __version__ in r.stdout


def test_viter_warns_on_node_cap_hit(tmp_path):
    out = tmp_path / "capped.svg"
    expr = ('[0], [Rule(lambda x: True, '
            'Op(lambda x: x+1, label="+1"))], default=None')
    r = run_viter(expr, "--max-nodes", "5", "-o", str(out))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    # Truncation warning goes to stderr, not stdout — so a pipeline
    # that redirects stdout to a file still sees the message.
    assert "node count reached 5" in r.stderr


def test_viter_argstring_max_nodes_overrides_cli_flag(tmp_path):
    # When the argstring carries its own max_nodes, the CLI flag
    # must not fight it — setdefault semantics.
    out = tmp_path / "explicit.svg"
    expr = ('[0], [Rule(lambda x: True, '
            'Op(lambda x: x+1, label="+1"))], default=None, '
            'max_nodes=20')
    r = run_viter(expr, "--max-nodes", "5", "-o", str(out))
    assert r.returncode == 0, r.stderr
    # Argstring wins → 20, not 5 — so the 5-cap warning must NOT fire.
    assert "node count reached 5" not in r.stderr


def test_viter_render_argstring_forwarded_to_to_dot(tmp_path):
    out = tmp_path / "factors.svg"
    expr = ('[6], [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], '
            'default=Op(lambda x: x+2, label="+2"), max_depth=3')
    r = run_viter(expr, "--render", "show_factors=True", "-o", str(out))
    assert r.returncode == 0, r.stderr
    body = out.read_text(encoding="utf-8")
    # 6 = 2·3 → the factorization glyph should appear in the SVG.
    assert "2" in body and "3" in body


def test_viter_format_dot_writes_plain_dot_source(tmp_path):
    out = tmp_path / "graph.dot"
    expr = ('[1], [], default=Op(lambda x: x+1, label="+1"), '
            'max_nodes=3, on_limit="stop"')
    r = run_viter(expr, "-f", "dot", "-o", str(out))
    assert r.returncode == 0, r.stderr
    # DOT output is plain text, not binary.
    text = out.read_text(encoding="utf-8")
    assert "digraph" in text


def test_viter_fraction_default_namespace(tmp_path):
    out = tmp_path / "golden.svg"
    expr = ('[Fraction(1)], [Rule(lambda x: True, '
            'Op(lambda x: 1 + 1/x, label="step"))], '
            'default=None, max_depth=4, key_type="number"')
    r = run_viter(expr, "-o", str(out))
    assert r.returncode == 0, r.stderr
    body = out.read_text(encoding="utf-8")
    # Fraction values like 3/2 should appear as node labels.
    assert "3/2" in body


def test_viter_import_option_propagates(tmp_path):
    out = tmp_path / "sqrt.svg"
    expr = ('[16], [Rule(lambda x: x > 2, '
            'Op(lambda x: int(sqrt(x)), label="sqrt"))], '
            'default=None, max_nodes=5')
    r = run_viter("--import", "math:sqrt", expr, "-o", str(out))
    assert r.returncode == 0, r.stderr
    assert out.exists()


def test_viter_requires_output_flag():
    expr = ('range(1,3), [], default=None')
    r = run_viter(expr)
    assert r.returncode != 0
    # Error surfaces via click's usage message, not a traceback.
    assert "Traceback" not in r.stderr


def test_iterate_pipeline_still_works():
    expr = ('range(1,8), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], default=Op(lambda x: x+2, label="+2")')
    r = run("build", expr)
    assert r.returncode == 0, r.stderr
    assert '"schema_version": "1"' in r.stdout
    assert '"op_order"' in r.stdout


def test_validate_pipeline_still_works():
    expr = ('range(1,5), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, label="÷3"))], default=Op(lambda x: x+2, label="+2")')
    build = run("build", expr)
    assert build.returncode == 0
    validate = run("validate", input_=build.stdout)
    assert validate.returncode == 0, validate.stderr


def test_unknown_subcommand_exits_nonzero():
    r = run("nonsense")
    assert r.returncode != 0


def test_iterate_pipeline_with_auto_labeled_ops():
    # Lambdas without an explicit label must work in the CLI eval path:
    # inspect.getsource has no file backing unless the CLI wires its
    # eval source into linecache.
    expr = ('range(1, 8), [Rule(lambda x: x % 3 == 0, '
            'Op(lambda x: x // 3))], default=Op(lambda x: x + 2)')
    r = run("build", expr)
    assert r.returncode == 0, r.stderr
    assert '"x // 3"' in r.stdout
    assert '"x + 2"' in r.stdout


def test_iterate_fraction_default_import():
    # Fraction is in the default eval namespace, so stdlib rationals
    # work on the CLI without any --import boilerplate.
    expr = ('[Fraction(1)], rules=[Rule(lambda x: True, '
            'Op(lambda x: 1 + 1/x, label="step"))], default=None, '
            'max_depth=3, key_type="number"')
    r = run("build", expr)
    assert r.returncode == 0, r.stderr
    assert '"key_type": "number"' in r.stdout
    assert '"3/2"' in r.stdout


def test_iterate_decimal_default_import():
    # Decimal is similarly pre-bound.
    r = run("build", '[Decimal("1.5")], rules=[], default=None')
    assert r.returncode == 0, r.stderr
    assert '"1.5"' in r.stdout


def test_iterate_import_option_binds_module_attribute():
    # `--import math:sqrt` makes sqrt available in the eval namespace.
    expr = ('[16], rules=[Rule(lambda x: x > 2, '
            'Op(lambda x: int(sqrt(x)), label="sqrt"))], default=None, max_nodes=5')
    r = run("build", "--import", "math:sqrt", expr)
    assert r.returncode == 0, r.stderr
    assert '"4"' in r.stdout  # 16 → 4 → 2


def test_iterate_import_option_multiple_names():
    # Comma-separated names on one --import.
    expr = ('[10], rules=[Rule(lambda x: x > 0, '
            'Op(lambda x: floor(sqrt(x)), label="floor sqrt"))], '
            'default=None, max_nodes=5')
    r = run("build", "--import", "math:sqrt,floor", expr)
    assert r.returncode == 0, r.stderr


def test_iterate_import_option_module_itself():
    # Bare `MODULE` binds the module; use dotted access in the argstring.
    expr = ('[16], rules=[Rule(lambda x: x > 2, '
            'Op(lambda x: int(math.sqrt(x)), label="sqrt"))], default=None, max_nodes=5')
    r = run("build", "--import", "math", expr)
    assert r.returncode == 0, r.stderr


def test_iterate_import_rejects_unknown_module():
    r = run("build", "--import", "no_such_module_xyz",
            '[1], rules=[], default=None')
    assert r.returncode != 0
    # Error surfaces as a click usage error, not a Python traceback.
    assert "cannot import module" in r.stderr
    assert "Traceback" not in r.stderr


def test_iterate_import_rejects_unknown_attribute():
    r = run("build", "--import", "math:not_a_math_function",
            '[1], rules=[], default=None')
    assert r.returncode != 0
    # rich-click wraps long error messages across the box drawing, so
    # we can't assert on the exact phrase; verify the attribute name
    # appears and no Python traceback leaks out.
    assert "not_a_math_function" in r.stderr
    assert "Traceback" not in r.stderr


def test_iterate_pipeline_multiline_argstring_auto_labels():
    # Multiline argstrings are idiomatic for readability. Auto-derived
    # labels must work even though `inspect.getsourcelines` on a lambda
    # on the 3rd line would otherwise return a syntactically incomplete
    # fragment that `ast.parse` refuses.
    expr = ('range(1, 8),\n'
            '[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],\n'
            'default=Op(lambda x: x + 2)')
    r = run("build", expr)
    assert r.returncode == 0, r.stderr
    assert '"x + 2"' in r.stdout
