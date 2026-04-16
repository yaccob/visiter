# VisIter Manual

> **First time here?** This manual is a reference. If you'd rather
> start with motivation, a small example, and a build-up of concepts,
> read [tutorial.md](tutorial.md) first and come back to the manual
> when you need parameter-level detail.

VisIter is two functions that compose: `iterate` builds a directed graph
by applying guarded rules to seed values and following reachable
successors, and `to_dot` turns such a graph into a Graphviz Digraph
for visualization. The two are connected only by
a documented dict shape, so each can be used standalone.

This manual walks through the data model, semantics, and common
patterns. For the absolute minimum, see [README.md](../README.md).

---

## 1. Data model

### `Op(func, label=None, id=None)`

A pure operation: a callable plus two string fields — a display
**`label`** and a stable **`id`** used for keying.

```python
Op(lambda x: x // 2)                       # label = id = "x // 2"
Op(lambda x: x // 2, "÷2")                 # label = "÷2", id = "x // 2"
Op(square)                                 # label = id = "square"
Op(lambda x: x + 1, "⊕", id="inc")         # label = "⊕", id = "inc"
```

**Label (display).** Free-form display string on edges. When omitted,
derived from `func`: `func.__name__` for named functions, the lambda
body's `ast.unparse` form for lambdas (same-line lambdas are
disambiguated by the bytecode's source position). When the source
isn't retrievable (REPL, `functools.partial`, C extensions) and no
`label=` is given, `Op` raises `ValueError`.

**Id (stable key).** Used by `op_order`, `op_colors` pinning, and
JSON round-trips. **Defaults to the auto-derived string from `func`
— independent of whatever the user chose for `label`.** That way two
ops built from the same `func` share an id even when their display
labels differ, and two ops that accidentally share a label but have
different `func` don't collide.

Pass `id=` explicitly when you want:
- a stable pin target that survives func refactors (whitespace
  changes, parameter renames, extraction into a named function —
  all shift the auto-derived id), or
- a shorter, user-chosen key, or
- to split two lambdas whose bodies happen to unparse to the same
  string but are semantically distinct.

If `_derive_label(func)` fails (REPL, partial), `id` falls back to
`label` (the one signal we have). `iterate` emits a `UserWarning`
when two rules declare the same id with different callables and
different labels.


### `Rule(condition, op, bound=None)`

A guarded operation. The fields:

- `condition: x -> bool` — *applicability*: is this rule's `op` even
  meaningful for this value?
- `op: Op` — what to apply when the rule fires.
- `bound: x -> bool, optional` — *structural cutoff*: even if the op IS
  applicable, do we want to stop here? `bound=None` means "no extra
  cutoff" (effectively `True`).

The two predicates are semantically distinct on purpose. "Is x divisible
by three?" is an applicability question (the op `x // 3` only makes
sense when it is); "would `2*x` exceed our exploration ceiling?" is a
structural cutoff (the op is always meaningful, we just choose to stop).
The renderer treats them differently:

| condition | bound      | result                                      |
| --------- | ---------- | ------------------------------------------- |
| False     | (any)      | rule skipped, nothing recorded              |
| True      | True/None  | normal edge fires                           |
| True      | False      | pseudo-edge recorded (rendered as ghost)    |

A `default: Op | None` argument to `iterate` (see below) covers the
"nothing else fired" case orthogonally.

---

## 2. `iterate` — building the graph

### Signature

```python
iterate(start, rules, *, default,
        max_depth=None,
        max_nodes=1_000_000,
        time_limit=None,
        on_limit="raise",
        tags=None)
```

### Inputs

- `start`: an `int` or any iterable of `int`s. All starts seed the BFS
  at depth 0.
- `rules`: an iterable of `Rule`. Order matters — it determines
  `op_order` (which controls palette assignment in `to_dot`).
- `default`: an `Op` or `None` (**required**, no Python default value
  — the caller must explicitly choose). Fires only when no rule's
  `condition` matches at a given node.
- `max_depth`: optional BFS-depth cap. Nodes at depth `max_depth` are
  kept but not expanded; their would-fire rules become pseudo-edges.
  `None` (default) disables the cap.
