"""Optional native acceleration for ``visiter.iteration.build``.

The native engine (the ``visiter_native`` extension, built from ``native/``)
is an *optional* accelerator. When it is not importable — the default for a
plain ``pip install visiter`` — everything falls back to the pure-Python BFS,
so visiter always works without a toolchain.

The native path only handles the **unbounded** subset of ``build`` semantics
(no ``max_depth`` / ``max_nodes`` / ``time_limit`` / ``bound`` — the
"compute the full graph" case the native engine is meant for). The caller
gates on that subset; this module assembles the resulting Graph dict so that
it is byte-identical to the pure-Python output. Anything outside the subset
returns ``None`` and the caller uses pure Python.
"""

try:
    import visiter_native as _native
except ImportError:  # pragma: no cover - exercised by absence, not presence
    _native = None


def native_available():
    """True iff the native engine is importable."""
    return _native is not None


def supports(rules, *, max_depth, max_nodes, time_limit):
    """Whether the native path can reproduce this build exactly.

    Restricted to the unbounded subset: any depth/node/time limit, or any
    ``bound`` predicate, introduces pseudo-edges / truncation semantics the
    native engine does not (yet) implement, so we defer to pure Python.
    """
    return (
        _native is not None
        and max_depth is None
        and max_nodes is None
        and time_limit is None
        and all(r.bound is None for r in rules)
    )


def native_build(starts, rules, default, *, tags, key_type):
    """Run the unbounded BFS natively and assemble the Graph dict.

    Mirrors ``visiter.iteration.build``'s output exactly for the supported
    subset. ``starts`` is the normalized list of start values.
    """
    from .graph import Graph
    from .iteration import OpResult, _make_key_type_resolver

    conditions = [r.condition for r in rules]
    op_funcs = [r.op.func for r in rules]
    exclusive = [bool(r.exclusive) for r in rules]
    default_func = default.func if default is not None else None

    values, depths, raw_edges = _native.build_raw(
        list(starts), conditions, op_funcs, exclusive, default_func, OpResult)

    # Op registration: first-seen id wins, rules before default (same order
    # as the pure-Python _register_op, minus the collision warning).
    op_order = []
    op_labels = {}
    seen = set()

    def register(op):
        if op.id not in seen:
            seen.add(op.id)
            op_order.append(op.id)
            op_labels[op.id] = op.label

    for r in rules:
        register(r.op)
    if default is not None:
        register(default)

    # op index -> Op object (index n_rules is the default).
    ops_by_idx = [r.op for r in rules]

    resolve_key_type = _make_key_type_resolver(key_type)
    tags = tags or {}

    nodes = {}
    for value, depth in zip(values, depths):
        info = {"depth": depth, "key_type": resolve_key_type(value)}
        node_tags = [name for name, fn in tags.items() if fn(value)]
        if node_tags:
            info["tags"] = node_tags
        nodes[str(value)] = info

    edges = []
    for from_idx, to_idx, op_idx, label in raw_edges:
        op = ops_by_idx[op_idx] if op_idx < len(rules) else default
        edges.append({
            "from": str(values[from_idx]),
            "to": str(values[to_idx]),
            "op": op.id,
            "label": label if label is not None else op.label,
        })

    return Graph({
        "schema_version": "1",
        "roots": list(starts),
        "nodes": nodes,
        "edges": edges,
        "pseudo_edges": [],
        "op_order": op_order,
        "op_labels": op_labels,
    })
