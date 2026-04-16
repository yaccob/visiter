"""Bridge between VisIter graph dicts and NetworkX DiGraphs.

VisIter handles the *building* of iteration graphs (via `iterate`) and
the *rendering* (via `to_dot`). For everything in between — graph
analysis, algorithms, metrics — NetworkX is the mature answer. This
module provides a two-way translation so you can pipe a VisIter graph
into NetworkX, run any of its hundreds of algorithms, and optionally
pipe the result back into `to_dot` for visualization.

The mapping is deliberately thin and information-preserving:

    node key (str in VisIter dict)   ↔   node id (any, typically str) in nx.DiGraph
    every key in node dict           ↔   named node attribute on nx.DiGraph
    edge["op"]                       ↔   edge attribute "op"
    "roots", "pseudo_edges",         ↔   graph-level attributes on
      "op_order", "schema_version"       nx.DiGraph.graph

All node attributes pass through in both directions, not just the
schema-defined `depth` and `tags` — this is what lets NetworkX
algorithms that annotate nodes (e.g. `nx.condensation` stashing the
SCC members as `members`) survive the round-trip into a renderable
graph dict. Non-JSON-serialisable attributes coming back from NX
(typically `frozenset`, `set`) are coerced: frozensets/sets become
sorted lists so the output stays JSON-friendly.

Round-trip (`from_networkx(to_networkx(g))`) is expected to preserve
the graph dict exactly. Going the other way (`to_networkx(from_networkx(h))`)
is only lossless when `h` already carries VisIter's conventions.

Requires the `[analytics]` extra:

    pip install visiter[analytics]
"""

try:
    import networkx as nx
except ImportError as _exc:  # pragma: no cover - surfaced as ImportError
    raise ImportError(
        "visiter.analytics requires the 'networkx' package. "
        "Install with: pip install visiter[analytics]"
    ) from _exc

from .iteration import json_type


def _coerce_json_friendly(value):
    """Turn NX-typical non-JSON types into JSON-serialisable ones.

    - ``frozenset`` / ``set`` → sorted list (deterministic output).
    - Nested ``dict`` / ``list`` / ``tuple`` → recurse so inner
      frozensets also get flattened.
    - Everything else is returned as-is; non-JSON exotica fall back
      to ``str`` when serialised by ``json.dump(default=str)``.
    """
    if isinstance(value, (set, frozenset)):
        return sorted(_coerce_json_friendly(v) for v in value)
    if isinstance(value, dict):
        return {k: _coerce_json_friendly(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce_json_friendly(v) for v in value]
    return value


def to_networkx(graph):
    """Convert a VisIter graph dict to a ``networkx.DiGraph``.

    The NetworkX node ids are the same strings that keyed ``graph["nodes"]``
    — this is the only stable identity the graph dict guarantees. Edge
    endpoints in the input are coerced to their ``str`` form so they
    match up. Every key of each node entry becomes a NetworkX node
    attribute, not just the schema-defined ``depth`` and ``tags``.
    Edge metadata (``op``) becomes an edge attribute. Top-level fields
    (``roots``, ``pseudo_edges``, ``op_order``, ``schema_version``)
    are stashed on ``nx.DiGraph.graph`` so a subsequent ``from_networkx``
    can reproduce the original dict.
    """
    g = nx.DiGraph()
    g.graph["schema_version"] = graph.get("schema_version", "1")
    g.graph["roots"] = list(graph.get("roots", []))
    g.graph["pseudo_edges"] = list(graph.get("pseudo_edges", []))
    g.graph["op_order"] = list(graph.get("op_order", []))

    for key, info in graph.get("nodes", {}).items():
        # Pass through every node attribute, not only the well-known
        # `depth` and `tags` ones. Defensive list() copy for tags.
        attrs = dict(info)
        if "tags" in attrs:
            attrs["tags"] = list(attrs["tags"])
        g.add_node(key, **attrs)

    for edge in graph.get("edges", []):
        # Preserve the raw endpoint values so from_networkx can round-
        # trip integer endpoints back to integers (node ids themselves
        # must be strings to align with the graph dict's str(value)
        # keying).
        g.add_edge(
            str(edge["from"]), str(edge["to"]),
            op=edge["op"],
            _raw_from=edge["from"], _raw_to=edge["to"],
        )

    return g


def from_networkx(g):
    """Convert a ``networkx.DiGraph`` back into a VisIter graph dict.

    Every NetworkX node attribute passes through to the node's dict
    entry, not only the schema-defined ``depth`` and ``tags``. Missing
    ``depth`` defaults to 0 so the output still validates against the
    schema (minimum: depth is required). Edge attribute ``op`` is
    read; missing ``op`` defaults to ``""`` and is added to
    ``op_order``. Graph-level attributes on ``g.graph`` (``roots``,
    ``pseudo_edges``, ``op_order``, ``schema_version``) are read if
    present; otherwise sensible defaults are used.

    Non-JSON-serialisable attribute values that NX algorithms often
    produce are coerced into JSON-friendly ones: ``frozenset`` / ``set``
    become sorted lists. Other exotic types are left as-is and will
    fall back to ``str`` when the dict is serialised by the CLI's
    ``json.dump(..., default=str)``.

    The output is intended to flow straight into ``to_dot``; for
    arbitrary NetworkX graphs without VisIter metadata you'll get a
    minimal, still-valid graph dict.
    """
    nodes = {}
    for n, attrs in g.nodes(data=True):
        entry = {}
        for k, v in attrs.items():
            entry[k] = _coerce_json_friendly(v)
        # Schema requires depth; supply a neutral default when the NX
        # graph doesn't carry one (typical for bare, non-visiter inputs).
        if "depth" not in entry:
            entry["depth"] = 0
        # Schema requires key_type. Prefer a preserved attribute; fall
        # back to inferring it from the JSON type of the NX node id —
        # that's the only honest signal we have for bare NX graphs.
        if "key_type" not in entry:
            entry["key_type"] = json_type(n)
        if "tags" in entry and not isinstance(entry["tags"], list):
            entry["tags"] = list(entry["tags"])
        nodes[str(n)] = entry

    edges = []
    seen_ops = list(g.graph.get("op_order", []))
    seen_ops_set = set(seen_ops)
    for u, v, attrs in g.edges(data=True):
        op = attrs.get("op", "")
        # Restore original endpoint types if they were stashed by
        # to_networkx. Otherwise the nx node ids (strings) are the
        # honest fallback.
        frm = attrs["_raw_from"] if "_raw_from" in attrs else str(u)
        to_ = attrs["_raw_to"] if "_raw_to" in attrs else str(v)
        edges.append({"from": frm, "to": to_, "op": op})
        if op not in seen_ops_set:
            seen_ops_set.add(op)
            seen_ops.append(op)

    return {
        "schema_version": g.graph.get("schema_version", "1"),
        "roots": list(g.graph.get("roots", [])),
        "nodes": nodes,
        "edges": edges,
        "pseudo_edges": list(g.graph.get("pseudo_edges", [])),
        "op_order": seen_ops,
    }
