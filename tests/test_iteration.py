"""Iteration-behavior tests via the viter() Builder API.

A handful of tests at the bottom exercise the internal ``Op`` class
directly (label/id derivation) — these import from ``visiter.iteration``
(the backing module) to avoid coupling the public API surface to
implementation details.
"""

import pytest

from visiter import viter
from visiter.iteration import Op  # internal: label/id derivation tests


# ---- BFS structure and cycle handling --------------------------------------

def descent():
    return (viter([1])
            .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
            .default(lambda x: x + 2, label="+2"))


def test_basic_descent_forms_cycle():
    g = descent().build()
    # 1 → +2 → 3 → ÷3 → 1 forms a cycle; expect those two nodes.
    assert set(g["nodes"].keys()) == {"1", "3"}
    assert {(e["from"], e["to"]) for e in g["edges"]} == {("1", "3"), ("3", "1")}


def test_op_order_follows_case_declaration():
    g = descent().build()
    # Identity is auto-derived from func, not from the display label,
    # so op_order keys are the lambda bodies' unparsed form — labels
    # live in graph["op_labels"].
    assert g["op_order"] == ["x // 3", "x + 2"]
    assert g["op_labels"] == {"x // 3": "÷3", "x + 2": "+2"}


def test_depth_is_bfs_minimum():
    g = descent().build()
    assert g["nodes"]["1"]["depth"] == 0
    assert g["nodes"]["3"]["depth"] == 1


def test_max_depth_caps_expansion_and_emits_pseudo_edges():
    g = (viter([1], max_depth=1)
         .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
         .default(lambda x: x + 2, label="+2")
         .build())
    # Only 1 (depth 0) and 3 (depth 1) should be present.
    assert set(g["nodes"].keys()) == {"1", "3"}
    # 3 is at max_depth; its case (x%3==0 → x // 3) would fire → pseudo.
    assert {(pe["from"], pe["op"]) for pe in g["pseudo_edges"]} == {("3", "x // 3")}


def test_case_bound_emits_pseudo_edges_not_real_ones():
    # Doubling case, bounded at 8.
    g = (viter([1])
         .case(lambda x: True, lambda x: 2 * x,
               label="×2", bound=lambda x: 2 * x <= 8)
         .build())
    # Real edges: 1→2, 2→4, 4→8. Pseudo: 8 (would go to 16 but blocked).
    assert {(e["from"], e["to"]) for e in g["edges"]} == {("1", "2"), ("2", "4"), ("4", "8")}
    assert {(pe["from"], pe["op"]) for pe in g["pseudo_edges"]} == {("8", "2 * x")}


