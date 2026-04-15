"""CLI: validate a graph JSON document against the bundled JSON Schema.

Reads JSON from stdin (or --input FILE) and validates it against
`schemas/v1/graph.schema.json`. Exits 0 on success, 1 on validation
errors (printed to stderr), 2 on usage/IO errors.

Requires the `jsonschema` package; install the `[validate]` extra:
    pip install visiter[validate]
"""

import json
import sys
from importlib.resources import files


def _load_schema(version="1"):
    resource = files("visiter").joinpath(f"schemas/v{version}/graph.schema.json")
    with resource.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    argv = sys.argv[1:]
    input_path = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            sys.stdout.write(
                "usage: visiter validate [--input FILE]\n"
                "  Validates a graph JSON document (stdin or --input) against\n"
                "  the bundled JSON Schema. Exit 0=valid, 1=invalid, 2=usage.\n"
            )
            sys.exit(0)
        elif a == "--input":
            if i + 1 >= len(argv):
                sys.stderr.write("visiter validate: --input requires a path\n")
                sys.exit(2)
            input_path = argv[i + 1]
            i += 2
        else:
            sys.stderr.write(f"visiter validate: unexpected argument {a!r}\n")
            sys.exit(2)

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        sys.stderr.write(
            "visiter validate: requires the 'jsonschema' package.\n"
            "  Install with: pip install visiter[validate]\n"
        )
        sys.exit(2)

    if input_path is None:
        doc = json.load(sys.stdin)
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            doc = json.load(f)

    version = doc.get("schema_version", "1") if isinstance(doc, dict) else "1"
    try:
        schema = _load_schema(version)
    except FileNotFoundError:
        sys.stderr.write(
            f"visiter validate: no bundled schema for version {version!r}\n"
        )
        sys.exit(1)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        for e in errors:
            loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
            sys.stderr.write(f"{loc}: {e.message}\n")
        sys.exit(1)

    sys.stdout.write(f"valid (schema v{version})\n")


if __name__ == "__main__":
    main()