- `max_nodes`: total node-count cap. Defaults to 1,000,000. `None`
  disables.
- `time_limit`: `"hh:mm:ss"` wall-clock cap on the build phase.
- `on_limit`: `"raise"` (default) makes `max_nodes` / `time_limit`
  abort with `RuntimeError`; `"stop"` returns the partial graph.
  `max_depth` is always a soft topological stop; it does not raise.
- `tags`: optional `dict[str, callable]`. Each callable is a predicate
  on values; nodes where it returns True get that tag in their `tags`
  list. `"highlight"` is the conventional tag for visual emphasis.

### Output graph dict

```python
{
    "schema_version": "1",             # always set by iterate
    "roots":         [int, ...],       # starts, in input order
    "nodes":         {str(value): {
                          "depth":    int,        # min BFS hops from any start
                          "key_type": str,        # JSON type: "integer",
                                                  # "string", "array", ...
                          "tags":     [str, ...], # if any tag predicate matched
                      }, ...},
    "edges":         [{"from": A, "to": B, "op": label}, ...],
    "pseudo_edges":  [{"from": A,           "op": label}, ...],
    "op_order":      [str, ...]        # distinct op labels in rule order,
                                       # then default's label if not already in
}
```

Notes:
- `nodes` keys are stringified ints (JSON-friendly).
- A node's `depth` is the **minimum** hop count over all paths from any
  start to it (BFS-correct, not first-DFS-visit).
- `op_order` drives palette assignment so colors are stable across
  invocations and don't depend on traversal order.
- `pseudo_edges` records edges that *would have* fired but were
  prevented by `Rule.bound` returning False, or by `max_depth` stopping
  expansion. They have no `to` field.

### Termination behavior

| Source                  | Effect                                                |
| ----------------------- | ----------------------------------------------------- |
| Cycle / known node      | edge added, no recursion (natural)                    |
| `max_nodes` reached     | `on_limit="raise"` → `RuntimeError`; `"stop"` returns |
| `time_limit` reached    | `on_limit="raise"` → `RuntimeError`; `"stop"` returns |
| `max_depth` reached     | node kept, not expanded; pseudo-edges for matching rules |
| `Rule.bound` False      | pseudo-edge recorded for that rule                    |

### Examples

Each block below shows an `iterate(...)` call and the rendered graph
that comes out of it. The rendering details (colors, wedges, dashed
stubs) are defined in §3 — here the pictures just show what the
iteration *produces* so the code doesn't have to be read in the
abstract.

**Descent with divisor rule and increment default, range(1, 30):**

```python
graph = iterate(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
    default=Op(lambda x: x + 2, "+2"),
)
```

![descent, full graph](images/iterate_descent.svg)

**Reverse binary tree from 1, ceiling at 64, depth-capped at 5:**

```python
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
    max_depth=5,
)
```

![reverse binary tree with depth cap](images/iterate_reverse_binary.svg)

**Multi-way decision via conjunctive rules:**

```python
graph = iterate(
    start=range(1, 30),
    rules=[
        Rule(lambda x: x % 15 == 0, Op(lambda x: x // 15, "÷15")),
        Rule(lambda x: x % 3 == 0 and x % 15 != 0, Op(lambda x: x // 3, "÷3")),
        Rule(lambda x: x % 5 == 0 and x % 15 != 0, Op(lambda x: x // 5, "÷5")),
    ],
    default=Op(lambda x: x + 1, "+1"),
    tags={"highlight": lambda x: x > 0 and (x & (x - 1)) == 0},
)
```

![multi-way decision, highlighted powers of two](images/iterate_multiway.svg)

---

## 3. `to_dot` — turning a graph into Graphviz

### Signature

```python
to_dot(graph, *, op_labels=None,
             anchor=None, radius=None, direction="forward",
             value_range=None,
             op_colors=None, palette=None,
             show_binary=False, show_ternary=False, show_factors=False,
             time_limit=None, on_limit="raise")
```

Returns a `graphviz.Digraph`. Caller decides what to do with it
(`.source`, `.render(format="svg")`, etc.).

### Inputs

- `graph`: dict with the shape produced by `iterate`. (Strictly: needs
  `roots`, `nodes`, `edges`, optional `op_order`, optional
  `pseudo_edges`.)
