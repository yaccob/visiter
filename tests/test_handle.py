"""GraphHandle uniformity across build paths (Phase 4).

Every ``build()`` now returns a :class:`GraphHandle`. For the eager paths (pure
Python, native PyO3 engine) it is pre-materialized and behaves exactly like the
populated dict that used to be returned; it also gains the uniform
``.view()`` / ``.to_vitgraph()`` / ``.is_materialized`` API. ``.view()`` on a
handle without a native view falls back to a Python crop that reproduces the
same neighborhood (and thus the same DOT) as cropping the full graph.
"""
from visiter import GraphHandle, viter


def _g():
    return (viter(8, max_depth=None, max_nodes=None, engine="python")
            .case(lambda n: n >= 1, lambda n: n - 1, label="d", id="d")
            .case(lambda n: n >= 2, lambda n: n - 2, label="d2", id="d2")).build()


def test_build_returns_pre_materialized_handle():
    g = _g()
    assert isinstance(g, GraphHandle)
    assert g.is_materialized is True          # eager build path
    assert "0" in g["nodes"]                   # behaves like the dict
    assert g == dict(g)                        # equal to its own contents


def test_python_view_fallback_dot_parity():
    g = _g()
    for direction in ("both", "forward", "backward"):
        ref = g.to_dot(anchor="4", radius=2, direction=direction)
        view = g.view("4", 2, direction)        # Python fallback crop
        got = view.to_dot(anchor="4", radius=2, direction=direction)
        assert got.source == ref.source


def test_handle_json_and_dict_ops_transparent():
    import json
    g = _g()
    # C-API paths (json.dump, dict()) work because the eager handle is filled.
    assert json.loads(json.dumps(g, default=str))["nodes"].keys() == g["nodes"].keys()
    assert dict(g)["op_order"] == g["op_order"]
