"""Top-level `visiter` CLI.

Built on rich-click. Each subcommand keeps the project's deliberate
"single positional Python expression that is eval'd into the wrapped
function call" contract — this avoids per-flag DSL drift as the
underlying Python API grows. The expression is spliced into a call
that has `Op`, `Rule`, `iterate`, `to_dot`, and (for `to-dot`/`validate`)
`graph` pre-bound in its eval namespace.

The eval namespace also comes with `Fraction` and `Decimal` bound by
default — the common stdlib numeric types that motivate
`iterate(..., key_type=...)`. Anything beyond those is opt-in via the
repeatable `--import` option: `--import MODULE` binds the module
under its own name, `--import MODULE:NAME[,NAME...]` binds specific
attributes. See each subcommand's `--help`.
"""

import importlib
import itertools
import json
import linecache
import sys
from decimal import Decimal
from fractions import Fraction

import rich_click as click

from . import __version__
from .iteration import Op, Rule, iterate
from .to_dot import to_dot

_eval_counter = itertools.count()

# Stdlib numeric types bound by default in the eval namespace. These
# are the types that motivated `iterate(..., key_type=...)` (rational
# and arbitrary-precision decimal arithmetic), so having them
# available without an explicit --import covers the common case.
_DEFAULT_EVAL_BINDINGS = {"Fraction": Fraction, "Decimal": Decimal}

_IMPORT_HELP = (
    "Add names to the eval namespace. `MODULE` binds the module "
    "itself; `MODULE:NAME[,NAME...]` binds specific attributes from "
    "it. Repeatable. Example: `--import sympy:Rational,Integer`."
)


def _resolve_imports(specs):
    """Parse --import specs into a {name: object} mapping.

    Raises ``click.BadParameter`` with a clear message on malformed
    specs, missing modules, or missing module attributes, so the error
    reaches the user as a usage error rather than a Python traceback.
    """
    bindings = {}
    for spec in specs:
        if ":" in spec:
            module_part, names_part = spec.split(":", 1)
            module_name = module_part.strip()
            if not module_name:
                raise click.BadParameter(
                    f"--import {spec!r}: module name is empty")
            try:
                mod = importlib.import_module(module_name)
            except ImportError as exc:
                raise click.BadParameter(
                    f"--import {spec!r}: cannot import module "
                    f"{module_name!r} ({exc})") from exc
            names = [n.strip() for n in names_part.split(",") if n.strip()]
            if not names:
                raise click.BadParameter(
                    f"--import {spec!r}: no attribute names after ':'")
            for name in names:
                if not hasattr(mod, name):
                    raise click.BadParameter(
                        f"--import {spec!r}: module {module_name!r} "
                        f"has no attribute {name!r}")
                bindings[name] = getattr(mod, name)
        else:
            module_name = spec.strip()
            if not module_name:
                raise click.BadParameter(
                    "--import received an empty string")
            try:
                bindings[module_name] = importlib.import_module(module_name)
            except ImportError as exc:
                raise click.BadParameter(
                    f"--import {spec!r}: cannot import module "
                    f"{module_name!r} ({exc})") from exc
    return bindings


def _eval_with_source(source, ns):
    """Eval `source` so that inspect.getsource works on its lambdas.

    Compiles with a unique synthetic filename and registers the source
    lines in ``linecache`` so that ``inspect.getsourcefile`` accepts
    the filename (via its linecache fallback) and ``inspect.findsource``
    can retrieve the lines. This makes the `Op(lambda x: ...)`
    no-label idiom work when lambdas are constructed by the CLI's
    eval-based argstring contract.
    """
    filename = f"<visiter-eval-{next(_eval_counter)}>"
    lines = [line + "\n" for line in source.splitlines()] or ["\n"]
    linecache.cache[filename] = (len(source), None, lines, filename)
    code = compile(source, filename, "eval")
    return eval(code, ns)

click.rich_click.USE_MARKDOWN = True
click.rich_click.MAX_WIDTH = 100
click.rich_click.SHOW_ARGUMENTS = True

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

BUILD_EXAMPLE = """\
**Example**

```
visiter build 'range(1, 30),
    [Rule(lambda x: x%3==0, Op(lambda x: x//3, label="÷3"))],
    default=Op(lambda x: x+2, label="+2")'
```
"""

TO_DOT_EXAMPLE = """\
**Example**

```
visiter build '...' | visiter to-dot 'anchor=1, radius=8' | dot -Tsvg > out.svg
```
"""

VALIDATE_EXAMPLE = """\
**Example**

```
visiter build '...' | visiter validate
```
"""