- `op_labels`: optional `{op: display_label}` dict. Ops not present
  fall back to `format_op_label`, which converts simple notations like
  `/2` → `÷2`, `*3+1` → `×3 + 1`. Use this for ops whose label needs
  domain knowledge the renderer can't infer (e.g., `"/3"` → `"−1, ÷3"`).
- `anchor`, `radius`, `direction`: BFS neighborhood crop. Only nodes
  within `radius` hops of `anchor` are rendered. `direction` ∈
  `{"forward", "backward", "both"}`. Default `"forward"` — walks edges
  in their iteration direction and answers "what does the orbit from
  `anchor` look like?". Use `"backward"` to answer "what reaches
  `anchor`?" (natural when the anchor is a sink or fixed point), and
  `"both"` for an undirected neighborhood.
- `value_range`: `(low, high)` int tuple. Combines with anchor/radius
  by intersection.
- `op_colors`: optional `{op: color}` map. Each value may be a single
  hex string (used for both fill and edge) or a `(fill, edge)` tuple
  for explicit pinning.
- `palette`: optional sequence of palette entries (string or tuple, as
  above). Replaces `DEFAULT_OP_PALETTE` for unmapped ops.
- `show_binary` / `show_ternary` / `show_factors`: extra annotations
  under each node label. Binary uses 4-bit nibble grouping; ternary
  uses 3-trit grouping (analogue of nibbles → hex / trits → base 27).
- `time_limit`, `on_limit`: bound the pure-Python build phase
  (BFS cropping + DOT loops + ghost emission). Independent of any
  subprocess-level Graphviz layout timeout.

### Coloring model

Color assignment is in two layers:

1. **Op → color pair.** `resolve_op_colors` walks `op_order` (or
   first-seen edges as fallback). Each distinct op gets a `(fill,
   edge)` pair: from `op_colors` if pinned, otherwise from `palette`
   in order. Exhaustion of the palette yields a neutral grey pair.

   ![op-to-palette: two ops, two (fill, edge) pairs](images/coloring_palette.svg)

2. **Per-node fill** is computed from the node's distinct outgoing op
   labels (real edges plus pseudo-edges and outgoing-cut edges):
   - 0 ops → no fill (Graphviz default white = leaf)
   - 1 op  → solid `fillcolor`
   - 2+ ops → `style="wedged"` with colon-joined fill colors,
     producing pie-wedge segments inside the ellipse

   ![node fill: leaf (white), solid, wedged](images/coloring_node_fill.svg)

3. **Highlight** (the `"highlight"` tag): the fill colors are darkened
   in HSL space (lightness reduced, hue and saturation preserved) so a
   light blue stays a saturated dark blue rather than going grey. Font
   becomes white for contrast.

   ![highlight: same op, one tagged darker than the other](images/coloring_highlight.svg)

4. **Roots** (any node whose value is in `graph["roots"]`) are
   distinguished by `penwidth="3"` — bold border.

   ![root bold border vs. non-root](images/coloring_roots.svg)

### Ghost stubs (cut boundary)

Three different things produce dashed ghost stubs, all rendered the
same way:

- **Outgoing cut**: `kept_src → outside_dst` was filtered out by
  `anchor/radius` or `value_range`. Rendered as `kept_src → <ghost>`.
  The op contributes to the kept node's fill via `extra_out_ops`.
- **Incoming cut**: `outside_src → kept_dst`. Rendered as
  `<ghost> → kept_dst`. Does not affect fill (fill comes from
  outgoing edges only).
- **Pseudo-edge** (from `iterate`): when `Rule.bound` returned False
  or `max_depth` was reached. Rendered the same as outgoing cut
  (kept_src → ghost), shares the fill-contribution path.

The visual vocabulary is uniform: a dashed stub means "the graph
continues here, but we stopped". The semantic source can be reading
the legend or inspecting the input.

A graph with both kinds of stub — the pseudo-edge at 8 (from
`bound=lambda x: 2*x <= 8`) and an incoming boundary stub at 2 from
the cropped-out parent:

![dashed arrows: pseudo-edge and crop boundary](images/dashed_arrows.svg)

