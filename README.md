# VisIter

See what a discrete iteration actually does — as a graph.

## The simplest case

Integers 1–9. Rule: divisible by 3 → divide by 3. Everything
else → add 2. Where does each value end up?

```python
#!/usr/bin/env viter
viter(
    range(1, 10),
    [Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
    Op(lambda x: x + 2),
)
```

![descent graph, range 1–9](docs/images/readme_quickstart.svg)

Save as `descent.vit`, run with `viter descent.vit > out.svg`.
One call, auto-derived edge labels, SVG on stdout.

## Install

```bash
pip install visiter
```

Graphviz must be available on `PATH` (`brew install graphviz` /
`apt install graphviz`).

## Going further

The fluent API gives you full control over each stage:

```python
#!/usr/bin/env viter
build(
    range(1, 10),
    [Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
    Op(lambda x: x + 2),
).to_dot(anchor=1, radius=8, direction="backward").render()
```

Save intermediate results with `.tap()`:

```python
build(...).tap(write(file="graph.json")).to_dot().render(file="out.svg")
```

Use NetworkX for graph analysis via `.filter()`:

```python
import networkx as nx
build(...).filter(NxFilter(nx.condensation)).to_dot().render()
```

Use the Python API directly (outside `.vit` files):

```python
from visiter import build, Op, Rule

graph = build(
    range(1, 10),
    [Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
    Op(lambda x: x + 2),
)
graph.to_dot().render(file="descent.svg")
```

## Why VisIter?

**Free, scriptable, Graphviz-native orbit-graph rendering for discrete
iterations under guarded rules** — with cutoff boundaries (bounds,
depth limits, render crops) as a first-class visual primitive, not
silent truncation.

Full honest comparison against NetworkX, NestGraph (Mathematica),
Maude, LoLA, and continuous-dynamics tooling:
**[docs/comparison.md](docs/comparison.md)**.

## Documentation

- [docs/tutorial.md](docs/tutorial.md) — gentle introduction: what
  problem the tool solves, smallest example, what each piece does,
  what the dashed arrows mean. Start here.
- [docs/manual.md](docs/manual.md) — reference: every parameter,
  every data field, the rendering model in full, design decisions.
- [docs/comparison.md](docs/comparison.md) — how VisIter relates to
  other tools in the ecosystem, and when to pick something else.
- [demos/](demos/) — runnable `.vit` examples organized by topic
  (`basics/`, `rendering/`, `integration/`, `applications/`).

## License

MIT
