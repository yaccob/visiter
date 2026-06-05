"""Columnar storage (.vitgraph) round-trip tests.

Skipped entirely when pyarrow (the optional [storage] extra) is absent.
"""
import json
import os

import pytest

pytest.importorskip("pyarrow")

from visiter import Graph, viter  # noqa: E402


def _nim(**kw):
    return (viter(10, **kw)
            .case(lambda n: n >= 1, lambda n: n - 1, label="take 1")
            .case(lambda n: n >= 2, lambda n: n - 2, label="take 2")
            .case(lambda n: n >= 3, lambda n: n - 3, label="take 3")
            .build())


def _grid(side):
    return (viter([(0, 0)], max_depth=None, max_nodes=None)
            .case(lambda s: s[0] < side - 1, lambda s: (s[0] + 1, s[1]),
                  label="R")
            .case(lambda s: s[1] < side - 1, lambda s: (s[0], s[1] + 1),
                  label="U")
            .build())


def test_roundtrip_int_graph_exact(tmp_path):
    g = _nim(max_depth=None, max_nodes=None)
    p = tmp_path / "g.vitgraph"
    g.to_vitgraph(str(p))
    assert Graph.from_vitgraph(str(p)) == g


def test_roundtrip_tags_and_pseudo_edges(tmp_path):
    # max_depth=2 produces pseudo-edges at the frontier; tags mark multiples
    # of 4. Exercises tags + pseudo_edges round-trip in one graph.
    g = _nim(max_depth=2, tags={"hl": lambda n: n % 4 == 0})
    assert g["pseudo_edges"]  # sanity: this graph actually has pseudo-edges
    p = tmp_path / "g.vitgraph"
    g.to_vitgraph(str(p))
    assert Graph.from_vitgraph(str(p)) == g


def test_roundtrip_tuple_nodes_edges_exact(tmp_path):
    g = _grid(5)
    p = tmp_path / "g.vitgraph"
    g.to_vitgraph(str(p))
    back = Graph.from_vitgraph(str(p))
    # node keys (strings) and edges round-trip exactly; tuple `roots` come back
    # as lists — the same JSON-native lossiness json.dumps/json.loads has.
    assert back["nodes"] == g["nodes"]
    assert back["edges"] == g["edges"]
    assert back["op_order"] == g["op_order"]
    assert back["op_labels"] == g["op_labels"]


def test_to_arrow_shapes():
    g = _nim(max_depth=None, max_nodes=None)
    nodes, edges, pseudo = g.to_arrow()
    assert nodes.num_rows == len(g["nodes"])
    assert edges.num_rows == len(g["edges"])
    assert set(nodes.column_names) == {"key", "depth", "key_type", "tags"}
    assert set(edges.column_names) == {"src", "dst", "op", "label"}


def test_vitgraph_smaller_than_json(tmp_path):
    g = _grid(20)  # 400 nodes, ~760 edges
    p = tmp_path / "g.vitgraph"
    g.to_vitgraph(str(p))
    json_size = len(json.dumps(g, default=str).encode())
    assert os.path.getsize(str(p)) < json_size
