# VisIter

Build and visualize orbit graphs for discrete iterations under guarded rules.

VisIter is a small library that does two complementary things:

1. **`iterate(start, rules, default=..., max_depth=..., ...)`** —
   applies a list of guard-and-operation Rules to seed values via BFS,
   producing a graph (nodes, edges, per-node depth, optional pseudo-edges
   marking structural boundaries).

2. **`to_dot(graph, ...)`** — turns the graph into a Graphviz
   Digraph for SVG/HTML/PDF rendering, with anchor/radius cropping,
   per-rule edge coloring, wedged-pie node fills for branching nodes,
   and dashed ghost stubs at every kind of cut boundary.

The two are independent: any graph dict that fits the documented shape
can be rendered, and `iterate` can be used purely for graph construction
without ever touching the renderer.

## Install

```bash
pip install visiter
```

Graphviz must be available on `PATH` for image rendering (the Python
`graphviz` package wraps the system tool).

## Quickstart — descent with divisor rule

A rule that divides by three when applicable, with a `+2` fallback for
all other values. Every integer path eventually joins one of two small
cycles (`1 → 3 → 1`, `2 → 4 → 6 → 2`).

```python
from visiter import iterate, Op, Rule, to_dot

graph = iterate(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
    default=Op(lambda x: x + 2, "+2"),
)
dot = to_dot(graph, anchor=1, radius=8, direction="backward")
dot.render("descent", format="svg")
```

## Quickstart — reverse binary tree with bound

Generate every positive integer up to a ceiling as the binary tree of
`×2` / `×2+1` successors of 1. `Rule.bound` keeps the expansion inside
the ceiling; to_dot draws the frontier as dashed ghost stubs.

```python
from visiter import iterate, Op, Rule, to_dot

ceiling = 64

graph = iterate(
    start=[1],
    rules=[
        Rule(lambda x: True,
             Op(lambda x: 2 * x, "×2"),
             bound=lambda x: 2 * x <= ceiling),
        Rule(lambda x: True,
             Op(lambda x: 2 * x + 1, "×2+1"),
             bound=lambda x: 2 * x + 1 <= ceiling),
    ],
    default=None,
)
dot = to_dot(graph, show_binary=True)
dot.render("binary_tree", format="svg")
```

## CLI

A single `visiter` command with subcommands. Each subcommand takes its
function's keyword arguments as a single Python expression that is
`eval`'d in a namespace where `Op`, `Rule`, `iterate`, and `to_dot` are
pre-bound. Output is JSON (`iterate`) and DOT (`to-dot`) on stdout, so
they pipe directly:

```bash
visiter iterate 'range(1, 30),
                 [Rule(lambda x: x%3==0, Op(lambda x: x//3, "÷3"))],
                 default=Op(lambda x: x+2, "+2")' \
  | visiter to-dot 'anchor=1, radius=8, direction="backward"' \
  | dot -Tsvg > descent.svg
```

The `validate` subcommand checks a graph JSON document against the
bundled JSON Schema (`schemas/v1/graph.schema.json`, Draft 2020-12):

```bash
pip install visiter[validate]
visiter iterate '...' | visiter validate
```

The `analyze` subcommand bridges to [NetworkX](https://networkx.org/)
so you can run any of its hundreds of graph algorithms on the output
(cycles, shortest paths, centrality, strongly-connected components,
...) — and when the algorithm returns a NetworkX graph itself, it
flows straight back into `visiter to-dot`:

```bash
pip install visiter[analytics]
visiter iterate '...' \
  | visiter analyze 'nx.condensation(graph)' \
  | visiter to-dot '' | dot -Tsvg > scc.svg
```

## Why VisIter?

The short pitch: VisIter is **free, scriptable, Graphviz-native,
Unix-pipe-composable orbit-graph rendering for discrete iterations
under guarded rules** — with cutoff boundaries (bounds, depth limits,
render crops) as a first-class visual primitive, not silent truncation.

If you have a Mathematica license, `NestGraph` covers the core BFS.
For term rewriting with equational theories, use Maude. For
Petri-net reachability, LoLA. For generic graph analytics, NetworkX.
For the specific combination of "Python + rule-driven reachability
from a seed + opinionated rendering + shell pipes", the niche is
small but real.

Full honest comparison against NetworkX, NestGraph, Maude, LoLA, and
continuous-dynamics tooling: **[docs/comparison.md](docs/comparison.md)**.

## Documentation

- [docs/tutorial.md](docs/tutorial.md) — gentle introduction: what
  problem the tool solves, smallest example, what each piece does,
  what the dashed arrows mean. Start here.
- [docs/manual.md](docs/manual.md) — reference: every parameter,
  every data field, the rendering model in full, design decisions.
- [docs/comparison.md](docs/comparison.md) — how VisIter relates to
  other tools in the ecosystem, and when to pick something else.
- [demos/](demos/) — runnable end-to-end examples: `make demo` writes
  SVG/PDF/DOT into `demos/out/`.

## License

MIT
