# VisIter

See what a discrete iteration actually does — as a graph.

## The simplest case

Integers 1–9. Case: divisible by 3 → divide by 3. Default (everything
else) → add 2. Where does each value end up?

```python
#!/usr/bin/env viter
(viter(range(1, 10))
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .render())
```

![descent graph, range 1–9](docs/images/readme_quickstart.svg)

Save as `descent.vit`, run with `viter descent.vit > out.svg`. The
`#!/usr/bin/env viter` shebang also lets you `chmod +x descent.vit`
and execute the file directly.

`.render()` is the shortcut terminal — it builds the graph, converts
to Graphviz, and writes SVG to stdout in one call.

## Install

```bash
pip install visiter
```

Graphviz must be available on `PATH` (`brew install graphviz` /
`apt install graphviz`).

## Going further

`.render()` is convenient for the common case. For anything more —
cropping, custom colors, side-effects, filters — materialize the
Graph explicitly via `.build()` and keep chaining:

```python
#!/usr/bin/env viter
(viter(range(1, 10))
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .build()
 .to_dot(anchor=1, radius=8, direction="backward")
 .render())
```

Save intermediate results with `.tap()`:

```python
(viter(...).case(...).default(...).build()
 .tap(write(file="graph.json"))
 .to_dot()
 .render(file="out.svg"))
```

Use NetworkX for graph analysis via `.filter()`:

```python
import networkx as nx
(viter(...).case(...).default(...).build()
 .filter(NxFilter(nx.condensation))
 .to_dot()
 .render())
```

If-elif-else semantics (first matching case wins) via `match=Match.FIRST`:

```python
(viter(range(1, 17), match=Match.FIRST)
 .case(lambda x: x % 2 == 0, lambda x: x // 2)
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x * 5 + 7)
 .render())
```

Use the Python API directly (outside `.vit` files):

```python
from visiter import viter

graph = (viter(range(1, 10))
         .case(lambda x: x % 3 == 0, lambda x: x // 3)
         .default(lambda x: x + 2)
         .build())
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
