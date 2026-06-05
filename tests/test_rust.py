"""Path B (lang="rust") parity and validation tests.

Each parity test builds the same graph twice — once with Python-lambda callbacks
(pure-Python engine) and once with inline Rust-expression strings — and asserts
the resulting Graph dicts are identical. Skipped when rustc is not on PATH; the
validation/error tests always run.

Explicit id=/label= are passed in both builds so the op metadata matches; the
only difference is the callback representation (lambda vs string), which does
not appear in the Graph.
"""
import shutil

import pytest

from visiter import Match, viter

rustc = pytest.mark.skipif(
    shutil.which("rustc") is None, reason="rustc not on PATH")


@rustc
def test_parity_nim_match_all():
    def py():
        return (viter(10, max_depth=None, max_nodes=None, engine="python")
                .case(lambda n: n >= 1, lambda n: n - 1, label="t1", id="o1")
                .case(lambda n: n >= 2, lambda n: n - 2, label="t2", id="o2")
                .case(lambda n: n >= 3, lambda n: n - 3, label="t3", id="o3")
                .build())

    def rs():
        return (viter(10, lang="rust")
                .case("s >= 1", "s - 1", label="t1", id="o1")
                .case("s >= 2", "s - 2", label="t2", id="o2")
                .case("s >= 3", "s - 3", label="t3", id="o3")
                .build())

    assert py() == rs()


@rustc
def test_parity_grid_tuples_with_consts():
    side = 6

    def py():
        return (viter([(0, 0)], max_depth=None, max_nodes=None, engine="python")
                .case(lambda s: s[0] < side - 1, lambda s: (s[0] + 1, s[1]),
                      label="R", id="R")
                .case(lambda s: s[1] < side - 1, lambda s: (s[0], s[1] + 1),
                      label="U", id="U")
                .build())

    def rs():
        return (viter([(0, 0)], lang="rust", consts={"N": side})
                .case("s.0 < N - 1", "(s.0 + 1, s.1)", label="R", id="R")
                .case("s.1 < N - 1", "(s.0, s.1 + 1)", label="U", id="U")
                .build())

    assert py() == rs()


@rustc
def test_parity_match_first_exclusive():
    def py():
        return (viter(10, max_depth=None, max_nodes=None, engine="python",
                      match=Match.FIRST)
                .case(lambda n: n >= 1, lambda n: n - 1, label="a", id="a")
                .case(lambda n: n >= 2, lambda n: n - 2, label="b", id="b")
                .build())

    def rs():
        return (viter(10, lang="rust", match=Match.FIRST)
                .case("s >= 1", "s - 1", label="a", id="a")
                .case("s >= 2", "s - 2", label="b", id="b")
                .build())

    assert py() == rs()


@rustc
def test_parity_default_branch():
    def py():
        return (viter([6], max_depth=None, max_nodes=None, engine="python")
                .case(lambda n: n % 2 == 0 and n > 0, lambda n: n // 2,
                      label="half", id="half")
                .default(lambda n: n - 1 if n > 0 else n, label="dec", id="dec")
                .build())

    def rs():
        return (viter([6], lang="rust")
                .case("s % 2 == 0 && s > 0", "s / 2", label="half", id="half")
                .default("if s > 0 { s - 1 } else { s }", label="dec", id="dec")
                .build())

    assert py() == rs()


@rustc
def test_expression_is_default_label_and_id():
    # With no explicit label/id, the Rust expression itself is both.
    g = (viter(3, lang="rust").case("s >= 1", "s - 1").build())
    assert g["op_order"] == ["s - 1"]
    assert g["op_labels"] == {"s - 1": "s - 1"}
    assert g["edges"][0]["label"] == "s - 1"


# --- validation (run regardless of rustc) ------------------------------------

def test_rust_rejects_bounded_build():
    with pytest.raises(ValueError, match="unbounded"):
        (viter(10, lang="rust", max_depth=5)
         .case("s >= 1", "s - 1").build())


def test_rust_rejects_unsupported_value_type():
    with pytest.raises(ValueError, match="int or tuple"):
        (viter(["a"], lang="rust").case("true", "s").build())
