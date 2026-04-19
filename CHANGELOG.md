# Changelog

All notable changes to VisIter are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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
