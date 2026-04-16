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
    # Help should describe the tool, not just dump usage.
    assert "iteration" in out.lower() or "graph" in out.lower()


@pytest.mark.parametrize("sub", ["iterate", "to-dot", "validate"])
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
