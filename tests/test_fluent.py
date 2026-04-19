"""Tests for the fluent pipeline API: Graph, Dot, write, filter."""

import json
import sys
from io import StringIO, BytesIO

import pytest

from visiter import viter, to_dot, Graph, Dot, write


def simple_graph():
    return (viter([1])
            .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
            .default(lambda x: x + 2, label="+2")
            .build())


# ---- Graph is a dict -------------------------------------------------------

def test_build_returns_graph_instance():
    g = simple_graph()
    assert isinstance(g, Graph)
    assert isinstance(g, dict)


def test_graph_dict_access():
    g = simple_graph()
    assert "nodes" in g
    assert "edges" in g
    assert g["schema_version"] == "1"


def test_graph_json_serializable():
    g = simple_graph()
    s = json.dumps(g, default=str)
    d = json.loads(s)
    assert d["schema_version"] == "1"


# ---- Graph.to_dot() --------------------------------------------------------

def test_graph_to_dot_returns_dot():
    g = simple_graph()
    d = g.to_dot()
    assert isinstance(d, Dot)


def test_graph_to_dot_has_source():
    g = simple_graph()
    d = g.to_dot()
    assert "digraph" in d.source


def test_graph_to_dot_kwargs_forwarded():
    g = (viter(range(1, 20))
         .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
         .default(lambda x: x + 2, label="+2")
         .build())
    d = g.to_dot(anchor=1, radius=2, direction="backward")
    assert "digraph" in d.source


# ---- Graph.tap() -----------------------------------------------------------

def test_graph_tap_calls_func_and_returns_self():
    g = simple_graph()
    called = []
    result = g.tap(lambda x: called.append(x))
    assert result is g
    assert called == [g]


def test_graph_peek_is_alias_for_tap():
    g = simple_graph()
    assert Graph.peek is Graph.tap


# ---- Graph.filter() --------------------------------------------------------

def test_graph_filter_with_callable():
    g = simple_graph()
    # Simple filter: adds a custom key
    def add_marker(graph):
        result = dict(graph)
        result["filtered"] = True
        return result
    filtered = g.filter(add_marker)
    assert isinstance(filtered, Graph)
    assert filtered["filtered"] is True


def test_graph_filter_returns_graph_from_dict():
    g = simple_graph()
    filtered = g.filter(lambda x: {"nodes": {}, "edges": []})
    assert isinstance(filtered, Graph)


# ---- Graph.write() ---------------------------------------------------------

def test_graph_write_to_file(tmp_path):
    g = simple_graph()
    out = tmp_path / "g.json"
    result = g.write(file=str(out))
    assert result is g  # returns self
    data = json.loads(out.read_text())
    assert data["schema_version"] == "1"


def test_graph_write_to_stdout(capsys):
    g = simple_graph()
    g.write()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "nodes" in data


# ---- Dot -------------------------------------------------------------------

def test_dot_source_property():
    g = simple_graph()
    d = g.to_dot()
    assert isinstance(d.source, str)
    assert "digraph" in d.source


def test_dot_tap_calls_func_and_returns_self():
    g = simple_graph()
    d = g.to_dot()
    called = []
    result = d.tap(lambda x: called.append(x))
    assert result is d
    assert called == [d]


def test_dot_peek_is_alias_for_tap():
    assert Dot.peek is Dot.tap


def test_dot_render_returns_self():
    g = simple_graph()
    d = g.to_dot()
    # Render to a file to avoid polluting stdout
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".svg") as f:
        result = d.render(file=f.name)
    assert result is d


def test_dot_render_to_file(tmp_path):
    g = simple_graph()
    out = tmp_path / "out.svg"
    g.to_dot().render(file=str(out))
    assert out.exists()
    body = out.read_text()
    assert "<svg" in body


def test_dot_render_dot_format(tmp_path):
    g = simple_graph()
    out = tmp_path / "out.dot"
    g.to_dot().render(format="dot", file=str(out))
    assert out.exists()
    body = out.read_text()
    assert "digraph" in body


def test_dot_write_to_file(tmp_path):
    g = simple_graph()
    out = tmp_path / "g.dot"
    d = g.to_dot()
    result = d.write(file=str(out))
    assert result is d  # chainable
    body = out.read_text()
    assert "digraph" in body


# ---- write() factory -------------------------------------------------------

def test_write_factory_graph_to_file(tmp_path):
    g = simple_graph()
    out = tmp_path / "via_write.json"
    g.tap(write(file=str(out)))
    data = json.loads(out.read_text())
    assert "nodes" in data


def test_write_factory_dot_to_file(tmp_path):
    g = simple_graph()
    out = tmp_path / "via_write.dot"
    g.to_dot().tap(write(file=str(out)))
    body = out.read_text()
    assert "digraph" in body


# ---- full chain -------------------------------------------------------------

def test_full_chain_build_to_render(tmp_path):
    out = tmp_path / "chain.svg"
    (viter(range(1, 8))
     .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
     .default(lambda x: x + 2, label="+2")
     .build()
     .to_dot().render(file=str(out)))
    assert out.exists()
    body = out.read_text()
    assert "<svg" in body


def test_full_chain_with_taps(tmp_path):
    json_out = tmp_path / "g.json"
    dot_out = tmp_path / "g.dot"
    svg_out = tmp_path / "g.svg"
    (viter(range(1, 8))
     .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
     .default(lambda x: x + 2, label="+2")
     .build()
     .tap(write(file=str(json_out)))
     .to_dot()
     .tap(write(file=str(dot_out)))
     .render(file=str(svg_out)))
    assert json_out.exists()
    assert dot_out.exists()
    assert svg_out.exists()
    assert "schema_version" in json_out.read_text()
    assert "digraph" in dot_out.read_text()
    assert "<svg" in svg_out.read_text()


# ---- NxFilter --------------------------------------------------------------

def test_nx_filter():
    pytest.importorskip("networkx")
    import networkx as nx
    from visiter import NxFilter

    g = (viter(range(1, 10))
         .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
         .default(lambda x: x + 2, label="+2")
         .build())
    filtered = g.filter(NxFilter(nx.condensation))
    assert isinstance(filtered, Graph)
    assert "nodes" in filtered
    assert "edges" in filtered


def test_nx_filter_in_chain(tmp_path):
    pytest.importorskip("networkx")
    import networkx as nx
    from visiter import NxFilter

    out = tmp_path / "condensed.svg"
    (viter(range(1, 10))
     .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
     .default(lambda x: x + 2, label="+2")
     .build()
     .filter(NxFilter(nx.condensation))
     .to_dot()
     .render(file=str(out)))
    assert out.exists()
    assert "<svg" in out.read_text()


# ---- standalone to_dot returns Dot -----------------------------------------

def test_standalone_to_dot_returns_dot():
    g = simple_graph()
    d = to_dot(g)
    assert isinstance(d, Dot)
    assert "digraph" in d.source
