from visiter import Op, Rule, build, to_dot
from visiter.render_helpers import resolve_op_colors


def make_descent_graph():
    return build(
        range(1, 28),
        rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],
        default=Op(lambda x: x + 2, label="+2"),
    )


def test_default_palette_assigns_blue_to_first_rule():
    g = make_descent_graph()
    colors = resolve_op_colors(g)
    # Palette is keyed on identity (auto-derived from func). First
    # rule's op identity = "x // 3" → palette[0] = blue pair.
    assert colors["x // 3"][0] == "#ccddff"   # fill
    assert colors["x // 3"][1] == "#6688bb"   # edge
    # Default's op identity = "x + 2" → palette[1] = orange pair.
    assert colors["x + 2"][0] == "#ffddcc"
    assert colors["x + 2"][1] == "#ddbb99"


def test_to_dot_emits_dot_with_correct_edge_colors():
    g = make_descent_graph()
    src = to_dot(g, anchor=1, radius=10, direction="backward").source
    # Edges with op "÷3" should use blue, "+2" should use orange.
    assert '#6688bb' in src
    assert '#ddbb99' in src


def test_op_colors_override_palette():
    g = make_descent_graph()
    # Pin by identity (auto-derived from func).
    src = to_dot(g, op_colors={"x // 3": "#123456"}).source
    assert '#123456' in src