### `value_range` and trees

For tree-shaped graphs (e.g., the reverse binary tree from a single
root), `anchor=root, radius=N, direction="forward"` (the default) is
the natural way to show the top N levels.

For forward-iteration graphs with a sink (cycle), `anchor=cycle_node,
radius=N, direction="backward"` shows the N levels of predecessors
above the cycle.

**`direction` × cycles × determinism.** A subtlety worth naming: with
`direction="forward"` and an anchor **inside a cycle**, the forward
BFS terminates in the cycle. For a *deterministic* iteration (each
node has exactly one outgoing edge — the usual case when your rules
are mutually exclusive plus a default), every cycle is closed, so the
radius is effectively ignored once the cycle is entered. In the
descent example below, forward from `1` yields just the two-node
1↔3 cycle regardless of `radius`. `backward` from the same anchor
reaches the full pre-image tree, bounded by `radius`. When rules
fan out (several match a single node), cycles may have branches
leaving them and the radius starts mattering again.

Same descent graph (`range(1, 30)` under `%3 ÷3` else `+2`), same
anchor `1`, same `radius=8`. `direction="forward"` terminates in the
1↔3 cycle — the ghost stub flags that other nodes still feed into 3
from outside the crop:

![anchor=1, radius=8, direction="forward"](images/crop_forward.svg)

Flipping to `direction="backward"` follows edges against the
iteration, so every value that eventually reaches 1 within 8 hops
shows up:

![anchor=1, radius=8, direction="backward"](images/crop_backward.svg)

### Examples

**Reverse binary tree, prime-factor annotations on each node:**

```python
dot = to_dot(graph, show_factors=True)
dot.render("bt", format="svg")
```

![show_factors on the reverse binary tree](images/example_show_factors.svg)

**Descent graph, render only what reaches 1 within 8 hops:**

```python
dot = to_dot(graph, anchor=1, radius=8, direction="backward")
```

![descent crop, backward from 1](images/crop_backward.svg)

**Pin specific ops to specific colors.**

`op_colors` is a `{op_id: color}` map. The **value** can be either:

- A **`(fill, edge)` tuple** — two colors, independently. That matches
  the two-layer palette: a light pastel for fills (readable labels on
  top), a saturated mid-tone for edges (thin lines that still pop
  against a white page).
- A **single hex string** — shorthand for `(hex, hex)`, same color
  for both surfaces. Simpler, but the single tone has to work for
  both: pick a color light enough to keep black label text legible
  on the fill and the thin edge line drawn in the same color is
  usually too faint against white; pick dark enough for a visible
  edge and the text contrast on the fill suffers.

**Recommended: freeze the id explicitly when you want to pin.** Pass
`id=` on the `Op` and pin on that string — it's stable across
func refactors, is identical from Python, the CLI, and against
JSON graphs:

```python
graph = iterate(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0,
                Op(lambda x: x // 3, "÷3", id="div3"))],
    default=Op(lambda x: x + 2, "+2", id="inc2"),
)

dot = to_dot(graph, op_colors={
    "div3": ("#ccddff", "#6688bb"),  # (fill, edge) pair — edges stay visible
    "inc2": "#ffdddd",               # single color — edges fade against white
})
```

![pinned op colors — (fill, edge) vs. single color](images/example_pinned_colors.svg)

The edge labels in the SVG stay `÷3` and `+2` — `op_colors` pins on
id; display is separate, served from `graph["op_labels"]`.

> **Why pinning on the auto-derived id is fragile.** If you don't
> pass `id=`, the id is whatever `_derive_label(func)` produced —
> `ast.unparse(lambda_body)` for lambdas, `func.__name__` for named
> functions. That's an *implementation detail of the source*:
> rewriting `lambda x: x // 3` as `lambda x: x//3` changes the
> unparsed form; renaming the parameter (`lambda y: y // 3` → id
> `"y // 3"`) does too; extracting the lambda into a named function
> shifts it again. Each of those makes your pin silently stop
> matching — the pin is ignored, no error, the op just falls back to
> the next palette slot. Explicit `id=` avoids the whole class.

### Visual vocabulary at a glance

