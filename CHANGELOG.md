# Changelog

All notable changes to VisIter are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [0.16.0] — 2026-06-05

### Added
- **Native engine ships as a wheel — `pip install "visiter[native]"`.** The
  `visiter_native` PyO3 extension is now built as `abi3` wheels (one per
  platform, CPython 3.11+) by a `native-wheels` workflow and published to PyPI
  on a `native-v*` tag, so the native engine no longer needs a local Rust
  toolchain (`make native` still works for local builds). The new `[native]`
  extra pulls it; `engine="auto"` picks it up automatically.
- **`lang="rust"` reaches full parity with the Python path.** Three additions
  close the remaining gaps:
  - **`Fraction` state values** — exact rationals backed by
    `num-rational`/`num-bigint`, so e.g. golden ratio
    (`x → 1 + 1/x`) matches Python's `Fraction` at any depth. Rational programs
    compile through `cargo` (a shared target dir builds the deps once); other
    value types keep the faster bare-`rustc` path.
  - **`time_limit`** — the wall-clock deadline is honoured with the same
    truncation/warning/`on_limit` behaviour as the Python build.
  - **`label_rs=`** on `.case()`/`.default()` — a Rust expression (value bound
    to `s`) computing a per-call edge label, the `lang="rust"` analogue of
    returning `OpResult(value, label=…)`. Rejected in the Python path (use
    `OpResult` there).
  The only remaining gap is heterogeneous value types (rustc rejects the mix
  as a clear compile error, never a silent divergence).

---

## [0.15.0] — 2026-06-05

### Added
- **Optional native BFS engine (`engine=` on `viter`/`build`).** An optional
  Rust extension (`visiter_native`, built from `native/` via `make native`)
  accelerates the build for **unbounded** graphs (`max_depth=None`,
  `max_nodes=None`, no `bound`). Selection:
  - `engine="auto"` (default) — use the native engine when it is installed and
    the build is within its supported subset; otherwise pure Python.
  - `engine="native"` — require it; raise if unavailable or unsupported.
  - `engine="python"` — always pure Python.
  The native path keeps callbacks in Python (called per node via PyO3) and
  produces a Graph byte-identical to the pure-Python build. **Pure Python
  remains the always-available baseline** — visiter works unchanged without the
  extension or a Rust toolchain.
- **Columnar storage (`Graph.to_vitgraph` / `Graph.from_vitgraph`).** Stores a
  graph as a single `.vitgraph` file — two columnar tables (nodes, edges) plus
  metadata in a zip container, with edge endpoints interned to int32 node ids
  and categorical columns (`op`, `label`, `key_type`) dictionary-encoded, all
  Arrow IPC + zstd. ~10–26× smaller than JSON with much faster load and
  columnar analytics. `Graph.to_arrow()` exposes the `(nodes, edges,
  pseudo_edges)` pyarrow Tables for analytics. Requires the optional
  `[storage]` extra (pyarrow); JSON stays the default human-readable format.
  Round-trip fidelity matches JSON (node keys are `str(value)`).
- **Inline Rust-expression callbacks (`viter(..., lang="rust")`).** With
  `lang="rust"`, `.case()` / `.default()` take Rust expression *strings* (the
  current value is bound to `s`) instead of Python lambdas; they are co-located
  at the call site, compiled on the fly with `rustc` (cached on a source hash),
  and run natively. `consts={"N": ...}` injects i64 constants; the expression is
  the edge label/id when none is given. A **drop-in** for the Python path: the
  same chain yields the same graph, byte-for-byte — including default bounds
  (`max_depth=64` / `max_nodes=1024`), ghost-stub pseudo-edges, `bound=` and
  `tags=` (also Rust strings), and `key_type=`. State values may be `int`,
  `tuple`-of-`int`, or `str`. Requires `rustc` on PATH (no Python fallback for
  Rust source); `time_limit` and `OpResult` are not supported and raise rather
  than diverge. See `demos/rust/`.

### Changed
- **Minimum Python is now 3.11** (was 3.9). The lambda-label derivation in
  `.case()` relies on `code.co_positions()`, which only exists on 3.11+; on
  3.9/3.10 it could not disambiguate same-line lambdas, so those versions were
  never actually supported. CI now runs 3.11/3.12/3.13.

