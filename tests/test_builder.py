"""Tests for the new viter() builder API (replacing build/Rule/Op).

Happy-path coverage first; per-feature tests (exclusive, match, bound,
label/id, cases, strict errors) follow once the Builder is in place.
"""

import pytest

from visiter import viter, Graph, Match, OnLimit


def test_viter_builder_happy_path_returns_graph():
    g = (viter(range(1, 17))
         .case(lambda x: x % 2 == 0, lambda x: x // 2)
         .case(lambda x: x % 3 == 0, lambda x: x // 3)
         .default(lambda x: x * 5 + 7)
         .build())
    assert isinstance(g, Graph)
    assert isinstance(g, dict)
    assert g["schema_version"] == "1"
    # At least the start values must appear as nodes.
    for n in range(1, 17):
        assert str(n) in g["nodes"]


def test_viter_builder_without_default_marks_unmatched_as_terminal():
    # default defaults to None → a value with no matching case is a leaf
    # (no outgoing edge, no pseudo-edge).
    g = (viter([3])
         .case(lambda x: x % 2 == 0, lambda x: x // 2)
         .build())
    # 3 has no matching case and no default → it stays as a lone node.
    assert "3" in g["nodes"]
    assert g["edges"] == []
    assert g["pseudo_edges"] == []


# ---- Match mode and exclusive semantics -----------------------------------

def test_match_all_is_default_and_fires_every_matching_case():
    g = (viter([6])
         .case(lambda x: x % 2 == 0, lambda x: x // 2, id="halve")
         .case(lambda x: x % 3 == 0, lambda x: x // 3, id="third")
         .build())
    # Both rules match for 6 → two outgoing edges with distinct ops.
    edges = {(e["from"], e["to"], e["op"]) for e in g["edges"]}
    assert ("6", "3", "halve") in edges
    assert ("6", "2", "third") in edges


def test_match_first_fires_only_first_matching_case():
    g = (viter([6], match=Match.FIRST)
         .case(lambda x: x % 2 == 0, lambda x: x // 2, id="halve")
         .case(lambda x: x % 3 == 0, lambda x: x // 3, id="third")
         .build())
    ops_from_6 = {e["op"] for e in g["edges"] if e["from"] == "6"}
    assert ops_from_6 == {"halve"}


def test_case_exclusive_short_circuits_later_cases_and_default():
    g = (viter([6])
         .case(lambda x: x % 2 == 0, lambda x: x // 2,
               id="halve", exclusive=True)
         .case(lambda x: x % 3 == 0, lambda x: x // 3, id="third")
         .default(lambda x: x + 100, id="boom")
         .build())
    ops_from_6 = {e["op"] for e in g["edges"] if e["from"] == "6"}
    # Exclusive halve matches first → third and default are skipped.
    assert ops_from_6 == {"halve"}


def test_case_exclusive_does_not_prevent_earlier_non_exclusive_cases():
    # First case non-exclusive, second case exclusive.
    # For 6 both match; first fires additively, then exclusive second
    # fires and short-circuits the rest.
    g = (viter([6])
         .case(lambda x: x % 2 == 0, lambda x: x // 2, id="halve")
         .case(lambda x: x % 3 == 0, lambda x: x // 3,
               id="third", exclusive=True)
         .case(lambda x: x > 0, lambda x: x - 1, id="dec")
         .build())
    ops_from_6 = {e["op"] for e in g["edges"] if e["from"] == "6"}
    assert "halve" in ops_from_6
    assert "third" in ops_from_6
    assert "dec" not in ops_from_6


# ---- bound: pseudo-edges vs. real edges -----------------------------------

def test_bound_produces_pseudo_edge_when_false():
    # "Double until 8, then stop." bound=False at x=8 records a pseudo
    # instead of recursing to 16.
    g = (viter([1])
         .case(lambda x: True, lambda x: 2 * x,
               id="double", bound=lambda x: 2 * x <= 8)
         .build())
    edges = {(e["from"], e["to"]) for e in g["edges"]}
    assert edges == {("1", "2"), ("2", "4"), ("4", "8")}
    pseudo = {(pe["from"], pe["op"]) for pe in g["pseudo_edges"]}
    assert pseudo == {("8", "double")}


# ---- label and id derivation/overrides ------------------------------------

def test_derived_label_from_named_function_uses_name():
    def halve(x):
        return x // 2
    g = (viter([4])
         .case(lambda x: x % 2 == 0, halve)
         .build())
    # Op label/id are derived from the function name for named functions.
    assert g["op_labels"]["halve"] == "halve"
    assert "halve" in g["op_order"]


def test_explicit_label_does_not_change_derived_id():
    # label overrides display only; id remains auto-derived from the
    # function source so reusing the same func yields the same id.
    g = (viter([4])
         .case(lambda x: x % 2 == 0, lambda x: x // 2, label="÷2")
         .build())
    # id derived from lambda body "x // 2"; label overridden to "÷2".
    assert g["op_labels"]["x // 2"] == "÷2"


def test_explicit_id_overrides_derivation():
    g = (viter([4])
         .case(lambda x: x % 2 == 0, lambda x: x // 2, id="halve")
         .build())
    assert "halve" in g["op_order"]
    assert g["op_labels"]["halve"] == "x // 2"


# ---- .cases() helper ------------------------------------------------------

def test_cases_helper_accepts_two_tuples():
    g = (viter([6])
         .cases([
             (lambda x: x % 2 == 0, lambda x: x // 2),
             (lambda x: x % 3 == 0, lambda x: x // 3),
         ])
         .build())
    edges_from_6 = {(e["to"]) for e in g["edges"] if e["from"] == "6"}
    assert edges_from_6 == {"3", "2"}


def test_cases_helper_accepts_three_tuples_with_kwargs():
    g = (viter([6])
         .cases([
             (lambda x: x % 2 == 0, lambda x: x // 2, {"id": "halve"}),
             (lambda x: x % 3 == 0, lambda x: x // 3,
              {"id": "third", "exclusive": True}),
             (lambda x: x > 0, lambda x: x - 1, {"id": "dec"}),
         ])
         .build())
    ops_from_6 = {e["op"] for e in g["edges"] if e["from"] == "6"}
    # Exclusive "third" short-circuits "dec"; halve already fired.
    assert ops_from_6 == {"halve", "third"}


def test_cases_helper_rejects_bad_shape():
    with pytest.raises(ValueError, match="cases items"):
        viter([1]).cases([(lambda x: True,)]).build()


# ---- strict errors --------------------------------------------------------

def test_double_default_raises():
    b = viter([1]).default(lambda x: x + 1)
    with pytest.raises(RuntimeError, match="default already set"):
        b.default(lambda x: x + 2)


# ---- Builder.render() shortcut --------------------------------------------

def test_builder_render_is_shortcut_for_build_to_dot_render(tmp_path):
    out = tmp_path / "shortcut.svg"
    result = (viter([1])
              .case(lambda x: x % 3 == 0, lambda x: x // 3)
              .default(lambda x: x + 2)
              .render(file=str(out)))
    assert out.exists()
    assert "<svg" in out.read_text()
    # Builder.render() returns the Dot so it can still be chained if
    # someone wants (matches Dot.render() which returns self).
    assert result is not None
