# VisIter demos

Self-contained `.vit` files organized by language and topic. Each
produces SVG output (to stdout or files in `out/`). Run them with
`viter`:

```bash
viter demos/python/basics/nim.vit > nim.svg
viter demos/python/applications/tictactoe.vit --depth 3 > tictactoe.svg
```

The tree is `demos/<language>/<topic>/`. `python/` holds the full set;
`rust/` mirrors the same topic layout but only for the demos that have a
`lang="rust"` counterpart.

## python/

### basics/

| demo                  | what it shows                                                        |
| --------------------- | -------------------------------------------------------------------- |
| `nim.vit`             | Nim matchstick game — all game states, winning positions highlighted |
| `atm.vit`             | ATM payout — all ways to dispense 80 EUR with 50/20/10 notes        |
| `collatz.vit`         | Collatz (3n+1) trajectories from 6 and 9 merging into the 1→4→2→1 cycle; powers of two highlighted |
| `reverse_collatz.vit` | Collatz run backwards — the predecessor tree of 1, bounded by `max_depth` |
| `golden_ratio.vit`    | Fraction iteration, `key_type="number"` override                    |
| `string_iteration.vit`| Arbitrary hashable values as nodes (strings)                         |

### rendering/

| demo                   | what it shows                                                       |
| ---------------------- | ------------------------------------------------------------------- |
| `cropping.vit`         | Tight anchor/radius crop with ghost stubs at the boundary           |
| `custom_colors.vit`    | `op_colors` override (pin colors by op identity)                    |
| `color_stability.vit`  | How op colors stay stable as rules are added/reordered              |
| `ghost_stubs.vit`      | Pseudo-edges from a case's `bound=` vs. `max_depth` — same rendering |
| `multi_op_fills.vit`   | Wedged pie-slice fills for nodes with multiple outgoing ops         |

### integration/

| demo                  | what it shows                                                        |
| --------------------- | -------------------------------------------------------------------- |
| `condensation.vit`    | SCC condensation via `NxFilter(nx.condensation)`                     |
| `inspection.vit`      | NetworkX queries (cycles, centrality) — text output, no rendering   |
| `shortest_paths.vit`  | Shortest paths to a target, highlighted via node tags               |

### applications/

| demo                  | what it shows                                                        |
| --------------------- | -------------------------------------------------------------------- |
| `tictactoe.vit`       | Tic-Tac-Toe game tree with symmetry reduction; `--depth N`          |
| `water_jugs.vit`      | Water jug problem with shortest-path analysis; `--cap-a/b --target` |

## rust/

Inline `lang="rust"` callbacks (Rust expression strings), compiled on
the fly with `rustc`. Require `rustc` on `PATH`; the `Fraction`-valued
`golden_ratio.vit` also needs `cargo`. Each is the counterpart of the
`python/` demo with the same name and renders a byte-for-byte identical
SVG (enforced by `tests/test_demos.py`).

### basics/

| demo                  | what it shows                                                        |
| --------------------- | -------------------------------------------------------------------- |
| `nim.vit`             | Counterpart of `python/basics/nim.vit` (inline Rust callbacks + tag) |
| `collatz.vit`         | Counterpart of `python/basics/collatz.vit` (inline Rust callbacks + tag) |
| `reverse_collatz.vit` | Counterpart of `python/basics/reverse_collatz.vit` (`match=ALL` branching) |
| `golden_ratio.vit`    | Exact rationals via `num-rational`'s `BigRational` (needs `cargo`)   |
| `string_iteration.vit`| `str` states (Path B): drop trailing vowels until a consonant       |

### applications/

| demo                  | what it shows                                                        |
| --------------------- | -------------------------------------------------------------------- |
| `water_jugs.vit`      | Water-jug reachability, inline Rust callbacks, `consts=` + highlight tag |

## Running all demos

```bash
make demo
```

Requires `dot` (Graphviz) on `PATH`. The `[analytics]` extra
(`pip install visiter[analytics]`) is needed for the `python/integration/`
demos.