Quick reference for what each rendered element means. Skim this once,
keep it in mind when reading SVGs:

| element                            | meaning                                                                                          |
| ---------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Bold border** (`penwidth=3`)     | node is in `graph["roots"]` — a seed value passed to `iterate`                                  |
| **No fill (white)**                | leaf: zero outgoing edges — iteration terminates here                                            |
| **Solid fill**                     | exactly one outgoing op label; fill = that op's color                                            |
| **Wedged-pie fill**                | ≥2 distinct outgoing op labels; one slice per op                                                 |
| **Darkened fill + white font**     | node carries the `"highlight"` tag (set by a predicate in `iterate(..., tags={...})`)            |
| **Dashed edge to a tiny target**   | "ghost stub" — the iteration would continue here but was stopped by `Rule.bound`, `max_depth`, or render-time crop |

One graph exhibiting every style in the table above:

![visual vocabulary — one graph, every style](images/node_styles.svg)

---

## 4. CLI

A single `visiter` command dispatches to subcommands. Each subcommand
(`iterate`, `to-dot`) takes a single positional argument: a Python
expression that is spliced into a call to the corresponding function
and `eval`'d. `Op`, `Rule`, `iterate`, `to_dot`, and `graph` (for the
renderer) live in the eval namespace.

The CLI exposes the entire Python API without per-flag glue: anything
you can write as kwargs to `iterate(...)` or `to_dot(...)` works as
the argument string.

`visiter --help` lists available subcommands.

### iterate

```
visiter iterate 'ARGSTRING'      → JSON graph on stdout
```

Examples:

```bash
visiter iterate 'range(1, 30),
    [Rule(lambda x: x%3==0, Op(lambda x: x//3, "÷3"))],
    default=Op(lambda x: x+2, "+2")'
```

```bash
visiter iterate 'start=[1], rules=[
    Rule(lambda x: True, Op(lambda x: 2*x, "×2"), bound=lambda x: 2*x <= 64),
    Rule(lambda x: True, Op(lambda x: 2*x+1, "×2+1"), bound=lambda x: 2*x+1 <= 64),
], default=None, max_depth=8'
```

### to_dot

```
visiter to-dot 'ARGSTRING' [--input FILE] [-o FILE]
```

Reads graph JSON from stdin (or `--input FILE`); writes DOT to stdout
(or `-o FILE`).

```bash
visiter to-dot 'anchor=1, radius=8, direction="backward", show_factors=True' < graph.json > out.dot
```

### Pipe composition

```bash
visiter iterate '...' | visiter to-dot '...' | dot -Tsvg > out.svg
```

### Errors and `eval`

Any error in the argstring surfaces as a normal Python exception
(SyntaxError, NameError, TypeError) with its native traceback. There is
no parser frontend to misdiagnose input. `eval` is appropriate here
because this is a local research tool: running `visiter iterate '…'` is
no different in trust model from running any local Python script.

---

## 5. Recipes

### "I want depth-gradient coloring"

VisIter exposes `depth` per node but doesn't ship a depth-gradient
renderer. Easy to build on top by constructing the graphviz.Digraph
yourself and picking each node's fill via `darken` on a base color:

```python
from visiter import iterate, Op, Rule, darken
import graphviz

graph = iterate(
    start=[1],
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
    default=Op(lambda x: x + 2, "+2"),
    max_depth=6,
)
max_d = max(info["depth"] for info in graph["nodes"].values()) or 1
base = "#ffccaa"
roots = {str(v) for v in graph["roots"]}

dot = graphviz.Digraph()
dot.attr(rankdir="TB")
dot.attr("node", fontsize="11", shape="ellipse", style="filled")
for k, info in graph["nodes"].items():
    factor = 1.0 - (info["depth"] / max_d) * 0.55
    dot.node(f"n{k}", label=k,
             fillcolor=darken(base, factor),
             penwidth="3" if k in roots else "1")
for e in graph["edges"]:
    dot.edge(f"n{e['from']}", f"n{e['to']}", label=f" {e['op']} ")
```

![depth-gradient: darker shades further from the roots](images/depth_gradient.svg)

### "I want to limit by absolute value"

