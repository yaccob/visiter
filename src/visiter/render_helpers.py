"""Shared helpers for Graphviz-based graph rendering."""

import re
import time
import warnings

from sympy import factorint

_SUP_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _is_int_str(s):
    return bool(re.fullmatch(r"-?(0|[1-9][0-9]*)", s))


def _format_label_value(v):
    """Turn a node-attribute value into a human-readable display string.

    Lists and tuples — the common case for collection-shaped attributes
    like `nx.condensation`'s `members` — are formatted as `{a, b, c}`,
    using `str()` on each element (no `repr`, so no stray quotes around
    string elements). Sets and frozensets are sorted for determinism.
    Scalars and other types fall back to `str()`.
    """
    if isinstance(v, (set, frozenset)):
        items = sorted(v, key=lambda x: (isinstance(x, str), x))
        return "{" + ", ".join(str(x) for x in items) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(str(x) for x in v) + "}"
    return str(v)


def _node_id(vstr):
    """Stable Graphviz node id derived from a string node key.

    Integer-valued keys keep the historical `n<N>` form. Non-integer keys
    get a hex-encoded `nx_<hex>` form: deterministic, collision-free, and a
    valid Graphviz identifier without quoting.
    """
    if _is_int_str(vstr):
        return f"n{vstr}"
    return "nx_" + vstr.encode("utf-8").hex()


def parse_time_limit(time_limit):
    """Convert "hh:mm:ss" string to a Unix-time deadline; None passes through."""
    if time_limit is None:
        return None
    h, m, s = map(int, time_limit.split(":"))
    return time.time() + h * 3600 + m * 60 + s


def check_deadline(deadline, on_limit, partial_value, where):
    """Honor a deadline either by raising or by returning `partial_value`.

    Returns `partial_value` when on_limit="stop" and the deadline has
    passed, so callers can `return check_deadline(...) or normal_path`.
    Returns None when the deadline has not yet passed (caller continues).
    """
    if deadline is None or time.time() < deadline:
        return None
    if on_limit == "raise":
        raise RuntimeError(f"render time_limit reached {where}")
    return partial_value

# Fallback palette. Each slot is (fill_color, edge_color): a light pastel for
# node fills (readable labels) and a more saturated variant for edges (thin
# lines that need visibility). The first six slots are the legacy palette
# (blue, orange, green, purple, olive, teal) so existing graphs keep their
# familiar look. Slots 7–12 fill the hue gaps for use cases with many ops
# (e.g. Tic-Tac-Toe's 9 move positions).
DEFAULT_OP_PALETTE = [
    ("#ccddff", "#6688bb"),  # blue
    ("#ffddcc", "#ddbb99"),  # orange
    ("#cceecc", "#77aa77"),  # green
    ("#eeccee", "#aa77aa"),  # purple
    ("#eeeeaa", "#aaaa66"),  # olive
    ("#cceeee", "#77aaaa"),  # teal
    ("#edcfcf", "#b96e6e"),  # red
    ("#ece1c6", "#bfa669"),  # gold
    ("#d9e8c9", "#94b474"),  # lime
    ("#d1e4eb", "#74a4b4"),  # cyan
    ("#cfc9e8", "#7e74b4"),  # indigo
    ("#ebd1de", "#b47494"),  # pink
]
_PALETTE_FALLBACK = "#888888"


def darken(hex_color, factor=0.45):
    """Reduce HSL lightness by `factor`, keeping hue and saturation.

    HSL-based darkening preserves the color identity: a light blue stays
    blue when darkened, instead of going grey as it would with a uniform
    RGB scale toward black.
    """
    import colorsys

    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(hue, light * factor, sat)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def _as_pair(c):
    """Normalize a palette entry to a (fill, edge) tuple."""
    if isinstance(c, str):
        return (c, c)
    fill, edge = c
    return (fill, edge)


