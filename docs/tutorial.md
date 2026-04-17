# VisIter — a gentle introduction

This tutorial walks you from "what is this for?" to "I can build my
own visualizations" in a handful of small steps. Each section is one
question. Skim the questions first; jump in where it feels useful.

When you want details, the [manual](manual.md) is the reference. When
you want to **see** something running, the [demos](../demos/) ship as
runnable shell scripts (`make demo` runs them all).

---

## What problem does VisIter solve?

You have an iteration: a value, a rule that produces the next value
(or several), and you want to **see** what happens. Where does it
converge? Does it cycle? Does it branch out and come back? Does it
escape to infinity?

Plotting numbers in a chart doesn't help — iteration structure isn't
about magnitudes, it's about **which value goes to which**. What you
actually want is a graph: nodes are reachable values, edges are
applied operations. Then you can read off cycles, branches, and
attractors at a glance.

VisIter does exactly that, in two stages:

1. **`iterate`** runs your rules from one or more starting values and
   returns a graph data structure (just a dict).
2. **`to_dot`** turns that graph into a Graphviz drawing.

The two stages are independent. You can use one without the other —
build a graph and analyze it programmatically, or render someone
else's graph dict.

---

## What does the simplest case look like?

Start from 1. Whenever the value is divisible by 3, divide it by 3.
Otherwise, add 2.

```python
from visiter import iterate, Op, Rule, to_dot

graph = iterate(
    start=[1],
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
    default=Op(lambda x: x + 2),
)
to_dot(graph).render("first", format="svg")
```

Read it back: from 1 the rule doesn't apply (1 isn't divisible by 3),
so the default fires and we get 3. From 3 the rule fires, dividing
back to 1. There's the cycle — and the rendered graph shows two nodes
and two arrows that prove it.

![simplest cycle](images/simplest.svg)

---

## How are edge labels chosen?

Notice the edges above read `x // 3` and `x + 2` — no labels were
passed. `Op(func)` derives a label from its callable: the function's
`__name__` for named functions, or the lambda body rendered via
`ast.unparse` for lambdas. That covers most cases with no typing.

When you want something shorter, nicer, or non-ASCII, pass the label
explicitly as the second argument:

```python
Op(lambda x: x // 3, "÷3")
Op(lambda x: x + 2, "+2")
```

![same graph, custom labels](images/custom_labels.svg)

Explicit labels are also the escape hatch when auto-derivation can't
identify the callable — `functools.partial`, REPL lambdas built from
an unreachable source, or several lambdas on one line that differ
only by whitespace.

`Op` also carries a separate **`id`** field — the stable key used by
color pinning (`op_colors`) and by `op_order`. By default it's the
**auto-derived form of `func`** (the same string `_derive_label`
produces), *not* the user-chosen display label. That means two ops
built from the same function share an id even when their display
labels differ, and pins you set via `op_colors` don't break when you
later rename a label. Set `id=` explicitly when you want a stable,
short key for pinning — the `Op` section of the manual has the
details.

---

## What happens when no rule applies?

You answer that explicitly when you call `iterate`, with the `default`
keyword:

- `default=Op(...)` — apply this operation when nothing else fires.
  Useful when "everything not covered by my rules takes this other
  path" describes your iteration honestly.
- `default=None` — declare the value a leaf. The graph just stops
  there.

`default` has no Python default value on purpose. You're forced to
make the choice, because "no rule matched" is not the same question as
"my rules said to stop here" — VisIter wants you to spell that out.

With `default=Op(x+1)`, the value whose rule didn't match still gets
a successor:

![default Op fires](images/default_op.svg)

With `default=None`, the same value is a leaf — drawn white, because
it has no outgoing edge:

![default None: leaf](images/default_none.svg)

---

## How do I stop the iteration from running forever?

Three orthogonal mechanisms, used in combination as needed:

- **`Rule.bound`** — *"this op IS applicable, but stop here anyway"*.
  The next quickstart uses it: doubling is always meaningful, but
  bound caps the value at a ceiling.
- **`max_depth`** — soft cap on BFS depth. Nodes at the limit are
  kept, just not expanded.
