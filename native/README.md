# visiter_native

The optional native BFS engine for [visiter](https://pypi.org/project/visiter/)
(Path A): a PyO3 extension that runs visiter's graph build natively while keeping
your Python callbacks.

You normally don't install this directly — use the extra:

```bash
pip install "visiter[native]"
```

Once `visiter_native` is importable, `viter(...).build()` uses it automatically
for every build — bounded or not (`engine="auto"`, the default) — handling
`max_depth`/`max_nodes`/`time_limit`/`bound` and producing a graph
byte-identical to the pure-Python build (`time_limit` is best-effort). visiter
works without it — pure Python is the always-available baseline.

Distributed as `abi3` wheels (one per platform, CPython 3.11+). MIT licensed.
See the [visiter manual](https://github.com/yaccob/visiter/blob/main/docs/manual.md#8-optional-native-acceleration-and-columnar-storage).