---

## [0.14.0] — 2026-06-04

### Breaking
- **Default crop `direction` changed from `"forward"` to `"both"`.**
  `to_dot(anchor=…, radius=…)` without an explicit `direction` now walks
  edges undirected, showing the full local context around the anchor.
  Callers that relied on the forward-only default must pass
  `direction="forward"` explicitly.

### Added
- **`to_dot(anchor=…)` accepts a list/tuple/set of node values.** With
  several anchors the rendered set is the union of their `radius`-hop
  neighborhoods, all bounded by the same `radius` (multi-source BFS).
  A single value keeps working unchanged.
- **`to_dot(max_depth=N)`** — render-time depth crop measured from the
  graph's root nodes outward (forward). Keeps nodes within `N` hops of a
  root; deeper nodes are dropped and the cut edges become dashed ghost
  stubs, like the anchor/radius crop. Distinct from the build-time
  `max_depth` on `viter(...)`, and combines with anchor/radius and
  value_range by intersection.

---

## [0.13.0] — 2026-05-03

### Breaking
- **Edge schema: `label` is now a required field on every `edge` and
  `pseudo_edge`.** Hand-written graph dicts (test fixtures, NetworkX
  round-trips, JSON snapshots produced before this version) must be
  updated to carry `label` per edge — the renderer reads `edge["label"]`
  directly without consulting `op_labels`. The `additionalProperties:
  false` constraint stays, so unknown fields still error. Schema URL
  remains `/v1/graph.schema.json` because v0.x has no compatibility
  guarantees yet; a future v1.0 release would have shipped this as
  `/v2/`.
- **`to_dot(..., op_labels=...)` keyword removed.** Per-op render-time
  label overrides are no longer a concern of the renderer; labels are
  baked into edges at build time. Callers that need different labels
  rebuild the graph (or use `OpResult` from inside an op fn).
- **`build_dot(graph, op_labels, ...)` signature changed.** The
  `op_labels` positional parameter is gone — `build_dot` reads
  `edge["label"]` from each edge directly.

### Added
- **`OpResult(value, label=None)`** — optional return type for case/
  default fns that want a per-call edge label. Returning
  `OpResult(value, label="…")` from `fn` overrides the case's static
  label for that one edge; returning a plain value (or `OpResult(value)`
  / `OpResult(value, label=None)`) keeps the static label. Discrimination
  is by `isinstance`, so the value field can carry tuples or any custom
  object without ambiguity. Pseudo-edges (suppressed by `bound=False`
  or `max_depth`) never call `fn` and therefore always carry the static
  label. Exported from `visiter` and pre-bound in the `.vit` namespace.

---

## [0.12.0] — 2026-04-19

### Breaking
- **`viter()` is now the primary entry**, returning an immutable
  `Builder` instead of rendering directly. Chain cases via `.case()` /
  `.cases()`, optionally a `.default()`, then terminate with `.build()`
  (returns Graph) or `.render()` (shortcut for
  `build().to_dot().render()`).
- **`Rule`, `Op`, `build` removed from the public API** (`from visiter
  import ...`). The explicit `build(start, rules, default)` call is
  replaced by the Builder chain; `Rule`/`Op` wrapping is gone in favor
  of direct `condition, fn` pairs in `.case(cond, fn, label=..., id=...,
  bound=..., exclusive=...)`. The same helpers remain available
  internally via `visiter.iteration` for tests.
- **`on_limit` default in `to_dot()`** changed from `"raise"` to
  `"stop"`, matching `build()`. Callers relying on the old default
  must now pass `on_limit="raise"` (or `OnLimit.RAISE`) explicitly.
- **CLI namespace changes**: `.vit` files no longer see `Rule`, `Op`,
  or `build` pre-bound. The new names `viter`, `Match`, `OnLimit` take
  their place.

### Added
- `Match.ALL` / `Match.FIRST` — enum selecting whether every matching
  case fires (additive fan-out) or only the first (if-elif-else
  semantics). Per-case override via `.case(..., exclusive=True|False)`.
- `OnLimit.STOP` / `OnLimit.RAISE` — enum form of the limit-policy
  option (still accepts raw strings for backward ergonomics).
