"""Optional native acceleration for ``visiter.iteration.build``.

The native engine (the ``visiter_native`` extension, built from ``native/``)
is an *optional* accelerator. When it is not importable — the default for a
plain ``pip install visiter`` — everything falls back to the pure-Python BFS,
so visiter always works without a toolchain.

The native path now handles the **full** ``build`` semantics, including the
bounded subset (``max_depth`` / ``max_nodes`` / ``time_limit`` / per-rule
``bound``): depth/bound truncation produces pseudo-edges, node/time limits
truncate with the same warnings (or raise under ``on_limit="raise"``). This
module assembles the resulting Graph dict so that it is byte-identical to the
pure-Python output for the deterministic limits. ``time_limit`` is best-effort:
it terminates and truncates, but the cut point is wall-clock dependent, so
byte-parity is not guaranteed (pure Python diverges the same way).
"""

import warnings

try:
    import visiter_native as _native
except ImportError:  # pragma: no cover - exercised by absence, not presence
    _native = None


def native_available():
    """True iff the native engine is importable."""
    return _native is not None


def supports(rules):
    """Whether the native path can run this build.

    The native engine reproduces the full build semantics, so the only
    requirement is that the extension is importable. ``rules`` is accepted for
    API symmetry (and to leave room for future per-rule opt-outs).
    """
    return _native is not None


def native_build(starts, rules, default, *, tags, key_type,
                 max_depth, max_nodes, time_limit, on_limit):
    """Run the BFS natively and assemble the Graph dict.

    Mirrors ``visiter.iteration.build``'s output for the deterministic limits
    (``max_depth`` / ``max_nodes`` / ``bound``) byte-for-byte; ``time_limit``
    is best-effort. ``starts`` is the normalized list of start values.
    """
    from .graph import Graph
    from .iteration import OpResult, _make_key_type_resolver

    conditions = [r.condition for r in rules]
    op_funcs = [r.op.func for r in rules]
    bounds = [r.bound for r in rules]
    exclusive = [bool(r.exclusive) for r in rules]
    default_func = default.func if default is not None else None

    time_limit_secs = None
    if time_limit is not None:
        h, m, s = map(int, time_limit.split(":"))
        time_limit_secs = float(h * 3600 + m * 60 + s)

    (values, depths, raw_edges, raw_pseudo,
     depth_limited, stop) = _native.build_raw(
        list(starts), conditions, op_funcs, bounds, exclusive,
        default_func, OpResult, max_depth, max_nodes, time_limit_secs)

    # Op registration: first-seen id wins, rules before default — mirrors the
    # pure-Python _register_op exactly, collision warning included, so the
    # native path stays behaviorally identical.
    op_order = []
    op_labels = {}
    seen = set()
    id_funcs = {}  # op.id → first func seen; used for collision check

    def register(op):
        if op.id not in seen:
            seen.add(op.id)
            op_order.append(op.id)
            op_labels[op.id] = op.label
            id_funcs[op.id] = op.func
            return
        # Same id twice — benign if the funcs are the same object or the
        # labels agree; otherwise warn about the silent merge.
        prior_func = id_funcs[op.id]
        prior_label = op_labels[op.id]
        if prior_func is op.func or prior_label == op.label:
            return
        warnings.warn(
            f"Op id collision on {op.id!r}: "
            f"two distinct callables produce the same id "
            f"(labels {prior_label!r} and {op.label!r}). "
            "Pass id=... on one of them to disambiguate, or "
            "accept the merge if this is intentional.",
            UserWarning,
            stacklevel=3,
        )

    for r in rules:
        register(r.op)
    if default is not None:
        register(default)

    # op index -> Op object (index n_rules is the default).
    ops_by_idx = [r.op for r in rules]

    def op_for(op_idx):
        return ops_by_idx[op_idx] if op_idx < len(rules) else default

    resolve_key_type = _make_key_type_resolver(key_type)
    tags = tags or {}

    nodes = {}
    for value, depth in zip(values, depths):
        info = {"depth": depth, "key_type": resolve_key_type(value)}
        node_tags = [name for name, fn in tags.items() if fn(value)]
        if node_tags:
            info["tags"] = node_tags
        nodes[str(value)] = info

    # Real edges dedup on (str(from), str(to), op.id) — the native side dedups
    # on (from_idx, to_idx, op_idx); re-dedup here so distinct rule indices
    # sharing one op.id collapse exactly like pure Python (which keys on op.id).
    edges = []
    seen_edges = set()
    for from_idx, to_idx, op_idx, label in raw_edges:
        op = op_for(op_idx)
        from_str = str(values[from_idx])
        to_str = str(values[to_idx])
        key = (from_str, to_str, op.id)
        if key not in seen_edges:
            edges.append({
                "from": from_str,
                "to": to_str,
                "op": op.id,
                "label": label if label is not None else op.label,
            })
            seen_edges.add(key)

    # Pseudo-edges carry the static op label and dedup on (str(from), op.id) —
    # the native side dedups on (from_idx, op_idx); re-dedup here so distinct
    # rule indices sharing one op.id collapse exactly like pure Python.
    pseudo_edges = []
    seen_pseudo = set()
    for from_idx, op_idx in raw_pseudo:
        op = op_for(op_idx)
        key = (str(values[from_idx]), op.id)
        if key not in seen_pseudo:
            pseudo_edges.append({
                "from": str(values[from_idx]),
                "op": op.id,
                "label": op.label,
            })
            seen_pseudo.add(key)

    graph = Graph({
        "schema_version": "1",
        "roots": list(starts),
        "nodes": nodes,
        "edges": edges,
        "pseudo_edges": pseudo_edges,
        "op_order": op_order,
        "op_labels": op_labels,
    })

    # Truncation signalling — mirror iteration.build exactly. A node/time stop
    # supersedes the depth warning (pure Python returns early on that stop,
    # before reaching the end-of-loop max_depth warning).
    if stop is not None:
        kind, context = stop
        reason = (f"max_nodes={max_nodes}" if kind == "max_nodes"
                  else f"time_limit={time_limit}")
        if on_limit == "raise":
            raise RuntimeError(f"{reason} reached {context}")
        warnings.warn(
            f"build: {reason} reached {context}; output is truncated. "
            f"Pass a higher limit or None to disable.",
            UserWarning,
            stacklevel=2,
        )
    elif depth_limited and on_limit != "raise":
        warnings.warn(
            f"build: max_depth={max_depth} reached; output is truncated. "
            f"Pass a higher max_depth or None to disable.",
            UserWarning,
            stacklevel=2,
        )

    return graph
