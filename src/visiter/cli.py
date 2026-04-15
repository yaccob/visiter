"""Top-level `visiter` CLI.

Built on rich-click. Each subcommand keeps the project's deliberate
"single positional Python expression that is eval'd into the wrapped
function call" contract — this avoids per-flag DSL drift as the
underlying Python API grows. The expression is spliced into a call
that has `Op`, `Rule`, `iterate`, `to_dot`, and (for `to-dot`/`validate`)
`graph` pre-bound in its eval namespace.
"""

import json
import sys

import rich_click as click

from . import __version__
from .iteration import Op, Rule, iterate
from .to_dot import to_dot

click.rich_click.USE_MARKDOWN = True
click.rich_click.MAX_WIDTH = 100
click.rich_click.SHOW_ARGUMENTS = True

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

ITERATE_EXAMPLE = """\
**Example**

```
visiter iterate 'range(1, 30),
    [Rule(lambda x: x%3==0, Op(lambda x: x//3, "÷3"))],
    default=Op(lambda x: x+2, "+2")'
```
"""

TO_DOT_EXAMPLE = """\
**Example**

```
visiter iterate '...' | visiter to-dot 'anchor=1, radius=8' | dot -Tsvg > out.svg
```
"""

VALIDATE_EXAMPLE = """\
**Example**

```
visiter iterate '...' | visiter validate
```
"""


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, "-V", "--version", prog_name="visiter")
def cli():
    """**VisIter** — build and visualize orbit graphs for discrete
    iterations under guarded rules.

    The three subcommands compose via shell pipes — `iterate` builds a
    graph and writes JSON; `to-dot` reads JSON and writes Graphviz DOT;
    `validate` checks a graph JSON document against the bundled JSON
    Schema. Hand the DOT to system Graphviz (`dot -Tsvg/-Tpdf/...`) for
    the final image.

    See `visiter SUBCOMMAND --help` for per-command details, or the
    project tutorial at https://github.com/yaccob/visiter for a walk-through.
    """


@cli.command("iterate", epilog=ITERATE_EXAMPLE)
@click.argument("argstring")
def iterate_cmd(argstring):
    """Build an iteration graph and write JSON to stdout.

    ARGSTRING is a Python expression spliced into iterate(<ARGSTRING>)
    and eval'd. `Op`, `Rule`, and `iterate` are pre-bound in the eval
    namespace.
    """
    ns = {"Rule": Rule, "Op": Op, "iterate": iterate}
    graph = eval(f"iterate({argstring})", ns)
    json.dump(graph, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


@cli.command("to-dot", epilog=TO_DOT_EXAMPLE)
@click.argument("argstring", required=False, default="")
@click.option("--input", "input_path", default="-", show_default=True,
              help="Input JSON file ('-' for stdin).")
@click.option("-o", "--output",
              help="Output DOT file (default: stdout).")
def to_dot_cmd(argstring, input_path, output):
    """Render a graph dict (JSON on stdin or --input) as Graphviz DOT.

    ARGSTRING is a Python expression spliced into to_dot(graph,
    <ARGSTRING>) and eval'd. `to_dot` and `graph` are pre-bound.
    """
    if input_path == "-":
        graph = json.load(sys.stdin)
    else:
        with open(input_path) as f:
            graph = json.load(f)

    ns = {"graph": graph, "to_dot": to_dot}
    call = (f"to_dot(graph, {argstring})"
            if argstring.strip() else "to_dot(graph)")
    dot = eval(call, ns)

    if output:
        with open(output, "w") as f:
            f.write(dot.source)
    else:
        sys.stdout.write(dot.source + "\n")


@cli.command("validate", epilog=VALIDATE_EXAMPLE)
@click.option("--input", "input_path", default="-", show_default=True,
              help="Input JSON file ('-' for stdin).")
def validate_cmd(input_path):
    """Validate a graph JSON document against the bundled JSON Schema.

    Exit codes: 0 valid, 1 invalid, 2 usage / missing dependency.
    Requires the [validate] extra (jsonschema).
    """
    from importlib.resources import files

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        click.echo("visiter validate: requires the 'jsonschema' package.\n"
                   "  Install with: pip install visiter[validate]",
                   err=True)
        sys.exit(2)

    if input_path == "-":
        doc = json.load(sys.stdin)
    else:
        with open(input_path) as f:
            doc = json.load(f)

    version = doc.get("schema_version", "1") if isinstance(doc, dict) else "1"
    resource = files("visiter").joinpath(f"schemas/v{version}/graph.schema.json")
    if not resource.is_file():
        click.echo(f"visiter validate: no bundled schema for version {version!r}",
                   err=True)
        sys.exit(1)
    schema = json.loads(resource.read_text(encoding="utf-8"))

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc),
                    key=lambda e: list(e.absolute_path))
    if errors:
        for e in errors:
            loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
            click.echo(f"{loc}: {e.message}", err=True)
        sys.exit(1)

    click.echo(f"valid (schema v{version})")


def main():
    cli()


if __name__ == "__main__":
    main()