- **`max_nodes`** / **`time_limit`** — hard resource limits. Default
  behaviour is to raise; pass `on_limit="stop"` to get the partial
  graph instead.

`Rule.bound` and `max_depth` produce **pseudo-edges** — entries that
record "an op would have fired here". The renderer turns them into
dashed ghost stubs at the boundary, so you can tell the difference
between "the iteration genuinely terminates here" (no ghost) and "the
iteration continues, we just stopped looking" (ghost).

Doubling from 1 with `bound=lambda x: 2*x <= 8` stops the BFS at 8 —
the dashed stub on 8 says "×2 would fire here, we chose not to":

![bound → pseudo-edge → ghost stub](images/bound_ghost.svg)

---

## What if the same value is reached two different ways?

VisIter de-duplicates nodes by `str(value)`. The second visit just
adds the edge — the node already exists. This is BFS, so each node's
recorded `depth` is the *minimum* hop count from the nearest start —
you always see the shortest path's depth, never an arbitrary
traversal-order depth.

That's exactly what makes graphs from VisIter useful: cycles, joins,
and shared subpaths show up as actual graph topology, not as
mysteriously duplicated subtrees.

Starting from `[1, 9]` with the same divide-by-3-else-+2 rule, 3 is
reached once from 1 (via +2) and once from 9 (via ÷3) — a single
node with two incoming edges, not a duplicate:

![fan-in: two paths into 3](images/fan_in.svg)

---

## How do I show only a slice of a big graph?

Render-time cropping. `to_dot` takes `anchor` (a node value) plus
`radius` (BFS hop count) and an optional `direction`:

```python
to_dot(graph, anchor=1, radius=2, direction="backward")
```

This says: keep nodes within 2 hops of node 1, walking edges
**backward** (so you see what reaches 1, not what 1 reaches). The
edges that leave the kept region are drawn as dashed ghost stubs —
same vocabulary as the bound/max_depth boundary.

`direction="forward"` (the default) is the natural choice for
tree-shaped graphs expanded from a root; `"backward"` is natural for
graphs with a sink/cycle you want to inspect. `"both"` walks edges
undirected — meaningful only for graphs that fan out (multiple
outgoing ops per node); on a deterministic 1-out graph it collapses
to backward.

The descent graph (`range(1, 30)` under %3-else-+2) from anchor 1,
radius 8, is a small orbit forward but a whole pre-image tree
backward:

**`direction="forward"`** — only the 1↔3 cycle itself (with a dashed
stub for "other nodes still feed in from outside"):

![crop, direction=forward](images/crop_forward.svg)

**`direction="backward"`** — every predecessor within 8 hops:

![crop, direction=backward](images/crop_backward.svg)

See [`demos/anchor_radius_crop_and_recolor.sh`](../demos/anchor_radius_crop_and_recolor.sh)
for a script that renders one graph as three different views.

---

## What do the node styles mean?

The renderer uses a small visual vocabulary so the picture itself
carries semantic information:

- **Bold border** (`penwidth="3"`) — this node is a *root*: one of the
  seed values you passed to `iterate`.
- **No fill (white)** — leaf: zero outgoing edges. The iteration
  terminates here naturally.
- **Solid fill** — node has exactly one outgoing op label; the fill
  is that op's color.
- **Wedged-pie fill** — node has two or more distinct outgoing op
  labels; the slices are colored after each op (one slice per op).