def resolve_op_colors(graph, op_colors=None, palette=None):
    """Return {op_label: (fill_color, edge_color)}.

    Entries in `op_colors` may be either a single hex string (used for both
    fill and edge) or a (fill, edge) tuple. Palette entries follow the same
    string/tuple rule. Assignment order for unmapped ops:
      - `graph["op_order"]` if present (rule-declaration order, set by build)
      - otherwise first-seen order over `graph["edges"]`
    When the palette is exhausted a neutral grey pair is used.
    """
    result = {op: _as_pair(c) for op, c in (op_colors or {}).items()}
    palette_list = [_as_pair(p) for p in
                    (palette if palette is not None else DEFAULT_OP_PALETTE)]
    palette_iter = iter(palette_list)

    ordered_ops = graph.get("op_order")
    if ordered_ops is None:
        ordered_ops = []
        seen = set()
        for edge in graph["edges"]:
            op = edge["op"]
            if op not in seen:
                seen.add(op)
                ordered_ops.append(op)

    for op in ordered_ops:
        if op in result:
            continue
        try:
            result[op] = next(palette_iter)
        except StopIteration:
            result[op] = (_PALETTE_FALLBACK, _PALETTE_FALLBACK)
    return result


def format_prime_factors(n):
    """Return n's prime factorization as a string like '2²·3·5'."""
    if n < 2:
        return str(n)
    parts = []
    for prime, exp in sorted(factorint(n).items()):
        if exp == 1:
            parts.append(str(prime))
        else:
            parts.append(f"{prime}{str(exp).translate(_SUP_DIGITS)}")
    return "·".join(parts)


def format_binary(v):
    """Return v's binary representation grouped in 4-bit nibbles."""
    b = bin(v)[2:] if v > 0 else "0"
    chunks = []
    while len(b) > 4:
        chunks.append(b[-4:])
        b = b[:-4]
    chunks.append(b)
    return "\u2009".join(reversed(chunks))


def format_op_label(op):
    """Format an operation string for display with Unicode operators."""
    m = re.match(r'^/(\d+)$', op)
    if m:
        return f'÷{m.group(1)}'
    m = re.match(r'^\*(\d+)$', op)
    if m:
        return f'×{m.group(1)}'
    m = re.match(r'^\*(\d+)\+(\d+)$', op)
    if m:
        return f'×{m.group(1)} + {m.group(2)}'
    m = re.match(r'^\*(\d+)-(\d+)$', op)
    if m:
        return f'×{m.group(1)} − {m.group(2)}'
    return op


def _label_attrs(vstr, display, is_int_key,
                 show_binary, show_factors):
    extras = []
    int_v = int(vstr) if is_int_key else None
    if show_binary and int_v is not None:
        extras.append(format_binary(int_v))
    if show_factors and int_v is not None:
        extras.append(format_prime_factors(int_v))
    if extras:
        body = "<BR/>".join(f'<FONT POINT-SIZE="8">{e}</FONT>' for e in extras)
        return {"label": f"<{display}<BR/>{body}>"}
    return {"label": display}


def node_attrs(vstr, out_op_colors, hl=False, show_binary=False,
               show_factors=False, display=None, is_int_key=False):
    """Build Graphviz node attributes from a node key and its outgoing edges.

    Fill is driven by the node's outgoing edges:
      0 out-edges: no fill (leaf, default Graphviz white)
      1 out-edge:  solid fill in that edge's color
      N out-edges: wedged (pie slices) in the edges' colors, sorted by op-label

    `highlight` darkens each fill color and switches the font to white.

    Int-only annotations (`show_binary`, `show_factors`) are silently
    skipped when `vstr` is not an integer-valued key; the caller
    (build_dot) emits a single aggregate warning rather than one per node.
    """
    attrs = _label_attrs(vstr, display if display is not None else vstr,
                         is_int_key,
                         show_binary, show_factors)
    colors = [darken(c) for c in out_op_colors] if hl else list(out_op_colors)
    if len(colors) == 1:
        attrs.update(style="filled", fillcolor=colors[0])
    elif len(colors) >= 2:
        attrs.update(style="wedged", fillcolor=":".join(colors))
    if hl and colors:
        attrs["fontcolor"] = "white"
    return attrs


