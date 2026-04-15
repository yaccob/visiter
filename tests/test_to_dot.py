from visiter import Op, Rule, iterate, to_dot
from visiter.render_helpers import resolve_op_colors


def make_descent_graph():
    return iterate(
        range(1, 28),
        rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
        default=Op(lambda x: x + 2, "+2"),
    )


def test_default_palette_assigns_blue_to_first_rule():
    g = make_descent_graph()
    colors = resolve_op_colors(g)
    # First rule's op = "÷3" → palette[0] = blue pair.
    assert colors["÷3"][0] == "#ccddff"   # fill
    assert colors["÷3"][1] == "#6688bb"   # edge
    # Default's op = "+2" → palette[1] = orange pair.
    assert colors["+2"][0] == "#ffddcc"
    assert colors["+2"][1] == "#ddbb99"


def test_to_dot_emits_dot_with_correct_edge_colors():
    g = make_descent_graph()
    src = to_dot(g, anchor=1, radius=10, direction="backward").source
    # Edges with op "÷3" should use blue, "+2" should use orange.
    assert '#6688bb' in src
    assert '#ddbb99' in src


def test_op_colors_override_palette():
    g = make_descent_graph()
    src = to_dot(g, op_colors={"÷3": "#123456"}).source
    assert '#123456' in src


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
    g = iterate([1],
                rules=[Rule(lambda x: True, Op(lambda x: 2 * x, "×2"),
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
    g = iterate([6],
                rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
                default=Op(lambda x: x + 2, "+2"))
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
    return iterate(
        start=["banana", "garage"],
        rules=[Rule(lambda s: len(s) > 0 and s[-1] in set("aeiou"),
                    Op(lambda s: s[:-1], "drop-vowel"))],
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
    g = iterate(
        start=[(0, 0)],
        rules=[Rule(lambda p: p[0] < 2,
                    Op(lambda p: (p[0] + 1, p[1]), "right"),
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


def test_show_ternary_warns_and_skips_for_non_int_values():
    import warnings
    g = make_string_graph()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src = to_dot(g, show_ternary=True).source
    assert any("show_ternary" in str(w.message) for w in caught)
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