def test_default_fires_only_when_no_case_matches():
    g = (viter([5], max_nodes=20)
         .case(lambda x: x > 100, lambda x: x // 2, label="halve")
         .default(lambda x: x + 1, label="+1")
         .build())
    # 5 < 100, so default fires; +1 goes 5→6→7→… until max_nodes.
    assert all(e["op"] == "x + 1" for e in g["edges"])


def test_max_nodes_raises_when_on_limit_is_raise():
    with pytest.raises(RuntimeError, match="max_nodes"):
        (viter([0], max_nodes=10, on_limit="raise")
         .case(lambda x: True, lambda x: x + 1, label="+1")
         .build())


def test_max_nodes_stop_returns_partial():
    g = (viter([0], max_nodes=10, on_limit="stop")
         .case(lambda x: True, lambda x: x + 1, label="+1")
         .build())
    assert len(g["nodes"]) == 10


def test_multiple_cases_fan_out():
    # Both cases can match for the same x → multiple outgoing edges.
    g = (viter([6])
         .case(lambda x: x < 100, lambda x: 2 * x, label="×2",
               bound=lambda x: 2 * x < 100)
         .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
         .build())
    # 6 matches both cases → edges 6→12 and 6→2.
    out_from_6 = {(e["from"], e["to"]) for e in g["edges"] if e["from"] == "6"}
    assert ("6", "12") in out_from_6
    assert ("6", "2") in out_from_6


def test_tags_recorded_when_predicate_matches():
    g = (viter([1, 2, 3], tags={"even": lambda x: x % 2 == 0})
         .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
         .default(lambda x: x + 2, label="+2")
         .build())
    # From 2: 2 → 4 → 6 → 2 cycle; even applies to 2, 4, 6.
    assert "even" in g["nodes"]["2"].get("tags", [])
    assert "even" in g["nodes"]["4"].get("tags", [])
    assert "even" in g["nodes"]["6"].get("tags", [])
    assert "even" not in g["nodes"]["1"].get("tags", [])
    assert "even" not in g["nodes"]["3"].get("tags", [])


# ---- label/id derivation and op-identity surface --------------------------

def test_op_label_defaults_to_function_name():
    def square(x):
        return x * x
    assert Op(square).label == "square"


def test_op_label_defaults_to_lambda_body():
    op = Op(lambda x: x * 2)
    assert op.label == "x * 2"


def test_op_label_explicit_still_wins():
    op = Op(lambda x: x * 2, label="double")
    assert op.label == "double"


def test_op_label_disambiguates_lambdas_on_same_line():
    # The common idiom `.case(lambda x: cond, lambda x: body)` has two
    # lambdas on one source line; each Op must still pick its own body.
    a, b = Op(lambda x: x + 1), Op(lambda x: x - 1)
    assert a.label == "x + 1"
    assert b.label == "x - 1"


def test_op_label_raises_when_source_unavailable():
    # functools.partial wraps a callable but carries no retrievable
    # source; the user must spell out label= in that case.
    from functools import partial
    with pytest.raises(ValueError, match="source unavailable"):
        Op(partial(lambda x, n: x + n, n=1))


def test_op_id_defaults_to_label():
    op = Op(lambda x: x + 1)
    assert op.id == op.label


def test_op_id_is_stable_against_custom_labels():
    # Two Ops from the same func — one with an auto-derived label, one
    # with a user-chosen pretty label — must still share an id, so
    # op_colors pinning remains valid across display tweaks.
    shared_func = lambda x: x // 3  # noqa: E731
    a = Op(shared_func)
    b = Op(shared_func, label="÷3")
    assert a.id == b.id
    assert a.label != b.label


def test_op_explicit_id_separates_display_from_key():
    op = Op(lambda x: x + 1, label="⊕", id="inc")
    assert op.label == "⊕"
    assert op.id == "inc"


def test_build_populates_op_labels_map():
    g = (viter([9])
         .case(lambda x: x % 3 == 0, lambda x: x // 3,
               label="÷3", id="div3")
         .default(lambda x: x + 2, label="+2", id="inc2")
         .build())
    assert g["op_order"] == ["div3", "inc2"]
    assert g["op_labels"] == {"div3": "÷3", "inc2": "+2"}
    ops_on_edges = {e["op"] for e in g["edges"]}
    assert ops_on_edges <= {"div3", "inc2"}


def test_build_warns_on_id_collision_with_different_funcs():
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        (viter([1])
         .case(lambda x: x > 0, lambda x: x - 1, id="shared")
         .case(lambda x: x < 0, lambda x: x + 1, id="shared")
         .build())
    assert any("id collision" in str(w.message) for w in caught)


# ---- key_type surface ------------------------------------------------------

def test_key_type_string_forces_type_for_all_nodes():
    # Integer seeds, but the caller asserts these should be treated as
    # "number" — e.g. because domain semantics are rational, not integral.
    g = viter([1, 2, 3], key_type="number").build()
    for info in g["nodes"].values():
        assert info["key_type"] == "number"


def test_key_type_string_rejects_invalid_json_primitive():
    # "int" is a Python type name, not a JSON Schema primitive.
    with pytest.raises(ValueError, match="key_type"):
        viter([1], key_type="int").build()


def test_key_type_callable_classifies_by_value():
    from fractions import Fraction
    g = viter([Fraction(1, 2), Fraction(3, 4)],
              key_type=lambda v: "number").build()
    for info in g["nodes"].values():
        assert info["key_type"] == "number"


def test_key_type_callable_none_falls_back_to_json_type():
    # Returning None for some values mixes in the default json_type logic
    # per value — here strings stay "string", ints become "number".
    g = viter([1, "a"],
              key_type=lambda v: "number" if isinstance(v, int) else None).build()
    assert g["nodes"]["1"]["key_type"] == "number"
    assert g["nodes"]["a"]["key_type"] == "string"


def test_key_type_callable_invalid_return_raises():
    with pytest.raises(ValueError, match="key_type"):
        viter([1], key_type=lambda v: "int").build()


def test_key_type_rejects_wrong_type():
    with pytest.raises(TypeError, match="key_type"):
        viter([1], key_type=42).build()


def test_build_no_warning_when_id_matches_same_op_reused():
    # Two cases that share the same id= value should not warn as long
    # as they're the exact same callable.
    import warnings
    shared = lambda x: x - 1  # noqa: E731
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        (viter([3])
         .case(lambda x: x > 0, shared, id="dec")
         .case(lambda x: x > 1, shared, id="dec")
         .build())
    assert not any("id collision" in str(w.message) for w in caught)
