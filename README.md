# VisIter

Build and visualize iteration graphs from rule-based state transitions.

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

## Documentation

- [docs/manual.md](docs/manual.md) — full API reference and concepts:
  rule semantics, depth/bound/pseudo-edges, ghost stubs, color model.

## License

MIT
