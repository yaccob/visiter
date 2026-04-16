"""Tests for the NetworkX bridge in src/visiter/analytics.py."""

import json

import pytest

from visiter import Op, Rule, iterate

pytest.importorskip("networkx")
import networkx as nx  # noqa: E402

from visiter.analytics import to_networkx, from_networkx  # noqa: E402


def sample_graph():
    return iterate(
        start=range(1, 10),
        rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
        default=Op(lambda x: x + 2, "+2"),
    )


# ---- to_networkx ------------------------------------------------------------

def test_to_networkx_produces_digraph():
    g = to_networkx(sample_graph())
    assert isinstance(g, nx.DiGraph)


def test_to_networkx_preserves_node_set():
    vg = sample_graph()
    g = to_networkx(vg)
    # NetworkX node ids == our string keys.
    assert set(g.nodes) == set(vg["nodes"])


def test_to_networkx_preserves_edge_set():
    vg = sample_graph()
    g = to_networkx(vg)
    expected = {(str(e["from"]), str(e["to"])) for e in vg["edges"]}
    assert set(g.edges) == expected


def test_to_networkx_preserves_node_attributes():
    vg = sample_graph()
    g = to_networkx(vg)
    for key, info in vg["nodes"].items():
        assert g.nodes[key]["depth"] == info["depth"]
        if "tags" in info:
            assert g.nodes[key]["tags"] == info["tags"]


def test_to_networkx_preserves_edge_op_attribute():
    vg = sample_graph()
    g = to_networkx(vg)
    for edge in vg["edges"]:
        assert g.edges[str(edge["from"]), str(edge["to"])]["op"] == edge["op"]


def test_to_networkx_preserves_graph_level_fields_in_graph_attr():
    vg = sample_graph()
    g = to_networkx(vg)
    assert g.graph["op_order"] == vg["op_order"]
    assert g.graph["roots"] == vg["roots"]
    assert g.graph["pseudo_edges"] == vg["pseudo_edges"]
    assert g.graph.get("schema_version") == vg.get("schema_version")


# ---- from_networkx ---------------------------------------------------------

def test_roundtrip_preserves_shape():
    # A VisIter graph, exported to nx and back, is structurally equal.
    vg = sample_graph()
    assert from_networkx(to_networkx(vg)) == vg


def test_from_networkx_of_bare_graph_works():
    # A plain nx.DiGraph without visiter metadata should still produce
    # a valid (but minimal) visiter graph dict.
    g = nx.DiGraph()
    g.add_node("a", depth=0)
    g.add_node("b", depth=1)
    g.add_edge("a", "b", op="step")

    out = from_networkx(g)
    assert out["nodes"] == {"a": {"depth": 0}, "b": {"depth": 1}}
    assert out["edges"] == [{"from": "a", "to": "b", "op": "step"}]
    assert out["pseudo_edges"] == []
    # roots default to empty when not provided.
    assert out["roots"] == []


def test_from_networkx_output_validates_against_schema():
    jsonschema = pytest.importorskip("jsonschema")
    from importlib.resources import files
    schema = json.loads(files("visiter").joinpath(
        "schemas/v1/graph.schema.json").read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema)

    vg = sample_graph()
    out = from_networkx(to_networkx(vg))
    errors = list(v.iter_errors(out))
    assert not errors, errors


def test_from_networkx_result_renders_via_to_dot():
    from visiter import to_dot
    vg = sample_graph()
    nxg = to_networkx(vg)
    round_tripped = from_networkx(nxg)
    src = to_dot(round_tripped).source
    assert "digraph" in src


# ---- attribute pass-through -------------------------------------------------