- **Darkened fill + white font** — the node carries the `"highlight"`
  tag (set by a predicate you passed to `iterate`'s `tags` argument).

So at a glance: bold border = where you started; white = where you
stopped naturally; multi-color pie = where the iteration branches;
dark = whatever your highlight predicate matched.

One graph exhibiting every style:

![visual vocabulary — one graph, every style](images/node_styles.svg)

## What do the dashed arrows mean?

Three different things, all rendered identically:

1. The iteration **could continue** but `Rule.bound` said no.
2. The iteration **could continue** but `max_depth` was reached.
3. The renderer **cropped** the view (anchor/radius or value_range)
   and an edge crossed the boundary.

The visual vocabulary is uniform on purpose: a dashed stub means *"the
graph continues here, but we stopped looking"*. The semantic source
is whatever you set up — the legend, the docstring, your own notes.

A graph combining both kinds — a pseudo-edge from a `bound` at 8 on
the 1-branch, and a cropped-out incoming stub at 2:

![dashed arrows: pseudo-edge and crop boundary](images/dashed_arrows.svg)

---

## Does this only work for numbers?

No. Values can be any hashable, `str()`-able Python object: integers,
strings, tuples, frozensets. The rule and op functions just need to
agree on the type. See
[`demos/non_integer_values.sh`](../demos/non_integer_values.sh) for
a string-valued example (drop trailing vowels until none remain).

A few `to_dot` features are intrinsically integer-specific —
`show_binary`, `show_ternary`, `show_factors`, and `value_range`. If
you turn them on for a non-integer graph, they emit a warning and are
silently skipped; everything else still renders normally.

Iterating on words, dropping each trailing vowel until the last
character is a consonant — string nodes, integer-free graph:

![string-valued iteration](images/strings.svg)

---

## What does the command line look like?

The `visiter` CLI mirrors the Python API: each subcommand takes one
positional argument that is a Python expression, spliced into the
function call.

```bash
visiter build 'range(1, 30),
                 [Rule(lambda x: x%3==0, Op(lambda x: x//3, "÷3"))],
                 default=Op(lambda x: x+2, "+2")' \
  | visiter to-dot 'anchor=1, radius=8, direction="backward"' \
  | dot -Tsvg > descent.svg
```

Three programs, one pipeline:

- `visiter build` writes a JSON graph to stdout.
- `visiter to-dot` reads JSON from stdin, writes DOT to stdout.
- `dot` is system Graphviz; takes DOT, produces SVG/PDF/PNG/etc.

Because the stages are decoupled, you can save the JSON once and
render it many times with different views — or run a schema validator
between stages as a sanity check.

See [`demos/pipeline_to_svg_and_pdf.sh`](../demos/pipeline_to_svg_and_pdf.sh)
for the full pipe to PDF, and
[`demos/schema_validation_in_pipeline.sh`](../demos/schema_validation_in_pipeline.sh)
for inserting validation into the pipeline.

---

## Can I run graph algorithms on the result?

Yes — via the `[analytics]` extra, which bridges VisIter's graph dict
to [NetworkX](https://networkx.org/). NetworkX ships hundreds of graph
algorithms (cycles, shortest paths, centrality, condensation,
strongly-connected components, ...); VisIter doesn't wrap them, it
just hands the graph over.

```bash
pip install visiter[analytics]
visiter build '...' | visiter analyze 'list(nx.simple_cycles(graph))'
```

`graph` is the NetworkX `DiGraph`, `nx` is the library; the expression
is evaluated and its result emitted as JSON. If the expression returns
a NetworkX graph (e.g. `nx.condensation(graph)`), it flows straight
back into `visiter to-dot` for rendering. See the
[manual's NetworkX section](manual.md#7-integrating-with-networkx) and
the [`analytics_*` demos](../demos/) for more.

## What does the JSON Schema buy me?

The graph-dict shape is formally specified as a JSON Schema (Draft
2020-12) at
[`schemas/v1/graph.schema.json`](../schemas/v1/graph.schema.json).

That gives you three things:

- A machine-readable contract for tools that consume `iterate` output.
- A pipeline checkpoint: `visiter validate` reads JSON on stdin and
  exits non-zero if the shape drifted.
- A versioning anchor: future breaking changes ship under `/v2/`,
  v1 stays frozen, instances self-identify via `schema_version`.

Install the optional extra to use the validator:

```bash
pip install visiter[validate]
```

---

## Where do I go from here?

- The [manual](manual.md) is the reference — every parameter, every
  data field, the rendering model in full, design decisions.
- The [demos](../demos/) are runnable end-to-end examples covering
  the patterns introduced above.
- Run `make demo` to generate every demo's output into `demos/out/`
  and look at the SVGs.
