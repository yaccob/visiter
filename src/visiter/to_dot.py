"""Convert iteration graphs into Graphviz Digraph objects (DOT)."""

import warnings

from .render_helpers import (build_dot, check_deadline, format_op_label,
                             parse_time_limit, resolve_op_colors,
                             _PALETTE_FALLBACK, _node_id)


def _bfs_neighborhood(graph, anchor, radius, direction):
    """Return the set of node ids within `radius` BFS hops of `anchor`.

    direction:
        "forward"  — follow edges in their native direction (src → dst)
        "backward" — follow edges in reverse (dst → src)
        "both"     — undirected (treat each edge as bidirectional)
    """
    anchor = str(anchor)
    if anchor not in graph["nodes"]:
        raise ValueError(f"anchor {anchor!r} is not a node in the graph")
    if direction not in ("forward", "backward", "both"):
        raise ValueError(f"direction must be 'forward', 'backward', or 'both'; "
                         f"got {direction!r}")

    neighbors = {v: [] for v in graph["nodes"]}
    for edge in graph["edges"]:
        src, dst = str(edge["from"]), str(edge["to"])
        if direction in ("forward", "both"):
            neighbors[src].append(dst)
        if direction in ("backward", "both"):
            neighbors[dst].append(src)

    distance = {anchor: 0}
    frontier = [anchor]
    while frontier:
        nxt = []
        for v in frontier:
            if distance[v] >= radius:
                continue
            for n in neighbors.get(v, []):
                if n not in distance:
                    distance[n] = distance[v] + 1
                    nxt.append(n)
        frontier = nxt
    return set(distance)


