"""Path B (lang="rust") parity and validation tests.

Each parity test builds the same graph twice — once with Python-lambda callbacks
(pure-Python engine) and once with inline Rust-expression strings — and asserts
the resulting Graph dicts are identical, **including default bounds, ghost-stub
pseudo-edges, max_nodes truncation, tags and key_type**. `lang="rust"` is a
drop-in: same chain ⇒ same graph.

Skipped when rustc is not on PATH; the validation/error tests always run.
Explicit id=/label= are passed in both builds so op metadata matches; the only
difference is the callback representation (lambda vs string).
"""
import shutil

import pytest

from visiter import Match, viter

rustc = pytest.mark.skipif(
    shutil.which("rustc") is None, reason="rustc not on PATH")


def _assert_parity(py_chain, rs_chain):
    assert py_chain().build() == rs_chain().build()


# --- core parity (finite, shallow) -------------------------------------------

@rustc
def test_parity_nim_match_all():
    _assert_parity(
        lambda: (viter(10, max_depth=None, max_nodes=None, engine="python")
                 .case(lambda n: n >= 1, lambda n: n - 1, label="t1", id="o1")
                 .case(lambda n: n >= 2, lambda n: n - 2, label="t2", id="o2")
                 .case(lambda n: n >= 3, lambda n: n - 3, label="t3", id="o3")),
        lambda: (viter(10, max_depth=None, max_nodes=None, lang="rust")
                 .case("s >= 1", "s - 1", label="t1", id="o1")
                 .case("s >= 2", "s - 2", label="t2", id="o2")
                 .case("s >= 3", "s - 3", label="t3", id="o3")))


@rustc
def test_parity_grid_tuples_with_consts():
    side = 6
    _assert_parity(
        lambda: (viter([(0, 0)], max_depth=None, max_nodes=None,
                       engine="python")
                 .case(lambda s: s[0] < side - 1, lambda s: (s[0] + 1, s[1]),
                       label="R", id="R")
                 .case(lambda s: s[1] < side - 1, lambda s: (s[0], s[1] + 1),
                       label="U", id="U")),
        lambda: (viter([(0, 0)], max_depth=None, max_nodes=None, lang="rust",
                       consts={"N": side})
                 .case("s.0 < N - 1", "(s.0 + 1, s.1)", label="R", id="R")
                 .case("s.1 < N - 1", "(s.0, s.1 + 1)", label="U", id="U")))


@rustc
def test_parity_match_first_exclusive():
    _assert_parity(
        lambda: (viter(10, max_depth=None, max_nodes=None, engine="python",
                       match=Match.FIRST)
                 .case(lambda n: n >= 1, lambda n: n - 1, label="a", id="a")
                 .case(lambda n: n >= 2, lambda n: n - 2, label="b", id="b")),
        lambda: (viter(10, max_depth=None, max_nodes=None, lang="rust",
                       match=Match.FIRST)
                 .case("s >= 1", "s - 1", label="a", id="a")
                 .case("s >= 2", "s - 2", label="b", id="b")))


@rustc
def test_parity_default_branch():
    _assert_parity(
        lambda: (viter([6], max_depth=None, max_nodes=None, engine="python")
                 .case(lambda n: n % 2 == 0 and n > 0, lambda n: n // 2,
                       label="half", id="half")
                 .default(lambda n: n - 1 if n > 0 else n, label="dec",
                          id="dec")),
        lambda: (viter([6], max_depth=None, max_nodes=None, lang="rust")
                 .case("s % 2 == 0 && s > 0", "s / 2", label="half", id="half")
                 .default("if s > 0 { s - 1 } else { s }", label="dec",
                          id="dec")))


# --- bounds and pseudo-edges (the behavioral-parity cases) -------------------

@rustc
def test_parity_default_max_depth_on_infinite_space():
    # Infinite space with NO explicit limit: both paths must apply the default
    # max_depth=64 and emit the ghost-stub pseudo-edge at the boundary. (This is
    # the case that previously diverged silently — rust ran unbounded.)
    _assert_parity(
        lambda: (viter(0, engine="python")
                 .case(lambda s: True, lambda s: s + 1, label="inc", id="inc")),
        lambda: (viter(0, lang="rust")
                 .case("true", "s + 1", label="inc", id="inc")))


@rustc
def test_parity_explicit_max_depth_pseudo_edges():
    _assert_parity(
        lambda: (viter(0, max_depth=5, engine="python")
                 .case(lambda s: True, lambda s: s + 1, label="inc", id="inc")),
        lambda: (viter(0, max_depth=5, lang="rust")
                 .case("true", "s + 1", label="inc", id="inc")))


@rustc
def test_parity_max_nodes_truncation():
    _assert_parity(
        lambda: (viter(0, max_nodes=10, max_depth=None, engine="python")
                 .case(lambda s: True, lambda s: s + 1, label="i", id="i")),
        lambda: (viter(0, max_nodes=10, max_depth=None, lang="rust")
                 .case("true", "s + 1", label="i", id="i")))


@rustc
def test_parity_bound_predicate_pseudo_edges():
    # bound() False where condition() True records a pseudo-edge instead of a
    # real successor — same ghost stubs in both paths.
    _assert_parity(
        lambda: (viter(0, max_depth=None, engine="python")
                 .case(lambda s: s < 10, lambda s: s + 1,
                       bound=lambda s: s < 5, label="i", id="i")),
        lambda: (viter(0, max_depth=None, lang="rust")
                 .case("s < 10", "s + 1", bound="s < 5", label="i", id="i")))


@rustc
def test_parity_string_values_and_tags():
    _assert_parity(
        lambda: (viter("a", max_depth=4, engine="python",
                       tags={"hl": lambda s: len(s) % 2 == 0})
                 .case(lambda s: len(s) < 6, lambda s: s + "a",
                       label="grow", id="grow")),
        lambda: (viter("a", max_depth=4, lang="rust",
                       tags={"hl": "s.len() % 2 == 0"})
                 .case("s.len() < 6", 's.to_string() + "a"',
                       label="grow", id="grow")))


@rustc
def test_parity_match_first_with_max_depth():
    _assert_parity(
        lambda: (viter(20, max_depth=4, match=Match.FIRST, engine="python")
                 .case(lambda n: n % 2 == 0, lambda n: n // 2, label="h", id="h")
                 .case(lambda n: True, lambda n: n - 1, label="d", id="d")),
        lambda: (viter(20, max_depth=4, match=Match.FIRST, lang="rust")
                 .case("s % 2 == 0", "s / 2", label="h", id="h")
                 .case("true", "s - 1", label="d", id="d")))


@rustc
def test_expression_is_default_label_and_id():
    # With no explicit label/id, the Rust expression itself is both.
    g = (viter(3, max_depth=None, lang="rust").case("s >= 1", "s - 1").build())
    assert g["op_order"] == ["s - 1"]
    assert g["op_labels"] == {"s - 1": "s - 1"}
    assert g["edges"][0]["label"] == "s - 1"


# --- validation (run regardless of rustc) ------------------------------------

def test_rust_rejects_time_limit():
    with pytest.raises(ValueError, match="time_limit"):
        (viter(10, lang="rust", time_limit="00:00:01")
         .case("s >= 1", "s - 1").build())


def test_rust_rejects_unsupported_value_type():
    with pytest.raises(ValueError, match="int, tuple"):
        (viter([1.5], lang="rust").case("true", "s").build())