Use `value_range=(low, high)` in `to_dot`. To stop iterate from
producing huge values in the first place, use `Rule.bound`.

### "Several disconnected starts, render each cluster separately"

Run `iterate` once per start, render separately. There's no built-in
multi-rooted layout; Graphviz handles disconnected components in one
canvas if rendered together.

### "I need a custom predicate for highlighting"

Pass it as a `tags` entry. The `"highlight"` tag name is the renderer's
visual emphasis trigger:

```python
graph = iterate(..., tags={"highlight": lambda x: is_prime(x)})
```

Other tag names are stored on nodes too and accessible via
`graph["nodes"][vstr]["tags"]`, but only `"highlight"` triggers the
renderer's fill-darkening logic.

---

## 6. Reference: complete graph dict shape

```python
{
    "schema_version": "1",           # bundled schema major version

    "roots": [int, ...],

    "nodes": {
        str(value): {
            "depth":    int,            # required: BFS distance from nearest start
            "key_type": str,            # required: JSON type of the value
                                        #   (one of "null", "boolean", "integer",
                                        #   "number", "string", "array", "object")
                                        #   — drives type-sensitive rendering
            "tags":     [str, ...],     # optional: present iff at least one tag matched
        },
        ...
    },

    "edges": [
        {"from": int, "to": int, "op": str},   # op = identity (see op_labels)
        ...
    ],

    "pseudo_edges": [
        {"from": int, "op": str},              # op = identity
        ...
    ],

    "op_order": [str, ...],          # distinct op identities in rule order, then default

    "op_labels": {                   # map from identity → display label
        identity_str: display_str,
        ...
    },
}
```

`to_dot` requires `roots`, `nodes`, `edges`. The other fields are
all optional in the renderer's eyes — consumed if present, ignored
otherwise.

### Value types

Values in an iteration graph can be any hashable Python object:
integers, strings, tuples of hashables, frozensets, etc. `iterate`
keys nodes by `str(value)`, so two values with the same string form
collide. On JSON output, native JSON types pass through unchanged;
non-native values are coerced to their `str()` form by the CLI's
`json.dump(default=str)`. The schema reflects this by accepting any
JSON type for edge `from`/`to` and any non-empty string for node
keys.

To let consumers recover the type of a node value despite JSON's
string-keys constraint, `iterate` records it explicitly as a
required `key_type` attribute on each node — using the seven
JSON Schema primitives (`null`, `boolean`, `integer`, `number`,
`string`, `array`, `object`) so any JSON consumer can interpret it
without Python-specific knowledge. The Python → JSON mapping is:
`bool` → `boolean`, `int` → `integer`, `float` → `number`, `str` →
`string`, `list`/`tuple`/`set`/`frozenset` → `array`, `dict` →
`object`, `None` → `null`; anything else falls back to `string` via
the default `str()` coercion. The renderer consults `key_type`
directly when deciding whether type-sensitive features
(`show_binary`, `show_ternary`, `show_factors`, `value_range`)
should fire — no string-pattern heuristic is involved. Hand-built
graph dicts and producers other than `iterate` must supply
`key_type` themselves; the schema enforces this via `required`.

### JSON Schema

The authoritative machine-readable contract lives at
[`schemas/v1/graph.schema.json`](../schemas/v1/graph.schema.json)
(JSON Schema Draft 2020-12). It is bundled with the package and served
under the `$id` URL
`https://github.com/yaccob/visiter/schemas/v1/graph.schema.json`.

Versioning policy: v1 accepts non-breaking additions (new optional
fields, new enum values) in place. Breaking changes ship under `/v2/`
with a new `$id`; v1 stays frozen. The `schema_version` field on the
graph instance identifies the major version.

Validate a graph document against the bundled schema via the CLI:

```bash
pip install visiter[validate]
visiter iterate '...' | visiter validate
```

---

## 8. Integrating with NetworkX