def build_dot(graph,
              show_binary=False, show_factors=False,
              op_colors=None, palette=None, extra_out_ops=None,
              resolved=None,
              deadline=None, on_limit="stop",
              node_label=None, node_label_attr=None):
    """Build a Graphviz Digraph from a graph dict.

    Edges are colored by operation identity via `resolve_op_colors` and
    labeled directly from each ``edge["label"]`` field — no
    ``op_labels`` lookup. Nodes are filled from their outgoing edges
    (wedged for branches).

    `extra_out_ops` is an optional {node_id: set[op_id]} map of
    additional outgoing op ids per node — used by callers that crop the
    graph but still want the kept nodes' fill to reflect ops on edges that
    leave the kept region (otherwise those nodes would appear unfilled).

    `resolved` is an optional pre-computed op → (fill, edge) mapping. When
    omitted, `build_dot` computes it via `resolve_op_colors(graph,
    op_colors, palette)` itself; callers that need the same mapping before
    (e.g. to derive ghost-edge colors) can compute it once and pass it in
    to avoid the redundant pass.

    `deadline` (Unix timestamp from `parse_time_limit`) bounds wall-clock
    time spent in the build loops; on hit, behavior follows `on_limit`
    ("stop" → return the partially-built dot [default], "raise" →
    RuntimeError).
    """
    import graphviz

    dot = graphviz.Digraph(format='svg')
    dot.attr(rankdir='TB')
    dot.attr('node', shape='ellipse', fontsize='11')
    dot.attr('edge', fontsize='9')

    roots = {str(r) for r in graph.get("roots", [])}
    if resolved is None:
        resolved = resolve_op_colors(graph, op_colors=op_colors, palette=palette)

    out_ops = {}
    for edge in graph["edges"]:
        out_ops.setdefault(str(edge["from"]), set()).add(edge["op"])
    for src, ops in (extra_out_ops or {}).items():
        out_ops.setdefault(src, set()).update(ops)

    fallback = (_PALETTE_FALLBACK, _PALETTE_FALLBACK)

    # Warn once if int-only annotations were requested but the graph
    # contains non-integer node keys; per-node logic silently skips.
    has_non_int = any(info["key_type"] != "integer"
                      for info in graph["nodes"].values())
    for flag_name, flag in (("show_binary", show_binary),
                            ("show_factors", show_factors)):
        if flag and has_non_int:
            warnings.warn(
                f"{flag_name}=True ignored for non-integer node keys",
                UserWarning, stacklevel=2)

    # Sort: all-int graphs numerically, otherwise lexicographically
    # for deterministic ordering.
    all_int = all(info["key_type"] == "integer"
                  for info in graph["nodes"].values())
    if all_int:
        sorted_nodes = sorted(graph["nodes"].items(),
                              key=lambda kv: int(kv[0]))
    else:
        sorted_nodes = sorted(graph["nodes"].items(), key=lambda kv: kv[0])

    # Order a node's outgoing-op wedges by rule-declaration order (op_order),
    # not by the op id string. The id is the callback's source form — a Python
    # lambda body in the pure-Python path, the inline expression in lang="rust"
    # — so sorting by it makes the wedge order (and thus the rendered fills)
    # depend on the callback *spelling*, diverging between the two engines for
    # an otherwise-identical graph. Declaration order is engine-independent and
    # already drives op colors, so wedges and colors now agree.
    op_rank = {op: i for i, op in enumerate(graph.get("op_order", []))}

    for vstr, info in sorted_nodes:
        if check_deadline(deadline, on_limit, dot, "in build_dot node loop") is dot:
            return dot
        node_id = _node_id(vstr)
        hl = "highlight" in info.get("tags", [])
        ops = sorted(out_ops.get(vstr, set()),
                     key=lambda o: (op_rank.get(o, len(op_rank)), o))
        fill_colors = [resolved.get(op, fallback)[0] for op in ops]
        display = None
        if node_label is not None:
            result = node_label(vstr, info)
            if result is not None:
                display = result
        if display is None and node_label_attr is not None and node_label_attr in info:
            display = _format_label_value(info[node_label_attr])
        is_int_key = info["key_type"] == "integer"
        attrs = node_attrs(vstr, fill_colors, hl=hl,
                           show_binary=show_binary,
                           show_factors=show_factors, display=display,
                           is_int_key=is_int_key)
        if vstr in roots:
            attrs["penwidth"] = "3"
        dot.node(node_id, **attrs)

    sorted_edges = sorted(
        graph["edges"], key=lambda e: (str(e["from"]), str(e["to"])))
    for edge in sorted_edges:
        if check_deadline(deadline, on_limit, dot, "in build_dot edge loop") is dot:
            return dot
        src = _node_id(str(edge["from"]))
        dst = _node_id(str(edge["to"]))
        color = resolved.get(edge["op"], fallback)[1]
        dot.edge(src, dst, label=f" {edge['label']} ",
                 color=color, fontcolor=color)

    return dot