- `.cases(iterable)` helper on the Builder for bulk rule registration,
  accepting `(cond, fn)` tuples or `(cond, fn, kwargs)` triples.
- Strict error when `.default()` is called twice on the same Builder.

### Changed
- All 14 `.vit` demos migrated to the fluent Builder API.
- `tictactoe.py` helper exposes `make_cases()` returning tuples instead
  of `make_rules()` returning `Rule` objects.
- `Rule` namedtuple extended with an `exclusive` field (default
  `False`); `build()`'s main loop short-circuits after a matched
  exclusive rule.

---

## [0.11.0] — 2026-04-18

### Breaking
- **Fluent API**: `build()` now returns a `Graph` (dict subclass) with
  chainable methods: `.to_dot()`, `.filter()`, `.tap()`, `.peek()`.
  `to_dot()` returns a `Dot` wrapper with `.render()`, `.tap()`.
  Existing code that treats `build()` result as a plain dict still works.
- **CLI rewrite**: `visiter` subcommand-based CLI replaced by `viter`,
  a simple executor for `.vit` files. No subcommands, no own flags.
  All arguments after the `.vit` path are passed to the script.
  The `visiter` entry point is removed.
- **`.vit` file format**: `.vit` files are now full Python scripts using
  the fluent API, not eval'd argstring fragments. Example:
  `build(10, [...], None).to_dot().render()`.
- **Safety defaults**: `max_nodes` default 1024 (was 1M), `max_depth`
  default 64 (was None), `on_limit` default "stop" (was "raise").
  Warnings emitted to stderr when limits are hit.
- **`visiter validate`** removed from CLI. Schema stays in the package.
- **Pipe composition** (`visiter build | visiter to-dot`) removed.
  Use the fluent chain in a single `.vit` file instead.

### Added
- `Graph` class (dict subclass) with `.to_dot()`, `.filter()`, `.tap()`.
- `Dot` class (graphviz.Digraph wrapper) with `.render()`, `.tap()`.
- `viter()` convenience function: one-shot `build().to_dot().render()`.
- `write()` factory function for use with `.tap()`:
  `.tap(write())` (stdout) or `.tap(write(file="g.json"))` (file).
- `NxFilter` for NetworkX graph transforms in the fluent chain:
  `build(...).filter(NxFilter(nx.condensation)).to_dot().render()`.
- `__file__` bound in `.vit` exec namespace to the script path.
- `sys.argv` passthrough for parameterized `.vit` files.

### Changed
- `to_dot()` returns `Dot` wrapper instead of raw `graphviz.Digraph`.
- Demos restructured into thematic subdirectories (`basics/`,
  `rendering/`, `integration/`, `applications/`) with generated
  SVG outputs checked in for browsing without Graphviz.

---

## [0.10.0] — 2026-04-17

### Breaking
- Python API function renamed: `iterate()` → `build()`. The function
  name now describes the goal (building a graph) rather than the
  mechanism (iterating). All imports change from
  `from visiter import iterate` to `from visiter import build`.
- CLI eval namespace: `iterate` → `build` (argstrings that called
  `iterate(...)` directly must be updated).

### Added
- CHANGELOG.md (this file).
- GitHub Actions CI (tests + demos on Python 3.9/3.12/3.13).
- TL;DR block at the top of `docs/tutorial.md`.

### Fixed
- JSON Schema `$id` now uses a resolvable `raw.githubusercontent.com`
  URL instead of the non-resolvable `github.com` repo path.

## [0.9.0] — 2026-04-17

### Breaking
- Edge endpoints (`from`/`to`) in the graph dict are now always
  `str(value)`, matching node keys. Previously tuple-valued nodes
  produced JSON arrays for endpoints, causing round-trip mismatches.

### Added
- `node_label` callback on `to_dot()` — custom node display via
  `(key, info) → str` (supports Graphviz HTML-labels).
- Tic-Tac-Toe demo: full game tree with symmetry reduction (765 nodes),
  HTML-table board display.
- Water Jugs demo: reachability graph + shortest-path subgraph via
  `visiter analyze` and NetworkX.

### Changed
- All demos refactored to pure `visiter` pipelines (no Python heredocs).
- Default palette expanded from 6 to 12 colour pairs.

## [0.8.1] — 2026-04-17