ANALYZE_EXAMPLE = """\
**Examples**

Scalars and dicts flow through as JSON:

```
visiter build '...' | visiter analyze 'nx.number_of_nodes(graph)'
visiter build '...' | visiter analyze 'nx.in_degree_centrality(graph)'
```

If the expression returns a NetworkX graph, it is re-emitted as a
VisIter graph dict so the next stage can render it:

```
visiter build '...' \\
  | visiter analyze 'nx.condensation(graph)' \\
  | visiter to-dot '' | dot -Tsvg > scc.svg
```
"""


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, "-V", "--version", prog_name="visiter")
def cli():
    """**VisIter** — build and visualize orbit graphs for discrete
    iterations under guarded rules.

    Pipe-composable subcommands — `build` constructs the orbit graph
    and writes JSON; `to-dot` reads JSON and writes Graphviz DOT;
    `validate` checks a graph JSON document against the bundled JSON
    Schema; `analyze` bridges to NetworkX for arbitrary graph
    algorithms on the JSON. Hand the DOT to system Graphviz
    (`dot -Tsvg/-Tpdf/...`) for the final image.

    For the one-shot path (argstring → image in one call, with safety
    caps) use `visiter render …` or its shorter alias `viter`.

    See `visiter SUBCOMMAND --help` for per-command details, or the
    project tutorial at https://github.com/yaccob/visiter for a walk-through.
    """


@cli.command("build", epilog=BUILD_EXAMPLE)
@click.argument("argstring")
@click.option("--import", "imports", multiple=True, metavar="SPEC",
              help=_IMPORT_HELP)
