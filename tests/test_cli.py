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


def test_top_level_version_flag():
    from visiter import __version__
    r = run("--version")
    assert r.returncode == 0, r.stderr
    assert __version__ in r.stdout


def test_top_level_help_describes_tool_and_lists_subcommands():
    r = run("--help")
    assert r.returncode == 0
    out = r.stdout
    assert "iterate" in out
    assert "to-dot" in out
    assert "validate" in out
    assert "analyze" in out
    # Help should describe the tool, not just dump usage.
    assert "iteration" in out.lower() or "graph" in out.lower()


@pytest.mark.parametrize("sub", ["iterate", "to-dot", "validate", "analyze"])
def test_subcommand_help_works(sub):
    r = run(sub, "--help")
    assert r.returncode == 0, r.stderr
    assert "Usage" in r.stdout or "usage" in r.stdout


def test_iterate_pipeline_still_works():
    expr = ('range(1,8), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, "÷3"))], default=Op(lambda x: x+2, "+2")')
    r = run("iterate", expr)
    assert r.returncode == 0, r.stderr
    assert '"schema_version": "1"' in r.stdout
    assert '"op_order"' in r.stdout


def test_validate_pipeline_still_works():
    expr = ('range(1,5), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, "÷3"))], default=Op(lambda x: x+2, "+2")')
    iterate = run("iterate", expr)
    assert iterate.returncode == 0
    validate = run("validate", input_=iterate.stdout)
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
    r = run("iterate", expr)
    assert r.returncode == 0, r.stderr
    assert '"x // 3"' in r.stdout
    assert '"x + 2"' in r.stdout


def test_iterate_fraction_default_import():
    # Fraction is in the default eval namespace, so stdlib rationals
    # work on the CLI without any --import boilerplate.
    expr = ('[Fraction(1)], rules=[Rule(lambda x: True, '
            'Op(lambda x: 1 + 1/x, "step"))], default=None, '
            'max_depth=3, key_type="number"')
    r = run("iterate", expr)
    assert r.returncode == 0, r.stderr
    assert '"key_type": "number"' in r.stdout
    assert '"3/2"' in r.stdout


def test_iterate_decimal_default_import():
    # Decimal is similarly pre-bound.
    r = run("iterate", '[Decimal("1.5")], rules=[], default=None')
    assert r.returncode == 0, r.stderr
    assert '"1.5"' in r.stdout


def test_iterate_import_option_binds_module_attribute():
    # `--import math:sqrt` makes sqrt available in the eval namespace.
    expr = ('[16], rules=[Rule(lambda x: x > 2, '
            'Op(lambda x: int(sqrt(x)), "sqrt"))], default=None, max_nodes=5')
    r = run("iterate", "--import", "math:sqrt", expr)
    assert r.returncode == 0, r.stderr
    assert '"4"' in r.stdout  # 16 → 4 → 2


def test_iterate_import_option_multiple_names():
    # Comma-separated names on one --import.
    expr = ('[10], rules=[Rule(lambda x: x > 0, '
            'Op(lambda x: floor(sqrt(x)), "floor sqrt"))], '
            'default=None, max_nodes=5')
    r = run("iterate", "--import", "math:sqrt,floor", expr)
    assert r.returncode == 0, r.stderr


def test_iterate_import_option_module_itself():
    # Bare `MODULE` binds the module; use dotted access in the argstring.
    expr = ('[16], rules=[Rule(lambda x: x > 2, '
            'Op(lambda x: int(math.sqrt(x)), "sqrt"))], default=None, max_nodes=5')
    r = run("iterate", "--import", "math", expr)
    assert r.returncode == 0, r.stderr


def test_iterate_import_rejects_unknown_module():
    r = run("iterate", "--import", "no_such_module_xyz",
            '[1], rules=[], default=None')
    assert r.returncode != 0
    # Error surfaces as a click usage error, not a Python traceback.
    assert "cannot import module" in r.stderr
    assert "Traceback" not in r.stderr


def test_iterate_import_rejects_unknown_attribute():
    r = run("iterate", "--import", "math:not_a_math_function",
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
            '[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],\n'
            'default=Op(lambda x: x + 2)')
    r = run("iterate", expr)
    assert r.returncode == 0, r.stderr
    assert '"x + 2"' in r.stdout
