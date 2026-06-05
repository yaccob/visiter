"""Columnar storage for visiter graphs (Arrow IPC / Feather + zstd).

A viter Graph is naturally two tables — nodes and edges — plus a little
metadata (roots, op order/labels). This module stores it as a single
self-contained ``.vitgraph`` file: a zip container holding ``meta.json`` and
zstd-compressed Arrow IPC buffers for the nodes, edges and pseudo-edges tables.

The size win over JSON comes from interning node keys to int32 ids (so edges
carry ints, not repeated string keys) plus dictionary-encoding the categorical
columns (``op``, ``label``, ``key_type``). Measured ~10-26x smaller than JSON
with much faster load and columnar analytics.

``pyarrow`` is an optional dependency (the ``[storage]`` extra). It is imported
lazily so the rest of visiter works without it.

Round-trip fidelity matches JSON: node keys are ``str(value)`` (the original
Python objects are not reconstructed), so ``from_vitgraph(to_vitgraph(g))``
equals ``g`` for graphs whose ``roots`` are JSON-native (ints, strings); tuple
roots come back as lists, exactly as a JSON round-trip would yield.
"""
import io
import json
import zipfile


def _require_pyarrow():
    try:
        import pyarrow as pa  # noqa: F401
        import pyarrow.ipc  # noqa: F401
        return pa
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Columnar storage needs pyarrow. Install the optional extra: "
            "pip install 'visiter[storage]'."
        ) from exc


def to_arrow(graph):
    """Return ``(nodes, edges, pseudo_edges)`` as pyarrow Tables.

    Edges/pseudo-edges reference nodes by their int32 row index in the nodes
    table (node keys are interned), and the categorical columns are
    dictionary-encoded. This is the low-level columnar view for analytics.
    """
    pa = _require_pyarrow()
    keys = list(graph["nodes"].keys())
    id_of = {k: i for i, k in enumerate(keys)}

    nodes = pa.table({
        "key": pa.array(keys, pa.string()),
        "depth": pa.array([graph["nodes"][k]["depth"] for k in keys],
                          pa.int32()),
        "key_type": pa.array([graph["nodes"][k]["key_type"] for k in keys],
                             pa.string()).dictionary_encode(),
        "tags": pa.array([graph["nodes"][k].get("tags", []) for k in keys],
                         pa.list_(pa.string())),
    })

    edge_list = graph["edges"]
    edges = pa.table({
        "src": pa.array([id_of[e["from"]] for e in edge_list], pa.int32()),
        "dst": pa.array([id_of[e["to"]] for e in edge_list], pa.int32()),
        "op": pa.array([e["op"] for e in edge_list],
                       pa.string()).dictionary_encode(),
        "label": pa.array([e["label"] for e in edge_list],
                          pa.string()).dictionary_encode(),
    })

    pseudo_list = graph.get("pseudo_edges", [])
    pseudo = pa.table({
        "src": pa.array([id_of[e["from"]] for e in pseudo_list], pa.int32()),
        "op": pa.array([e["op"] for e in pseudo_list],
                       pa.string()).dictionary_encode(),
        "label": pa.array([e["label"] for e in pseudo_list],
                          pa.string()).dictionary_encode(),
    })
    return nodes, edges, pseudo


def _ipc_bytes(pa, table, compression):
    sink = pa.BufferOutputStream()
    opts = pa.ipc.IpcWriteOptions(compression=compression)
    with pa.ipc.new_file(sink, table.schema, options=opts) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


def _read_ipc(pa, data):
    return pa.ipc.open_file(pa.BufferReader(data)).read_all()


def to_vitgraph(graph, path, *, compression="zstd"):
    """Write *graph* to a single ``.vitgraph`` file (Arrow IPC + zstd in a zip).

    Returns *graph* for chaining.
    """
    pa = _require_pyarrow()
    nodes, edges, pseudo = to_arrow(graph)
    meta = {
        "schema_version": graph.get("schema_version", "1"),
        "roots": graph.get("roots", []),
        "op_order": graph.get("op_order", []),
        "op_labels": graph.get("op_labels", {}),
    }
    # Arrow buffers are already zstd-compressed; store them in the zip uncompressed.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("meta.json", json.dumps(meta, default=str))
        z.writestr("nodes.arrow", _ipc_bytes(pa, nodes, compression))
        z.writestr("edges.arrow", _ipc_bytes(pa, edges, compression))
        z.writestr("pseudo.arrow", _ipc_bytes(pa, pseudo, compression))
    return graph


def from_vitgraph(path):
    """Read a ``.vitgraph`` file back into a Graph dict."""
    from .graph import Graph
    pa = _require_pyarrow()
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("meta.json"))
        nodes = _read_ipc(pa, z.read("nodes.arrow"))
        edges = _read_ipc(pa, z.read("edges.arrow"))
        pseudo = _read_ipc(pa, z.read("pseudo.arrow"))

    keys = nodes.column("key").to_pylist()
    depths = nodes.column("depth").to_pylist()
    ktypes = nodes.column("key_type").to_pylist()
    tags = nodes.column("tags").to_pylist()
    node_map = {}
    for key, depth, ktype, tag in zip(keys, depths, ktypes, tags):
        info = {"depth": depth, "key_type": ktype}
        if tag:
            info["tags"] = tag
        node_map[key] = info

    src = edges.column("src").to_pylist()
    dst = edges.column("dst").to_pylist()
    ops = edges.column("op").to_pylist()
    labels = edges.column("label").to_pylist()
    edge_list = [{"from": keys[s], "to": keys[d], "op": o, "label": lb}
                 for s, d, o, lb in zip(src, dst, ops, labels)]

    psrc = pseudo.column("src").to_pylist()
    pops = pseudo.column("op").to_pylist()
    plabels = pseudo.column("label").to_pylist()
    pseudo_list = [{"from": keys[s], "op": o, "label": lb}
                   for s, o, lb in zip(psrc, pops, plabels)]

    return Graph({
        "schema_version": meta["schema_version"],
        "roots": meta["roots"],
        "nodes": node_map,
        "edges": edge_list,
        "pseudo_edges": pseudo_list,
        "op_order": meta["op_order"],
        "op_labels": meta["op_labels"],
    })