def test_from_networkx_preserves_arbitrary_node_attributes():
    g = nx.DiGraph()
    g.add_node("0", depth=0, members=frozenset({"1", "3"}), score=0.42)
    g.add_node("1", depth=1, members=frozenset({"2", "4", "6"}))
    g.add_edge("0", "1", op="collapse")

    out = from_networkx(g)
    # frozenset round-trips as a sorted list (JSON-serialisable).
    assert out["nodes"]["0"]["members"] == ["1", "3"]
    assert out["nodes"]["0"]["score"] == 0.42
    assert out["nodes"]["1"]["members"] == ["2", "4", "6"]


def test_roundtrip_preserves_arbitrary_node_attributes():
    vg = sample_graph()
    for key, info in vg["nodes"].items():
        info["custom_score"] = int(key) * 10

    g = to_networkx(vg)
    for key in vg["nodes"]:
        assert g.nodes[key]["custom_score"] == int(key) * 10
    out = from_networkx(g)
    for key, info in vg["nodes"].items():
        assert out["nodes"][key]["custom_score"] == info["custom_score"]


def test_condensation_members_reach_graph_dict():
    vg = sample_graph()
    g = to_networkx(vg)
    cond = nx.condensation(g)
    out = from_networkx(cond)

    for key, info in out["nodes"].items():
        assert "members" in info, f"node {key} missing members attr"
        assert isinstance(info["members"], list)


def test_schema_allows_extra_node_attributes():
    jsonschema_module = pytest.importorskip("jsonschema")
    from importlib.resources import files
    schema = json.loads(files("visiter").joinpath(
        "schemas/v1/graph.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema_module.Draft202012Validator(schema)

    doc = {
        "schema_version": "1",
        "roots": [],
        "nodes": {"0": {"depth": 0, "members": ["1", "3"], "score": 0.42}},
        "edges": [],
        "pseudo_edges": [],
        "op_order": [],
    }
    errors = list(validator.iter_errors(doc))
    assert not errors, errors


# ---- analyze CLI ------------------------------------------------------------

def test_analyze_cli_scalar_result(tmp_path):
    import os
    import subprocess
    import sys

    env = {**os.environ,
           "PATH": os.path.dirname(sys.executable) + os.pathsep
                   + os.environ.get("PATH", "")}
    expr = ('range(1,10), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, "÷3"))], default=Op(lambda x: x+2, "+2")')
    iterate_run = subprocess.run(["visiter", "iterate", expr],
                                 capture_output=True, text=True, env=env)
    assert iterate_run.returncode == 0, iterate_run.stderr

    analyze_run = subprocess.run(
        ["visiter", "analyze", "nx.number_of_nodes(graph)"],
        input=iterate_run.stdout, capture_output=True, text=True, env=env)
    assert analyze_run.returncode == 0, analyze_run.stderr
    result = json.loads(analyze_run.stdout)
    assert isinstance(result, int)
    assert result > 0


def test_analyze_cli_graph_result_is_piped_back_into_to_dot(tmp_path):
    import os
    import subprocess
    import sys

    env = {**os.environ,
           "PATH": os.path.dirname(sys.executable) + os.pathsep
                   + os.environ.get("PATH", "")}
    expr = ('range(1,10), [Rule(lambda x: x%3==0, '
            'Op(lambda x: x//3, "÷3"))], default=Op(lambda x: x+2, "+2")')
    iterate_run = subprocess.run(["visiter", "iterate", expr],
                                 capture_output=True, text=True, env=env)
    # Condensation returns an nx.DiGraph; analyze should emit it as a
    # VisIter-schema JSON document so the next stage can to-dot it.
    analyze_run = subprocess.run(
        ["visiter", "analyze", "nx.condensation(graph)"],
        input=iterate_run.stdout, capture_output=True, text=True, env=env)
    assert analyze_run.returncode == 0, analyze_run.stderr
    doc = json.loads(analyze_run.stdout)
    assert "nodes" in doc
    assert "edges" in doc

    todot_run = subprocess.run(["visiter", "to-dot", ""],
                               input=analyze_run.stdout,
                               capture_output=True, text=True, env=env)
    assert todot_run.returncode == 0, todot_run.stderr
    assert "digraph" in todot_run.stdout
