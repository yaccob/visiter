import pytest

from visiter import Op, Rule, iterate


def descent_rules():
    # Rule: divisible-by-3 → divide by 3.
    return [Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))]


def descent_default():
    # Default: add 2 when no rule matches.
    return Op(lambda x: x + 2, "+2")


def test_basic_descent_forms_cycle():
    g = iterate([1], rules=descent_rules(), default=descent_default())
    # 1 → +2 → 3 → ÷3 → 1 forms a cycle; expect those two nodes.
    assert set(g["nodes"].keys()) == {"1", "3"}
    assert {(e["from"], e["to"]) for e in g["edges"]} == {(1, 3), (3, 1)}


def test_op_order_follows_rule_declaration():
    g = iterate([1], rules=descent_rules(), default=descent_default())
    assert g["op_order"] == ["÷3", "+2"]


def test_depth_is_bfs_minimum():
    g = iterate([1], rules=descent_rules(), default=descent_default())
    # 1 is start (depth 0); 3 reached in one step.
    assert g["nodes"]["1"]["depth"] == 0
    assert g["nodes"]["3"]["depth"] == 1


def test_max_depth_caps_expansion_and_emits_pseudo_edges():
    g = iterate([1], rules=descent_rules(), default=descent_default(),
                max_depth=1)
    # Only 1 (depth 0) and 3 (depth 1) should be present.
    assert set(g["nodes"].keys()) == {"1", "3"}
    # 3 is at max_depth; its rule (x%3==0 → ÷3) would fire → pseudo.
    assert {(pe["from"], pe["op"]) for pe in g["pseudo_edges"]} == {(3, "÷3")}


def test_rule_bound_emits_pseudo_edges_not_real_ones():
    # Doubling rule, bounded at 8.
    rules = [Rule(lambda x: True, Op(lambda x: 2 * x, "×2"),
                  bound=lambda x: 2 * x <= 8)]
    g = iterate([1], rules=rules, default=None)
    # Real edges: 1→2, 2→4, 4→8. Pseudo: 8 (would go to 16 but blocked).
    assert {(e["from"], e["to"]) for e in g["edges"]} == {(1, 2), (2, 4), (4, 8)}
    assert {(pe["from"], pe["op"]) for pe in g["pseudo_edges"]} == {(8, "×2")}


def test_default_fires_only_when_no_rule_matches():
    rules = [Rule(lambda x: x > 100, Op(lambda x: x // 2, "halve"))]
    g = iterate([5], rules=rules, default=Op(lambda x: x + 1, "+1"),
                max_nodes=20, on_limit="stop")
    # 5 < 100, so default fires; +1 goes 5→6→7→… until max_nodes.
    assert all(e["op"] == "+1" for e in g["edges"])


def test_max_nodes_raises_by_default():
    rules = [Rule(lambda x: True, Op(lambda x: x + 1, "+1"))]
    with pytest.raises(RuntimeError, match="max_nodes"):
        iterate([0], rules=rules, default=None, max_nodes=10)


def test_max_nodes_stop_returns_partial():
    rules = [Rule(lambda x: True, Op(lambda x: x + 1, "+1"))]
    g = iterate([0], rules=rules, default=None, max_nodes=10, on_limit="stop")
    assert len(g["nodes"]) == 10


def test_default_required_keyword():
    with pytest.raises(TypeError):
        iterate([1], rules=descent_rules())


def test_tags_recorded_when_predicate_matches():
    g = iterate([1, 2, 3], rules=descent_rules(), default=descent_default(),
                tags={"even": lambda x: x % 2 == 0})
    # From 2: 2 → 4 → 6 → 2 cycle; even applies to 2, 4, 6.
    assert "even" in g["nodes"]["2"].get("tags", [])
    assert "even" in g["nodes"]["4"].get("tags", [])
    assert "even" in g["nodes"]["6"].get("tags", [])
    assert "even" not in g["nodes"]["1"].get("tags", [])
    assert "even" not in g["nodes"]["3"].get("tags", [])


def test_multiple_rules_fan_out():
    # Rules can both match for the same x → multiple outgoing edges.
    rules = [
        Rule(lambda x: x < 100, Op(lambda x: 2 * x, "×2"),
             bound=lambda x: 2 * x < 100),
        Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3")),
    ]
    g = iterate([6], rules=rules, default=None)
    # 6 matches both rules → edges 6→12 and 6→2.
    out_from_6 = {(e["from"], e["to"]) for e in g["edges"] if e["from"] == 6}
    assert (6, 12) in out_from_6
    assert (6, 2) in out_from_6


def test_op_label_defaults_to_function_name():
    def square(x):
        return x * x
    assert Op(square).label == "square"


def test_op_label_defaults_to_lambda_body():
    op = Op(lambda x: x * 2)
    assert op.label == "x * 2"


def test_op_label_explicit_still_wins():
    op = Op(lambda x: x * 2, "double")
    assert op.label == "double"
    op_kw = Op(lambda x: x * 2, label="double")
    assert op_kw.label == "double"


def test_op_label_derivation_drives_iterate():
    # A rule built with auto-labeled ops must still populate op_order
    # correctly (labels go through the same code path as explicit ones).
    rules = [Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))]
    g = iterate([9], rules=rules, default=Op(lambda x: x + 2))
    assert g["op_order"] == ["x // 3", "x + 2"]


def test_op_label_disambiguates_lambdas_on_same_line():
    # The common idiom Rule(lambda x: cond, Op(lambda x: body)) has two
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