def to_dot(graph, *, op_labels=None,
                 anchor=None, radius=None, direction="forward",
                 value_range=None,
                 op_colors=None, palette=None,
                 show_binary=False, show_ternary=False, show_factors=False,
                 node_label_attr=None,
                 time_limit=None, on_limit="raise"):
    """Render a graph dict (from `iterate`) as a Graphviz Digraph.

    Args:
        graph: dict with "roots", "nodes", "edges".
        op_labels: optional {op: display_label} map. Ops not in the map fall
            back to the generic `format_op_label` (e.g. "/2" → "÷2").
        anchor, radius, direction: if `anchor` and `radius` are given, only
            nodes within `radius` BFS hops of `anchor` are rendered.
            `direction` selects how edges are followed during BFS:
              "forward"  — along edges (src → dst); default. Matches
                           the "show me the orbit from x" reading that
                           aligns with the iteration's own direction.
              "backward" — against edges. Matches the "show me what
                           reaches this anchor" reading (natural when
                           anchoring on a sink or fixed point).
              "both"     — undirected neighborhood.
            `anchor` is a node value as it appears in graph["nodes"] keys.
        value_range: optional (low, high) int tuple; only nodes with integer
            value in [low, high] are rendered. Combines with anchor/radius
            by intersection.
        op_colors: optional {op: color or (fill, edge)} — pins operation
            colors. See resolve_op_colors.
        palette: optional color sequence used for ops not in `op_colors`.
        show_binary / show_ternary / show_factors: extra node annotations.
            show_ternary groups digits in 3-trit blocks (base-2 nibbles →
            base-16; base-3 trits → base-27).
        node_label_attr: optional name of a per-node attribute whose value
            should be rendered as the node's display label instead of the
            node key. Falls back to the node key when the attribute is
            absent. List/tuple/set values are formatted as `{a, b, c}`
            (no repr quotes); scalars use their plain `str()` form.
            Useful for showing e.g. `nx.condensation`'s `members` list
            in the SVG rather than NetworkX's opaque SCC indices.
        time_limit: optional "hh:mm:ss" wall-clock bound on the build phase
            (BFS cropping, build_dot loops, ghost-edge loop). Independent
            from any subprocess-level Graphviz layout timeout the caller
            may apply.
        on_limit: "raise" (default) → RuntimeError when time_limit hits;
            "stop" → return the partially-built dot.

    Edges whose source falls outside the rendered set but whose target stays
    get a dashed "ghost" stub as a visual cue that the graph continues.

    Returns:
        graphviz.Digraph
    """
    deadline = parse_time_limit(time_limit)

    # Effective display label per op identity. Priority: user override
    # (via to_dot's op_labels= kwarg) > graph["op_labels"] (set by
    # iterate from each Op's label) > format_op_label(identity) as a
    # last-resort cosmetic transform for legacy string-style ops.
    user_labels = op_labels or {}
    graph_labels = graph.get("op_labels", {})
    effective_labels = {
        edge["op"]: user_labels.get(
            edge["op"],
            graph_labels.get(edge["op"], format_op_label(edge["op"])))
        for edge in graph["edges"]
    }
    for pe in graph.get("pseudo_edges", []):
        effective_labels.setdefault(
            pe["op"],
            user_labels.get(
                pe["op"],
                graph_labels.get(pe["op"], format_op_label(pe["op"]))))

    keep = None
    if anchor is not None or radius is not None:
        if anchor is None or radius is None:
            raise ValueError("anchor and radius must both be given, or neither")
        keep = _bfs_neighborhood(graph, anchor, radius, direction)
    if value_range is not None:
        lo, hi = value_range
        all_int = all(info["key_type"] == "integer"
                      for info in graph["nodes"].values())
        if all_int:
            range_set = {v for v in graph["nodes"] if lo <= int(v) <= hi}
            keep = range_set if keep is None else keep & range_set
        else:
            warnings.warn(
                "value_range ignored for graphs with non-integer node keys",
                UserWarning, stacklevel=2)

    # Each entry: (kept_node_id, op_label, kept_is_src)
    #   kept_is_src=True  → outgoing cut (or pseudo-edge): kept_src → ghost
    #   kept_is_src=False → incoming cut: ghost → kept_dst
    cut_edges = []
    if keep is not None:
        for edge in graph["edges"]:
            src = str(edge["from"])
            dst = str(edge["to"])
            if src in keep and dst not in keep:
                cut_edges.append((src, edge["op"], True))
            elif dst in keep and src not in keep:
                cut_edges.append((dst, edge["op"], False))
        graph = {
            "roots": graph.get("roots", []),
            "nodes": {v: info for v, info in graph["nodes"].items() if v in keep},
            "edges": [e for e in graph["edges"]
                      if str(e["from"]) in keep and str(e["to"]) in keep],
            "pseudo_edges": [pe for pe in graph.get("pseudo_edges", [])
                             if str(pe["from"]) in keep],
            "op_order": graph.get("op_order", []),
            "op_labels": graph.get("op_labels", {}),
        }

    # Pseudo-edges (from iterate's bound=False outcomes) become outgoing
    # ghost stubs, sharing the cut_edges_out machinery.
    for pe in graph.get("pseudo_edges", []):
        cut_edges.append((str(pe["from"]), pe["op"], True))

    # Outgoing cuts contribute to the kept node's fill (incoming cuts don't —
    # fill is derived from outgoing edges only).
    extra_out_ops = {}
    for kept, op, kept_is_src in cut_edges:
        if kept_is_src:
            extra_out_ops.setdefault(kept, set()).add(op)

    resolved = resolve_op_colors(graph, op_colors=op_colors, palette=palette)
    dot = build_dot(graph, effective_labels,
                    show_binary=show_binary, show_ternary=show_ternary,
                    show_factors=show_factors,
                    op_colors=op_colors, palette=palette,
                    extra_out_ops=extra_out_ops,
                    resolved=resolved,
                    node_label_attr=node_label_attr,
                    deadline=deadline, on_limit=on_limit)

    for i, (kept, op, kept_is_src) in enumerate(cut_edges):
        if check_deadline(deadline, on_limit, dot, "in ghost-edge loop") is dot:
            return dot
        direction_tag = "out" if kept_is_src else "in"
        ghost_id = f"ghost_{direction_tag}_{kept}_{i}"
        edge_label = effective_labels.get(op, op)
        color = resolved.get(op, (_PALETTE_FALLBACK, _PALETTE_FALLBACK))[1]
        dot.node(ghost_id, label="", shape="none", width="0", height="0")
        kept_id = _node_id(kept)
        endpoints = (kept_id, ghost_id) if kept_is_src else (ghost_id, kept_id)
        dot.edge(*endpoints, label=f" {edge_label} ", style="dashed",
                 color=color, fontcolor=color, arrowhead="normal")

    return dot
