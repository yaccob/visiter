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