def test_to_dot_uses_op_labels_for_display_when_id_differs():
    # Explicit id decoupled from display label: the rendered edge
    # label must be the display label, not the id.
    g = build([6], rules=[
        Rule(lambda x: x % 2 == 0,
             Op(lambda x: x // 2, label="half", id="hv"))],
        default=None)
    src = to_dot(g).source
    assert " half " in src
    assert " hv " not in src


def test_anchor_radius_crops_graph():
    import re
    g = make_descent_graph()
    big = to_dot(g, anchor=1, radius=100, direction="backward").source
    small = to_dot(g, anchor=1, radius=2, direction="backward").source
    # Count regular value nodes (n<digits>) — exclude ghost_*.
    big_nodes = len(re.findall(r"^\tn\d+ \[", big, re.MULTILINE))
    small_nodes = len(re.findall(r"^\tn\d+ \[", small, re.MULTILINE))
    assert big_nodes > small_nodes


def test_pseudo_edges_become_ghost_stubs():
    # Bound-stopped graph: 1→2→4→8→(pseudo)16.
    g = build([1],
                rules=[Rule(lambda x: True, Op(lambda x: 2 * x, label="×2"),
                            bound=lambda x: 2 * x <= 8)],
                default=None)
    src = to_dot(g).source
    assert "ghost_out_8" in src


def test_outgoing_cut_emits_ghost_and_contributes_fill():
    g = make_descent_graph()
    src = to_dot(g, anchor=1, radius=2, direction="backward").source
    # Some kept node has an outgoing edge to outside → ghost_out.
    assert "ghost_out_" in src or "ghost_in_" in src


def test_show_factors_adds_factorization_to_label():
    g = build([6],
                rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],
                default=Op(lambda x: x + 2, label="+2"))
    src = to_dot(g, show_factors=True).source
    # 6 = 2·3 should appear in some form.
    assert "2·3" in src or "2&middot;3" in src


def test_to_dot_time_limit_stops_partial():
    g = make_descent_graph()
    # time_limit=0 forces immediate hit; on_limit=stop returns partial dot.
    dot = to_dot(g, time_limit="00:00:00", on_limit="stop")
    # At least the digraph header is in the source.
    assert "digraph" in dot.source


def test_to_dot_time_limit_raises():
    import pytest
    g = make_descent_graph()
    with pytest.raises(RuntimeError, match="time_limit"):
        to_dot(g, time_limit="00:00:00", on_limit="raise")


# ---- value-neutral rendering ------------------------------------------------

def make_string_graph():
    # Drop trailing vowel until none remain. Pure string-valued iteration.
    return build(
        start=["banana", "garage"],
        rules=[Rule(lambda s: len(s) > 0 and s[-1] in set("aeiou"),
                    Op(lambda s: s[:-1], label="drop-vowel"))],
        default=None,
    )


def test_to_dot_renders_string_valued_graph():
    g = make_string_graph()
    src = to_dot(g).source
    # Labels for the start values must appear in the DOT source.
    assert "banana" in src
    assert "garage" in src


def test_to_dot_marks_string_valued_roots_with_bold_border():
    g = make_string_graph()
    src = to_dot(g).source
    # Roots get penwidth=3; the start values are roots.
    assert "penwidth=3" in src or 'penwidth="3"' in src


def test_to_dot_renders_tuple_valued_graph_after_json_roundtrip():
    import json
    g = build(
        start=[(0, 0)],
        rules=[Rule(lambda p: p[0] < 2,
                    Op(lambda p: (p[0] + 1, p[1]), label="right"),
                    bound=lambda p: p[0] + 1 <= 2)],
        default=None,
    )
    wire = json.loads(json.dumps(g, default=str))
    src = to_dot(wire).source
    # The CLI-style representation of (0, 0) should appear as a label.
    assert "(0, 0)" in src


def test_show_binary_warns_and_skips_for_non_int_values():
    import warnings
    g = make_string_graph()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src = to_dot(g, show_binary=True).source
    assert any("show_binary" in str(w.message) for w in caught)
    # Render still produces output.
    assert "banana" in src


def test_show_factors_warns_and_skips_for_non_int_values():
    import warnings
    g = make_string_graph()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src = to_dot(g, show_factors=True).source
    assert any("show_factors" in str(w.message) for w in caught)
    assert "banana" in src


def test_value_range_warns_and_skips_for_non_int_values():
    import warnings
    g = make_string_graph()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src = to_dot(g, value_range=(0, 100)).source
    assert any("value_range" in str(w.message) for w in caught)
    # Filter was skipped → all original nodes still present.
    assert "banana" in src and "garage" in src


def test_node_label_attr_renders_attribute_as_label():
    graph = {
        "schema_version": "1",
        "roots": [],
        "nodes": {
            "0": {"depth": 0, "key_type": "integer", "members": ["1", "3"]},
            "1": {"depth": 1, "key_type": "integer", "members": ["2", "4", "6"]},
        },
        "edges": [{"from": 0, "to": 1, "op": "collapse"}],
        "pseudo_edges": [],
        "op_order": ["collapse"],
    }
    src = to_dot(graph, node_label_attr="members").source
    # List-typed attribute renders as {a, b} — braces, no repr quotes.
    assert "{1, 3}" in src
    assert "{2, 4, 6}" in src
    # The ugly Python list-str form must NOT leak into the DOT output.
    assert "['1', '3']" not in src


def test_node_label_attr_scalar_value_renders_as_plain_str():
    graph = {
        "schema_version": "1",
        "roots": [],
        "nodes": {
            "x": {"depth": 0, "key_type": "string", "score": 0.42},
            "y": {"depth": 1, "key_type": "string", "score": 1},
        },
        "edges": [],
        "pseudo_edges": [],
        "op_order": [],
    }
    src = to_dot(graph, node_label_attr="score").source
    assert "0.42" in src
    # Plain int scalar shows as "1", not "{1}".
    assert 'label=1' in src or 'label="1"' in src
    assert "{0.42}" not in src


def test_node_label_attr_missing_attribute_falls_back_to_node_key():
    graph = {
        "schema_version": "1",
        "roots": [],
        "nodes": {"alpha": {"depth": 0, "key_type": "string"}},  # no "members" attr
        "edges": [],
        "pseudo_edges": [],
        "op_order": [],
    }
    src = to_dot(graph, node_label_attr="members").source
    # Fell back to the node key.
    assert "alpha" in src


def test_default_label_is_node_key_when_no_attr_given():
    g = make_descent_graph()
    # Render with nothing specified.
    src = to_dot(g).source
    # Some integer node key should appear as a label verbatim.
    assert 'label=1' in src or 'label="1"' in src


def test_show_factors_follows_key_type_not_string_pattern():
    # A node whose key happens to look like an integer but whose
    # key_type says otherwise must NOT receive int-only annotations.
    graph = {
        "schema_version": "1",
        "roots": [],
        "nodes": {
            "42": {"depth": 0, "key_type": "string"},
        },
        "edges": [],
        "pseudo_edges": [],
        "op_order": [],
    }
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src = to_dot(graph, show_factors=True).source
    # Warning must fire because this is not an int-keyed graph.
    assert any("show_factors" in str(w.message) for w in caught)
    # The factorization "2·3·7" (for 42) must not be in the output.
    assert "2·3·7" not in src
    assert "2&middot;3&middot;7" not in src


def test_value_range_follows_key_type_not_string_pattern():
    graph = {
        "schema_version": "1",
        "roots": [],
        "nodes": {
            "42": {"depth": 0, "key_type": "string"},
        },
        "edges": [],
        "pseudo_edges": [],
        "op_order": [],
    }
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src = to_dot(graph, value_range=(0, 100)).source
    assert any("value_range" in str(w.message) for w in caught)
    # "42" still rendered (filter was skipped, not applied).
    assert "42" in src


def test_int_features_still_work_after_generalisation():
    # Sanity check: with integer-valued graphs, all int-specific features
    # should continue to function without warnings.
    import warnings
    g = make_descent_graph()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src = to_dot(g, show_binary=True, show_factors=True,
                     value_range=(1, 30)).source
    # No int-feature warnings expected.
    assert not any("show_binary" in str(w.message) or
                   "show_factors" in str(w.message) or
                   "value_range" in str(w.message) for w in caught)
    assert "digraph" in src