VisIter builds iteration graphs and renders them. For everything in
between — cycle detection, shortest paths, centrality measures,
strongly-connected components, topological sort, bipartite matching,
community detection, and many more — [NetworkX](https://networkx.org/)
is the mature Python answer. Rather than wrap any of NetworkX's
algorithms ourselves, VisIter ships a thin *bridge* that translates
between its own graph dict and a `networkx.DiGraph`.

### Install

```bash
pip install visiter[analytics]
```

That pulls `networkx>=3.0` alongside VisIter's core deps.

### Python API

`visiter.analytics` exports two functions:

```python
from visiter import iterate, Op, Rule, to_dot
from visiter.analytics import to_networkx, from_networkx
import networkx as nx

graph = iterate(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
    default=Op(lambda x: x + 2, "+2"),
)

g = to_networkx(graph)
# Now the entire NetworkX toolbox is available:
cycles       = list(nx.simple_cycles(g))
path_to_one  = nx.shortest_path(g, source="5", target="1")
centrality   = nx.in_degree_centrality(g)
condensation = nx.condensation(g)   # a new nx.DiGraph, one node per SCC

# If the NetworkX call returns a graph, you can render that too:
dot = to_dot(from_networkx(condensation))
```

`to_networkx` preserves node keys (as strings — this is the only
identity the graph dict actually guarantees) and every node
attribute, including `depth`, `tags`, and `key_type`. Edge
attributes (`op`) pass through as well. Top-level fields (`roots`,
`pseudo_edges`, `op_order`, `schema_version`) are stashed on
`nx.DiGraph.graph` so `from_networkx` can reproduce the original
dict exactly. Round-trip is information-preserving for VisIter graphs.

For bare NetworkX graphs without VisIter metadata you still get a
minimal, schema-valid result: missing `depth` defaults to 0, and
`key_type` is inferred from the JSON type of the NX node id — that's
the only honest signal available when the producer didn't set it
explicitly.

**Attribute pass-through** is what lets NX algorithms that annotate
nodes stay useful on our side. `nx.condensation`, for instance,
tags each SCC-node with a `members` attribute (a frozenset of the
original nodes in that component). `from_networkx` carries the
attribute through to the graph dict; non-JSON values like frozensets
are coerced to sorted lists so the result stays serialisable.

Once the attribute is in the graph dict, you can tell the renderer
to use it as the displayed label instead of the node key via
`to_dot`'s `node_label_attr` kwarg (or the matching argstring on the
CLI). List/tuple/set values get formatted as `{a, b, c}`
automatically (no `repr` quotes); scalars render as plain `str()`:

```python
dot = to_dot(graph, node_label_attr="members")
```

```bash
visiter analyze 'nx.condensation(graph)' \
  | visiter to-dot 'node_label_attr="members"' \
  | dot -Tsvg > scc.svg
```

See [`demos/analytics_condensation_rendered.sh`](../demos/analytics_condensation_rendered.sh)
for the full end-to-end pipeline.

### CLI

The `analyze` subcommand mirrors the Python API over shell pipes:

```bash
visiter iterate '...' | visiter analyze '<python expression>'
```

`graph` (a `networkx.DiGraph`) and `nx` are pre-bound in the eval
namespace. The expression's result is written to stdout as JSON; if
it is itself a NetworkX graph, it is emitted as a VisIter graph dict,
so the output flows straight into `visiter to-dot`:

```bash
# Count things.
visiter iterate '...' | visiter analyze 'nx.number_of_nodes(graph)'

# List cycles.
visiter iterate '...' | visiter analyze 'list(nx.simple_cycles(graph))'

# Pipe a derived graph back into rendering.
visiter iterate '...' \
  | visiter analyze 'nx.condensation(graph)' \
  | visiter to-dot '' \
  | dot -Tsvg > scc.svg
```

See [`demos/analytics_cycles_and_centrality.sh`](../demos/analytics_cycles_and_centrality.sh),
[`demos/analytics_condensation_rendered.sh`](../demos/analytics_condensation_rendered.sh),
and [`demos/analytics_shortest_paths_highlighted.sh`](../demos/analytics_shortest_paths_highlighted.sh)
for runnable end-to-end examples.

### Scope

The bridge is deliberately thin: two Python functions plus one CLI
subcommand. We don't wrap individual NetworkX algorithms — their
names are already their documentation, and wrapping would only
duplicate surface area we can't maintain. Everything NetworkX can do
is one `nx.<something>(graph)` call away.
