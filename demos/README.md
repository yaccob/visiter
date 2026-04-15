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

Run them all at once:

```bash
make demo
```

Each script prints one line per artifact it writes; check `demos/out/`
for the result. The `make demo` target requires `dot` (Graphviz) on
`PATH`; the `[validate]` extra (`pip install visiter[validate]`) is
needed for `03_validate_in_pipeline.sh`.
