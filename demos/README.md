# VisIter demos

Each script is self-contained and writes its outputs into `out/`
(gitignored). Run any of them from the repo root or from this
directory; they `cd` to their own location.

| script                              | shows                                                                 | tutorial section |
| ----------------------------------- | --------------------------------------------------------------------- | ---------------- |
| `01_one_data_many_views.sh`         | One iterate result, several `to-dot` views with different crops/colors | "How do I show only a slice?" |
| `02_pipeline_to_pdf.sh`             | Full pipeline `iterate → to-dot → dot -Tsvg/-Tpdf`                    | "What does the command line look like?" |
| `03_validate_in_pipeline.sh`        | Schema validation as a pipeline checkpoint via `tee`                  | "What does the JSON Schema buy me?" |
| `04_string_iteration.sh`            | Iteration on **strings** (not integers) — drop trailing vowels         | "Does this only work for numbers?" |
| `05_analyze_cycles_and_depths.sh`   | Ask NetworkX: how many nodes/edges, which cycles, which nodes are most central? | "Can I run graph algorithms on the result?" |
| `06_analyze_condensation.sh`        | Collapse strongly-connected components with `nx.condensation`, then render the resulting DAG side-by-side with the original | "Can I run graph algorithms on the result?" |
| `07_analyze_shortest_paths.sh`      | Compute shortest paths to the cycle attractor with NetworkX, highlight every node that lies on one | "Can I run graph algorithms on the result?" |

Run them all at once:

```bash
make demo
```

Each script prints one line per artifact it writes; check `demos/out/`
for the result. The `make demo` target requires `dot` (Graphviz) on
`PATH`; the `[validate]` extra (`pip install visiter[validate]`) is
needed for `03_validate_in_pipeline.sh`; the `[analytics]` extra
(`pip install visiter[analytics]`) is needed for demos 05–07.
