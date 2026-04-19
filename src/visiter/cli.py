"""``viter`` CLI — execute .vit files as Python scripts.

A .vit file is a Python script that uses the visiter fluent API
to build, transform, and render iteration graphs.  The CLI provides
a pre-populated namespace (``viter``, ``Match``, ``OnLimit``,
``to_dot``, ``Graph``, ``NxFilter``, ``write``, ``Fraction``,
``Decimal``) and executes the file via ``exec``.

Usage::

    viter script.vit                    # run with defaults
    viter script.vit --cap-a 4          # pass args to the script
    viter --version                     # show version
    viter --help                        # show help

All arguments after the .vit file path are passed through to the
script as ``sys.argv`` (the script can use ``argparse`` or raw
``sys.argv`` to parse them).
"""

import sys
from pathlib import Path

from . import __version__


def _build_namespace(vit_path):
    """Build the exec namespace for a .vit file.

    Pre-binds the visiter API so .vit files don't need boilerplate
    imports (though they can add their own for IDE support).
    """
    from decimal import Decimal
    from fractions import Fraction

    from .builder import Match, OnLimit, viter
    from .filters import NxFilter
    from .graph import Graph
    from .io import write
    from .to_dot import to_dot

    return {
        "__file__": str(Path(vit_path).resolve()),
        "__name__": "__main__",
        # Core API
        "viter": viter,
        "Match": Match,
        "OnLimit": OnLimit,
        "to_dot": to_dot,
        "Graph": Graph,
        # Filters
        "NxFilter": NxFilter,
        # I/O
        "write": write,
        # Convenience types
        "Fraction": Fraction,
        "Decimal": Decimal,
    }


def _read_vit(path):
    """Read a .vit file and return (source, resolved_path).

    A leading ``#!`` shebang is left intact — Python's parser treats it
    as a comment, so no special handling is needed.
    """
    p = Path(path)
    if not p.exists():
        print(f"viter: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    source = p.read_text(encoding="utf-8")
    return source, str(p.resolve())


def _exec_vit(source, vit_path, script_argv):
    """Execute a .vit script in the visiter namespace.

    Sets sys.argv to *script_argv* for the duration of the exec,
    restoring it afterward.
    """
    ns = _build_namespace(vit_path)
    code = compile(source, vit_path, "exec")

    saved_argv = sys.argv
    sys.argv = script_argv
    try:
        exec(code, ns)
    finally:
        sys.argv = saved_argv


def main():
    """Entry point for the ``viter`` console script."""
    args = sys.argv[1:]

    # Handle --version / -V before anything else.
    if not args or args[0] in ("-h", "--help"):
        print(f"viter {__version__} — execute .vit files\n")
        print("Usage: viter <script.vit> [script-args...]")
        print("       viter --version")
        print()
        print("A .vit file is a Python script using the visiter fluent API.")
        print("All arguments after the .vit path are passed to the script")
        print("as sys.argv.")
        sys.exit(0)

    if args[0] in ("-V", "--version"):
        print(f"viter {__version__}")
        sys.exit(0)

    vit_path = args[0]
    script_argv = [vit_path] + args[1:]

    source, resolved_path = _read_vit(vit_path)
    _exec_vit(source, resolved_path, script_argv)


if __name__ == "__main__":
    main()
