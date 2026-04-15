"""Top-level dispatcher for the `visiter` command.

Subcommands are registered in `SUBCOMMANDS` as `name → "module:function"`
strings. Each subcommand keeps its own `main()` and parses its own
remaining argv, so adding a new one means writing a tiny module with a
`main()` and adding one entry here.
"""

import importlib
import sys

SUBCOMMANDS = {
    "iterate":  "visiter.iteration:main",
    "to-dot":   "visiter.to_dot:main",
    "validate": "visiter.validate:main",
}


def _print_usage(stream=sys.stderr):
    stream.write("usage: visiter SUBCOMMAND [ARGS...]\n\n")
    stream.write("Subcommands:\n")
    for name in SUBCOMMANDS:
        stream.write(f"  {name}\n")
    stream.write("\nRun 'visiter SUBCOMMAND' with no further args to see its usage.\n")


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        _print_usage(sys.stdout if argv else sys.stderr)
        sys.exit(0 if argv else 2)
    cmd, rest = argv[0], argv[1:]
    if cmd not in SUBCOMMANDS:
        sys.stderr.write(f"visiter: unknown subcommand '{cmd}'\n\n")
        _print_usage()
        sys.exit(2)
    module_path, fn_name = SUBCOMMANDS[cmd].split(":")
    module = importlib.import_module(module_path)
    fn = getattr(module, fn_name)
    sys.argv = [f"visiter {cmd}"] + rest
    fn()


if __name__ == "__main__":
    main()
