# VisIter demos

Each script is self-contained and writes its outputs into `out/`
(gitignored). Names describe the **capability** each demo exercises —
there's no implied progression, run them in any order.

| script                                          | capability shown                                                                                     |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `anchor_radius_crop_and_recolor.sh`             | Anchor/radius cropping at render time + the `op_colors` palette override                             |
| `pipeline_to_svg_and_pdf.sh`                    | Full pipeline `build → to-dot → dot -Tsvg/-Tpdf`; also showcases wedged fills and bound stubs      |
| `non_integer_values.vit`                        | Arbitrary hashable values as nodes (strings, in this case)                                            |
| `pseudo_edges_bound_and_max_depth.sh`           | Pseudo-edges from the two distinct sources — `Rule.bound` and `max_depth` — both rendered identically |
| `wedged_multi_op_fills.sh`                      | Wedged-pie fills for nodes with multiple distinct outgoing op labels                                  |
| `op_label_stable_coloring.sh`                   | Stable colors per op label across runs; the `op_colors` pin for resilience under rule edits           |
| `schema_validation_in_pipeline.sh`              | JSON Schema validation as a pipeline checkpoint via `tee`                                             |
| `analytics_cycles_and_centrality.sh`            | NetworkX bridge: scalar / dict results (cycle counts, centrality)                                     |
| `analytics_condensation_rendered.sh`            | NetworkX bridge: graph-valued result (condensation) piped back into `to-dot`                          |
| `analytics_shortest_paths_highlighted.sh`       | NetworkX bridge: shortest paths, then tag-driven node highlighting on render                          |
| `custom_key_type.sh`                            | Iteration on `fractions.Fraction` values, classified as `"number"` via `build(..., key_type=...)`  |
| `nim_matchstick_game.vit`                       | Matchstick game (Nim): all game states, winning positions highlighted                                |
| `atm_banknote_combinations.vit`                 | ATM payout: all ways to dispense 80 EUR with 50/20/10 notes                                         |
| `tictactoe.sh`                                  | Tic-Tac-Toe game tree with symmetry reduction (canonical boards); arg: depth (default 9)            |
| `water_jugs.sh`                                 | Water jug problem (Die Hard 3): non-trivial cycles from fill/empty/pour; args: cap_a cap_b target   |

Run them all at once:

```bash
make demo
```

Each script prints one line per artifact it writes; check `demos/out/`
for the result. The `make demo` target requires `dot` (Graphviz) on
`PATH`; the `[validate]` extra (`pip install visiter[validate]`) is
needed for `schema_validation_in_pipeline.sh`; the `[analytics]`
extra (`pip install visiter[analytics]`) is needed for the three
`analytics_*` demos.