### Added
- Tic-Tac-Toe demo with 8-fold symmetry reduction.
- Palette expanded from 6 to 12 colour pairs (red, gold, lime, cyan,
  indigo, pink).

## [0.8.0] — 2026-04-17

### Breaking
- CLI reads the argstring from a file or stdin instead of a positional
  argument. Old: `visiter build 'expr'`. New: `echo 'expr' | visiter build`
  or `visiter build < file.vit`.

### Added
- `.vit` file format with `#`-comment stripping and shebang support.
- `visiter build`, `visiter to-dot`, and `visiter render` all accept
  `FILE` (default stdin) via `click.File("r")`.

## [0.7.2] — 2026-04-17

### Changed
- `iterate()` accepts `default` as a positional argument (was keyword-only).
- README quickstart simplified.

## [0.7.1] — 2026-04-17

### Changed
- `viter -o` is optional; output defaults to stdout.

## [0.7.0] — 2026-04-17

### Breaking
- `Op(func, *, label=None, id=None)` — `label` and `id` are now
  keyword-only arguments.
- `iterate` subcommand renamed to `build`.

### Added
- `key_type=` parameter on `iterate()` for custom value type
  classification (Fraction, Decimal, etc.).
- `--import MODULE[:NAME,…]` CLI option for extending the eval namespace.
- `Fraction` and `Decimal` are available by default in the CLI namespace.
- `viter` one-shot CLI entry point with safe defaults
  (`max_nodes=10000`, `time_limit=00:00:30`, `on_limit="stop"`).
- Manual §5: recipe for Fraction/Decimal with CLI examples.
- Nim matchstick game and ATM banknote combination demos.

### Changed
- Manual renumbered (§1–§7, previously had a gap at §7).

## [0.6.0] — 2026-04-16

### Breaking
- Default crop direction changed from `"backward"` to `"forward"`.

### Added
- Stable `Op.id` field, separate from display `label`. Pinning via
  `op_colors` and `op_order` uses `id`, not `label`.
- Embedded SVGs in tutorial and manual (generated from live CLI).

### Changed
- Resolved palette (`resolve_op_colors`) computed once in `to_dot()`
  and threaded through; removed unused `edge_dir` parameter from
  `build_dot()`.

## [0.5.1] — 2026-04-16

### Fixed
- `Op` auto-label now works for CLI eval and multi-line expressions.

## [0.5.0] — 2026-04-16

### Added
- Auto-derived `Op` labels from `func` (lambdas via `ast.unparse`,
  named functions via `__name__`).
- Single-source version from `__init__.py` via hatchling.

## [0.4.0] — 2026-04-16

### Added
- `key_type` field on every node in the graph dict.
- `schema_version` is now required.
- Arbitrary node attributes and `node_label_attr` on `to_dot`.

## [0.3.0] — 2026-04-16

### Added
- NetworkX bridge (`visiter analyze`, `[analytics]` extra).
- `comparison.md` — honest positioning against NestGraph, Maude, LoLA.
- Three new demos; capability-based naming; visual vocabulary docs.

## [0.2.0] — 2026-04-15

### Changed
- CLI switched to `rich-click` for a unified, modern interface.
- Publish guard (`scripts/check_pypi_version.py`) prevents re-uploads.

### Added
- Tutorial and runnable demos (`demos/*.sh`).

## [0.1.0] — 2026-04-15

### Added
- Initial release: `iterate()` BFS graph builder, `to_dot()` Graphviz
  renderer, CLI with `iterate` / `to-dot` / `validate` subcommands.
- Value-neutral iteration (not limited to integers).
- JSON Schema for the graph dict (`schemas/v1/graph.schema.json`).

[0.12.0]: https://github.com/yaccob/visiter/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/yaccob/visiter/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/yaccob/visiter/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/yaccob/visiter/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/yaccob/visiter/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/yaccob/visiter/compare/v0.7.2...v0.8.0
[0.7.2]: https://github.com/yaccob/visiter/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/yaccob/visiter/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/yaccob/visiter/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/yaccob/visiter/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/yaccob/visiter/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/yaccob/visiter/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/yaccob/visiter/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/yaccob/visiter/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/yaccob/visiter/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yaccob/visiter/releases/tag/v0.1.0
