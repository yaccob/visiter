# VisIter Manual

> **First time here?** This manual is a reference. If you'd rather
> start with motivation, a small example, and a build-up of concepts,
> read [tutorial.md](tutorial.md) first and come back to the manual
> when you need parameter-level detail.

VisIter is two functions that compose: `iterate` builds a directed graph
from rule-based state transitions, and `to_dot` turns such a graph
into a Graphviz Digraph for visualization. The two are connected only by
a documented dict shape, so each can be used standalone.

This manual walks through the data model, semantics, and common
patterns. For the absolute minimum, see [README.md](../README.md).

---

## 1. Data model

### `Op(func, label)`

A pure operation: a callable mapping the current value to the next, plus
a string label used for edge display and color keying.

```python
Op(lambda x: x // 2, "/2")
```

The label is the **identity** of an op throughout the system —
`op_order`, palette assignment, `op_colors` lookup all key on it. Two
different `Op` instances with the same label are treated as the same
operation for color and ordering purposes.

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
    "roots":         [int, ...],       # starts, in input order
    "nodes":         {str(value): {
                          "depth": int,        # min BFS hops from any start
                          "tags":  [str, ...]  # if any tag predicate matched
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

**Descent with divisor rule and increment default, range(1, 30):**

```python
graph = iterate(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
    default=Op(lambda x: x + 2, "+2"),
)
```

**Reverse binary tree from 1, ceiling at 64, depth-capped at 8:**

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
    max_depth=8,
)
```

**Multi-way decision via conjunctive rules:**

```python
graph = iterate(
    start=range(1, 50),
    rules=[
        Rule(lambda x: x % 15 == 0, Op(lambda x: x // 15, "÷15")),
        Rule(lambda x: x % 3 == 0 and x % 15 != 0, Op(lambda x: x // 3, "÷3")),
        Rule(lambda x: x % 5 == 0 and x % 15 != 0, Op(lambda x: x // 5, "÷5")),
    ],
    default=Op(lambda x: x + 1, "+1"),
    tags={"highlight": lambda x: x > 0 and (x & (x - 1)) == 0},
)
```

---

## 3. `to_dot` — turning a graph into Graphviz

### Signature

```python
to_dot(graph, *, op_labels=None,
             anchor=None, radius=None, direction="backward",
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
  `{"forward", "backward", "both"}`. Default `"backward"` matches the
  common "show what reaches the anchor" intent (forward-iteration with
  an anchor on the cycle). For trees rooted at the start, use
  `direction="forward"` (or `"both"`).
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
2. **Per-node fill** is computed from the node's distinct outgoing op
   labels (real edges plus pseudo-edges and outgoing-cut edges):
   - 0 ops → no fill (Graphviz default white = leaf)
   - 1 op  → solid `fillcolor`
   - 2+ ops → `style="wedged"` with colon-joined fill colors,
     producing pie-wedge segments inside the ellipse

3. **Highlight** (the `"highlight"` tag): the fill colors are darkened
   in HSL space (lightness reduced, hue and saturation preserved) so a
   light blue stays a saturated dark blue rather than going grey. Font
   becomes white for contrast.

4. **Roots** (any node whose value is in `graph["roots"]`) are
   distinguished by `penwidth="3"` — bold border.

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

### `value_range` and trees

For tree-shaped graphs (e.g., the reverse binary tree from a single
root), `anchor=root, radius=N, direction="forward"` is the natural way
to show the top N levels.

For forward-iteration graphs with a sink (cycle), `anchor=cycle_node,
radius=N, direction="backward"` shows the N levels of predecessors
above the cycle.

### Examples

**Reverse binary tree, full graph, three node annotations:**

```python
dot = to_dot(graph, show_binary=True, show_ternary=True, show_factors=True)
dot.render("bt", format="svg")
```

**Descent graph, render only what reaches 1 within 8 hops:**

```python
dot = to_dot(graph, anchor=1, radius=8, direction="backward")
```

**Pin specific ops to specific colors:**

```python
dot = to_dot(graph,
    op_colors={
        "÷3": ("#ccddff", "#6688bb"),  # explicit fill / edge pair
        "+2": "#cc4422",                # single string used for both
    })
```

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
renderer. Easy to build on top:

```python
from visiter import iterate, to_dot, darken

graph = iterate(...)
max_d = max(info["depth"] for info in graph["nodes"].values())
# Pin op_colors per (op, depth) using darken on a base palette,
# OR post-process dot.source to insert per-node fillcolors.
```

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
            "depth": int,            # required: BFS distance from nearest start
            "tags":  [str, ...],     # optional: present iff at least one tag matched
        },
        ...
    },

    "edges": [
        {"from": int, "to": int, "op": str},
        ...
    ],

    "pseudo_edges": [
        {"from": int, "op": str},
        ...
    ],

    "op_order": [str, ...],          # distinct op labels in rule order, then default
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