def build_cmd(argstring, imports):
    """Build an orbit graph and write JSON to stdout.

    ARGSTRING is a Python expression spliced into iterate(<ARGSTRING>)
    and eval'd (the Python-side name of the graph-building function is
    `iterate`; this subcommand is its CLI-friendly alias). `Op`, `Rule`,
    `iterate`, plus `Fraction` and `Decimal` are pre-bound; add more via
    `--import`.
    """
    ns = {"Rule": Rule, "Op": Op, "iterate": iterate,
          **_DEFAULT_EVAL_BINDINGS, **_resolve_imports(imports)}
    graph = _eval_with_source(f"iterate({argstring})", ns)
    json.dump(graph, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


@cli.command("to-dot", epilog=TO_DOT_EXAMPLE)
@click.argument("argstring", required=False, default="")
@click.option("--input", "input_path", default="-", show_default=True,
              help="Input JSON file ('-' for stdin).")
@click.option("-o", "--output",
              help="Output DOT file (default: stdout).")
@click.option("--import", "imports", multiple=True, metavar="SPEC",
              help=_IMPORT_HELP)
def to_dot_cmd(argstring, input_path, output, imports):
    """Render a graph dict (JSON on stdin or --input) as Graphviz DOT.

    ARGSTRING is a Python expression spliced into to_dot(graph,
    <ARGSTRING>) and eval'd. `to_dot` and `graph`, plus `Fraction`
    and `Decimal`, are pre-bound; add more via `--import`.
    """
    if input_path == "-":
        graph = json.load(sys.stdin)
    else:
        with open(input_path) as f:
            graph = json.load(f)

    ns = {"graph": graph, "to_dot": to_dot,
          **_DEFAULT_EVAL_BINDINGS, **_resolve_imports(imports)}
    call = (f"to_dot(graph, {argstring})"
            if argstring.strip() else "to_dot(graph)")
    dot = _eval_with_source(call, ns)

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


@cli.command("analyze", epilog=ANALYZE_EXAMPLE)
@click.argument("argstring")
@click.option("--input", "input_path", default="-", show_default=True,
              help="Input JSON file ('-' for stdin).")
@click.option("--import", "imports", multiple=True, metavar="SPEC",
              help=_IMPORT_HELP)
def analyze_cmd(argstring, input_path, imports):
    """Run a NetworkX computation against a graph JSON document.

    ARGSTRING is a Python expression evaluated with `graph` (a
    `networkx.DiGraph` built from the input) and `nx` pre-bound, plus
    `Fraction` and `Decimal`; add more via `--import`. The result is
    written to stdout as JSON; if it is itself a NetworkX graph, it
    is converted back into VisIter's schema so the output can flow
    straight into `visiter to-dot`.

    Requires the [analytics] extra (networkx).
    """
    try:
        import networkx as nx
    except ImportError:
        click.echo("visiter analyze: requires the 'networkx' package.\n"
                   "  Install with: pip install visiter[analytics]",
                   err=True)
        sys.exit(2)

    from .analytics import to_networkx, from_networkx

    if input_path == "-":
        doc = json.load(sys.stdin)
    else:
        with open(input_path) as f:
            doc = json.load(f)

    graph = to_networkx(doc)
    ns = {"graph": graph, "nx": nx,
          **_DEFAULT_EVAL_BINDINGS, **_resolve_imports(imports)}
    result = _eval_with_source(argstring, ns)

    if isinstance(result, nx.Graph):
        payload = from_networkx(result)
    else:
        payload = result

    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


RENDER_EXAMPLE = """\
**Example**

```
viter 'range(1, 30),
    [Rule(lambda x: x%3==0, Op(lambda x: x//3, label="÷3"))],
    default=Op(lambda x: x+2, label="+2")' \\
  --render 'anchor=1, radius=8, direction="backward"' \\
  -o descent.svg
```
"""


# Safe defaults for one-shot rendering — tighter than `iterate`'s own
# defaults so typo'd rules don't silently consume minutes or gigabytes.
_RENDER_DEFAULT_MAX_NODES = 10_000
_RENDER_DEFAULT_TIME_LIMIT = "00:00:30"


@cli.command("render", epilog=RENDER_EXAMPLE)
@click.argument("argstring")
@click.option("--render", "render_args", default="", metavar="ARGSTRING",
              help="Python expression spliced into to_dot(graph, …). "
                   "Empty means to_dot defaults.")
@click.option("-f", "--format", "fmt", default="svg", show_default=True,
              help="Output format passed to Graphviz (svg, pdf, png, "
                   "dot, …).")
@click.option("-o", "--output", required=True, metavar="FILE",
              help="Output file path.")
@click.option("--max-nodes", type=int, default=_RENDER_DEFAULT_MAX_NODES,
              show_default=True,
              help="Safety cap on the BFS node count. Argstring can "
                   "override by passing `max_nodes=…` explicitly.")
@click.option("--max-depth", type=int, default=None,
              help="Optional BFS depth cap. Argstring can override.")
@click.option("--time-limit", default=_RENDER_DEFAULT_TIME_LIMIT,
              show_default=True, metavar="HH:MM:SS",
              help="Wall-clock limit on the build phase. Argstring "
                   "can override.")
@click.option("--import", "imports", multiple=True, metavar="SPEC",
              help=_IMPORT_HELP)
def render_cmd(argstring, render_args, fmt, output,
               max_nodes, max_depth, time_limit, imports):
    """Run the full pipeline (build → to-dot → Graphviz) in one call.

    ARGSTRING is the same Python expression you'd pass to `build`.
    --render takes the argstring you'd pass to `to-dot` (optional).

    Niederschwellig entry point: safe defaults (`--max-nodes 10000`,
    `--time-limit 00:00:30`, `on_limit="stop"` + a warning on stderr
    when the cap is hit) keep a typo'd rule from running away. Any
    of the safety caps can be overridden either via CLI flag or by
    passing the same kwarg explicitly in ARGSTRING.
    """
    from pathlib import Path

    # Wrap iterate() so the CLI's safety defaults apply but an
    # explicit kwarg in the argstring still wins. dict.setdefault
    # honours the caller-provided value when present.
    cap_was_hit = {"flag": False}

    def _iterate_with_caps(*args, **kwargs):
        effective_max = kwargs.get("max_nodes", max_nodes)
        kwargs.setdefault("max_nodes", max_nodes)
        kwargs.setdefault("time_limit", time_limit)
        kwargs.setdefault("on_limit", "stop")
        if max_depth is not None:
            kwargs.setdefault("max_depth", max_depth)
        g = iterate(*args, **kwargs)
        if (effective_max is not None
                and len(g.get("nodes", {})) >= effective_max):
            cap_was_hit["flag"] = True
            click.echo(
                f"viter: node count reached {effective_max}; "
                f"output is truncated. Raise --max-nodes (or pass "
                f"max_nodes=... in the argstring) to go further.",
                err=True,
            )
        return g

    build_ns = {"Rule": Rule, "Op": Op, "iterate": _iterate_with_caps,
                **_DEFAULT_EVAL_BINDINGS, **_resolve_imports(imports)}
    graph = _eval_with_source(f"iterate({argstring})", build_ns)

    # JSON-round-trip so graph keys end up as strings (matches what
    # `visiter build | visiter to-dot` would see), without this
    # Fraction/Decimal node keys stay as their native types and
    # break to_dot's string-keyed lookups.
    graph = json.loads(json.dumps(graph, default=str))

    render_ns = {"graph": graph, "to_dot": to_dot,
                 **_DEFAULT_EVAL_BINDINGS, **_resolve_imports(imports)}
    render_call = (f"to_dot(graph, {render_args})"
                   if render_args.strip() else "to_dot(graph)")
    dot = _eval_with_source(render_call, render_ns)

    if fmt == "dot":
        Path(output).write_text(dot.source, encoding="utf-8")
    else:
        Path(output).write_bytes(dot.pipe(format=fmt))


def main():
    cli()


def viter_main():
    """Entry point for the ``viter`` console script — shortcut for
    ``visiter render``. Injects the subcommand name so users can say
    ``viter 'argstring' -o out.svg`` (or ``viter --help``, etc.)
    without typing ``render``. Only ``-V``/``--version`` stays on the
    group so ``viter --version`` reports the tool version.
    """
    if len(sys.argv) == 1 or sys.argv[1] not in ("-V", "--version"):
        sys.argv.insert(1, "render")
    cli(prog_name="viter")


if __name__ == "__main__":
    main()
