# VisIter Manual

> **First time here?** This manual is a reference. If you'd rather
> start with motivation, a small example, and a build-up of concepts,
> read [tutorial.md](tutorial.md) first and come back to the manual
> when you need parameter-level detail.

VisIter is two functions that compose: `build` builds a directed graph
by applying guarded rules to seed values and following reachable
successors, and `to_dot` turns such a graph into a Graphviz Digraph
for visualization. The two are connected only by
a documented dict shape, so each can be used standalone.

This manual walks through the data model, semantics, and common
patterns. For the absolute minimum, see [README.md](../README.md).

---

## 1. Data model

### `Op(func, *, label=None, id=None)`

A pure operation: a callable plus two string fields — a display
**`label`** and a stable **`id`** used for keying. Only `func` is
accepted positionally; `label` and `id` are keyword-only, to keep
the intent of an override visible at the call site and avoid the
ambiguity of two adjacent unnamed strings.

```python
Op(lambda x: x // 2)                          # label = id = "x // 2"
Op(lambda x: x // 2, label="÷2")              # label = "÷2", id = "x // 2"
Op(square)                                    # label = id = "square"
Op(lambda x: x + 1, label="⊕", id="inc")      # label = "⊕", id = "inc"
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
`label` (the one signal we have). `build` emits a `UserWarning`
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

A `default: Op | None` argument to `build` (see below) covers the
"nothing else fired" case orthogonally.

---

## 2. `build` — building the graph

### Signature

```python
build(start, rules, default, *,
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
- `default`: an `Op` or `None` (**required** — the caller must
  explicitly choose). May be passed positionally as the third argument
  or as a keyword. Fires only when no rule's `condition` matches at
  a given node.
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
- `key_type`: optional override for per-node classification. `None`
  (default) infers each node's `key_type` from the Python type of its
  value via `json_type`. Pass one of the seven JSON Schema primitive
  names (`"null"`, `"boolean"`, `"integer"`, `"number"`, `"string"`,
  `"array"`, `"object"`) to fix a single type on every node, or a
  callable `value → str | None` to classify per value (returning
  `None` falls back to `json_type` for that value). Useful when a
  domain type serialises to a string but should be treated
  numerically (`Fraction`, `Decimal`, `sympy.Rational`) so that
  type-sensitive features (`value_range`, `show_factors`) engage.

### Output graph dict

```python
{
    "schema_version": "1",             # always set by build
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

Each block below shows an `build(...)` call and the rendered graph
that comes out of it. The rendering details (colors, wedges, dashed
stubs) are defined in §3 — here the pictures just show what the
iteration *produces* so the code doesn't have to be read in the
abstract.

**Descent with divisor rule and increment default, range(1, 30):**

```python
graph = build(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],
    default=Op(lambda x: x + 2, label="+2"),
)
```

![descent, full graph](images/iterate_descent.svg)

**Reverse binary tree from 1, ceiling at 64, depth-capped at 5:**

```python
ceiling = 64
graph = build(
    start=[1],
    rules=[
        Rule(lambda x: True,
             Op(lambda x: 2 * x, label="×2"),
             bound=lambda x: 2 * x <= ceiling),
        Rule(lambda x: True,
             Op(lambda x: 2 * x + 1, label="×2+1"),
             bound=lambda x: 2 * x + 1 <= ceiling),
    ],
    default=None,
    max_depth=5,
)
```

![reverse binary tree with depth cap](images/iterate_reverse_binary.svg)

**Multi-way decision via conjunctive rules:**

```python
graph = build(
    start=range(1, 30),
    rules=[
        Rule(lambda x: x % 15 == 0, Op(lambda x: x // 15, label="÷15")),
        Rule(lambda x: x % 3 == 0 and x % 15 != 0, Op(lambda x: x // 3, label="÷3")),
        Rule(lambda x: x % 5 == 0 and x % 15 != 0, Op(lambda x: x // 5, label="÷5")),
    ],
    default=Op(lambda x: x + 1, label="+1"),
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
             show_binary=False, show_factors=False,
             time_limit=None, on_limit="raise")
```

Returns a `graphviz.Digraph`. Caller decides what to do with it
(`.source`, `.render(format="svg")`, etc.).

### Inputs

- `graph`: dict with the shape produced by `build`. (Strictly: needs
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
- `show_binary` / `show_factors`: extra annotations under each node
  label. Binary uses 4-bit nibble grouping.
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
- **Pseudo-edge** (from `build`): when `Rule.bound` returned False
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
graph = build(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0,
                Op(lambda x: x // 3, label="÷3", id="div3"))],
    default=Op(lambda x: x + 2, label="+2", id="inc2"),
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
| **Bold border** (`penwidth=3`)     | node is in `graph["roots"]` — a seed value passed to `build`                                  |
| **No fill (white)**                | leaf: zero outgoing edges — iteration terminates here                                            |
| **Solid fill**                     | exactly one outgoing op label; fill = that op's color                                            |
| **Wedged-pie fill**                | ≥2 distinct outgoing op labels; one slice per op                                                 |
| **Darkened fill + white font**     | node carries the `"highlight"` tag (set by a predicate in `build(..., tags={...})`)            |
| **Dashed edge to a tiny target**   | "ghost stub" — the iteration would continue here but was stopped by `Rule.bound`, `max_depth`, or render-time crop |

One graph exhibiting every style in the table above:

![visual vocabulary — one graph, every style](images/node_styles.svg)

---

## 4. CLI

A single `visiter` command dispatches to subcommands. Each subcommand
(`build`, `to-dot`) takes a single positional argument: a Python
expression that is spliced into a call to the corresponding function
and `eval`'d. `Op`, `Rule`, `build`, `to_dot`, and `graph` (for the
renderer) live in the eval namespace.

A `.vit` file is a Python script executed by the `viter` command.
The exec namespace pre-binds `Op`, `Rule`, `build`, `viter`, `to_dot`,
`Graph`, `Dot`, `NxFilter`, `write`, `Fraction`, and `Decimal`.

### Running a `.vit` file

```bash
viter script.vit                  # SVG to stdout
viter script.vit > out.svg        # redirect to file
viter script.vit --arg value      # pass args to the script
viter --version                   # show version
```

All arguments after the `.vit` path are passed through as `sys.argv`
to the script. The script can use `argparse` or raw `sys.argv`.

### One-shot: `viter()`

For the simplest case — build, render with defaults — the `viter()`
shortcut wraps `build().to_dot().render()`:

```python
#!/usr/bin/env viter
viter(
    range(1, 30),
    [Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
    Op(lambda x: x + 2),
)
```

### Fluent chain

When you need `to_dot` options, filters, or intermediate saves, use
the explicit chain:

```python
#!/usr/bin/env viter
build(
    range(1, 30),
    [Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
    Op(lambda x: x + 2),
).tap(write(file="graph.json"))       \
 .to_dot(anchor=1, radius=8)         \
 .render(file="out.svg")
```

### Safety defaults

`build()` ships conservative defaults so a typo'd rule can't silently
burn minutes or gigabytes:

| Parameter       | Default       | Purpose                                    |
| --------------- | ------------- | ------------------------------------------ |
| `max_nodes`     | `1024`        | BFS node cap                               |
| `max_depth`     | `64`          | BFS depth cap                              |
| `on_limit`      | `"stop"`      | Stop and warn (vs. `"raise"`)              |
| `time_limit`    | `None`        | Wall-clock limit (`"hh:mm:ss"`)            |

When a limit is hit, `build()` emits a warning to stderr and returns
the partial graph. Pass `None` to disable a limit, or a higher value
to raise it.

### Errors

Any error surfaces as a normal Python exception with its native
traceback. `exec` is appropriate here because this is a local research
tool: running `viter script.vit` is no different in trust model from
running any local Python script.

---

## 5. Recipes

### "I want depth-gradient coloring"

VisIter exposes `depth` per node but doesn't ship a depth-gradient
renderer. Easy to build on top by constructing the graphviz.Digraph
yourself and picking each node's fill via `darken` on a base color:

```python
from visiter import build, Op, Rule, darken
import graphviz

graph = build(
    start=[1],
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],
    default=Op(lambda x: x + 2, label="+2"),
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

Use `value_range=(low, high)` in `to_dot`. To stop build from
producing huge values in the first place, use `Rule.bound`.

### "Several disconnected starts, render each cluster separately"

Run `build` once per start, render separately. There's no built-in
multi-rooted layout; Graphviz handles disconnected components in one
canvas if rendered together.

### "I need a custom predicate for highlighting"

Pass it as a `tags` entry. The `"highlight"` tag name is the renderer's
visual emphasis trigger:

```python
graph = build(..., tags={"highlight": lambda x: is_prime(x)})
```

Other tag names are stored on nodes too and accessible via
`graph["nodes"][vstr]["tags"]`, but only `"highlight"` triggers the
renderer's fill-darkening logic.

### "I want to use `Fraction` / `Decimal` / other domain numeric types"

The default per-node classification comes from `json_type`, which only
knows about Python's built-in JSON types. Anything outside that set —
`fractions.Fraction`, `decimal.Decimal`, `sympy.Rational`, a custom
quantity class — falls through to `"string"` because those values
serialise through `str()`. Pass `key_type=` to `build` to declare
the true semantic type.

As a worked example, the continued-fraction recurrence `x ↦ 1 + 1/x`
starting at `1` produces the Fibonacci-ratio convergents to the
golden ratio. With `Fraction` the arithmetic is exact; without the
`key_type=` override every node would be labelled `"string"` in the
graph dict — honest for JSON-on-the-wire, misleading for what the
values actually mean.

`Fraction` and `Decimal` are pre-bound in the `.vit` namespace:

```python
#!/usr/bin/env viter
viter(
    [Fraction(1)],
    [Rule(lambda x: True, Op(lambda x: 1 + 1/x))],
    None,
    max_depth=7,
    key_type="number",
)
```

![golden-ratio convergents as Fraction, classified as "number"](images/golden_ratio_convergents.svg)

Two forms of `key_type=` are available:

- **A plain string** — one of the JSON Schema primitives (`"null"`,
  `"boolean"`, `"integer"`, `"number"`, `"string"`, `"array"`,
  `"object"`) — sets one fixed classification on every node.
- **A callable `value → str | None`** — called per value; return one
  of those primitives, or `None` to delegate to `json_type` for that
  value. Useful when a single graph mixes domain types (e.g. ints
  and `Fraction`s coexisting) and you want `json_type`'s defaults
  on the integers but an override on the rationals:

  ```python
  build(
      [1, Fraction(1, 2)],
      [],
      None,
      key_type=lambda v: "number" if isinstance(v, Fraction) else None,
  )
  ```

The override is a **declaration of intent**, not a transformation:
renderer features that actually consume the value still have to be
able to handle what you passed. `value_range` in particular calls
`int(vstr)` on the node keys, which fails on `"1/2"`; so declaring
`Fraction` values as `"number"` does *not* unlock `value_range` for
them. Pick the classification that matches how downstream consumers
should treat the data, and keep the data compatible with the claim.

**Beyond `Fraction` and `Decimal`.** Any other type — `sympy.Rational`,
a third-party quantity class, your own domain object — just needs a
standard `import` in the `.vit` file:

```python
#!/usr/bin/env viter
from sympy import Rational

viter(
    [Rational(1, 2)],
    [Rule(lambda x: x.q < 100, Op(lambda x: 1 + 1/x))],
    None,
    key_type="number",
)
```

A runnable end-to-end version of this pipeline lives in
[`demos/basics/golden_ratio.vit`](../demos/basics/golden_ratio.vit).

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
integers, strings, tuples of hashables, frozensets, etc. `build`
keys nodes by `str(value)`, so two values with the same string form
collide. On JSON output, native JSON types pass through unchanged;
non-native values are coerced to their `str()` form by the CLI's
`json.dump(default=str)`. The schema reflects this by accepting any
JSON type for edge `from`/`to` and any non-empty string for node
keys.

To let consumers recover the type of a node value despite JSON's
string-keys constraint, `build` records it explicitly as a
required `key_type` attribute on each node — using the seven
JSON Schema primitives (`null`, `boolean`, `integer`, `number`,
`string`, `array`, `object`) so any JSON consumer can interpret it
without Python-specific knowledge. The Python → JSON mapping is:
`bool` → `boolean`, `int` → `integer`, `float` → `number`, `str` →
`string`, `list`/`tuple`/`set`/`frozenset` → `array`, `dict` →
`object`, `None` → `null`; anything else falls back to `string` via
the default `str()` coercion. The renderer consults `key_type`
directly when deciding whether type-sensitive features
(`show_binary`, `show_factors`, `value_range`)
should fire — no string-pattern heuristic is involved. Hand-built
graph dicts and producers other than `build` must supply
`key_type` themselves; the schema enforces this via `required`.

For domain types whose values do not fit the built-in mapping —
`fractions.Fraction`, `decimal.Decimal`, `sympy.Rational`, a custom
quantity class — pass `key_type=` to `build` to override the
default. A bare string sets a single type for every node; a callable
`value → str | None` classifies per value, with `None` delegating to
`json_type` for that particular value. Type-sensitive renderer
features still require that the downstream value is actually
representable as the claimed type (e.g. `value_range` casts node
keys via `int(...)`, which fails on `"1/2"`), so the override is a
declaration of intent, not a transformation — keep the data
compatible with the claim.

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

Validate a graph document programmatically:

```python
pip install visiter[validate]
```

```python
import json
from importlib.resources import files
from jsonschema import Draft202012Validator

schema = json.loads(files("visiter").joinpath(
    "schemas/v1/graph.schema.json").read_text())
Draft202012Validator(schema).validate(graph_dict)
```

---

## 7. Integrating with NetworkX

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
from visiter import build, Op, Rule, to_dot
from visiter.analytics import to_networkx, from_networkx
import networkx as nx

graph = build(
    start=range(1, 30),
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],
    default=Op(lambda x: x + 2, label="+2"),
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

```python
# In a .vit file — NxFilter handles the round-trip:
build(...).filter(NxFilter(nx.condensation)).to_dot(node_label_attr="members").render()
```

See [`demos/integration/condensation.vit`](../demos/integration/condensation.vit)
for the full end-to-end example.

### Fluent chain: `NxFilter`

For graph-to-graph transforms, `NxFilter` plugs into the fluent chain:

```python
#!/usr/bin/env viter
import networkx as nx

build(...).filter(NxFilter(nx.condensation)).to_dot().render()
```

For ad-hoc inspection (scalar results, cycle lists, centrality), use
NetworkX directly in the `.vit` file:

```python
from visiter.analytics import to_networkx
nxg = to_networkx(g)
print(list(nx.simple_cycles(nxg)))
print(nx.in_degree_centrality(nxg))
```

See the [`demos/integration/`](../demos/integration/) directory for
runnable end-to-end examples.

### Worked example: water jug shortest path

The classic "Die Hard 3" puzzle: measure exactly 4 litres with a 3L
and a 5L jug. Six actions (fill, empty, pour) build a 16-node
reachability graph from `(0, 0)`. The graph has non-trivial cycles
because the actions are not self-inverse (fill ≠ empty).

The full graph, with target states (where either jug holds 4)
highlighted:

![water jug — full reachability graph](images/water_jugs_full.svg)

The solution is the shortest path from `(0, 0)` to any target node.
`nx.all_shortest_paths` finds it; extracting the path nodes and edges
into a subgraph and piping that through `to-dot` renders the answer
as a standalone image:

![water jug — shortest path to 4L](images/water_jugs_path.svg)

Bold cell values mark the target amount; the darkened node is the
goal state where the path ends. The full pipeline (build → analyze →
subgraph → render) is in
[`demos/applications/water_jugs.vit`](../demos/applications/water_jugs.vit).

### Scope

The bridge is deliberately thin: two Python functions plus one CLI
subcommand. We don't wrap individual NetworkX algorithms — their
names are already their documentation, and wrapping would only
duplicate surface area we can't maintain. Everything NetworkX can do
is one `nx.<something>(graph)` call away.
