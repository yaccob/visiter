"""Native-engine parity and fallback tests.

The native engine (Path A / ①) must produce a Graph byte-identical to pure
Python for the supported unbounded subset, and the engine selection must fall
back safely when native is unavailable or the build is outside the subset.

Parity tests are skipped when the ``visiter_native`` extension isn't built
(the default for a plain install); the fallback/selection tests always run.
"""
import pytest

from visiter import Match, OpResult, viter
from visiter import _accel

native_only = pytest.mark.skipif(
    not _accel.native_available(), reason="visiter_native extension not built")


def _both(make):
    """Build the same chain with the python and native engines."""
    return make("python"), make("native")


@native_only
def test_parity_nim_match_all():
    def make(engine):
        return (viter(10, max_depth=None, max_nodes=None, engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1, label="take 1")
                .case(lambda n: n >= 2, lambda n: n - 2, label="take 2")
                .case(lambda n: n >= 3, lambda n: n - 3, label="take 3")
                .build())
    py, nat = _both(make)
    assert py == nat


@native_only
def test_parity_match_first_exclusive():
    def make(engine):
        return (viter(10, max_depth=None, max_nodes=None,
                      match=Match.FIRST, engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1, label="a")
                .case(lambda n: n >= 2, lambda n: n - 2, label="b")
                .build())
    py, nat = _both(make)
    assert py == nat


@native_only
def test_parity_default_branch():
    def make(engine):
        return (viter([6], max_depth=None, max_nodes=None, engine=engine)
                .case(lambda n: n % 2 == 0 and n > 0, lambda n: n // 2,
                      label="half")
                .default(lambda n: n - 1 if n > 0 else n, label="dec")
                .build())
    py, nat = _both(make)
    assert py == nat


@native_only
def test_parity_parallel_edges_same_target():
    # Two distinct ops landing on the same successor must survive on both
    # engines (edge dedup keys on (from, to, op)).
    def make(engine):
        return (viter([6], max_depth=None, max_nodes=None, engine=engine)
                .case(lambda x: x == 6, lambda x: 3, label="div2", id="div2")
                .case(lambda x: x == 6, lambda x: 3, label="sub3", id="sub3")
                .build())
    py, nat = _both(make)
    assert py == nat
    assert len([e for e in py["edges"] if e["from"] == "6"]) == 2


@native_only
def test_parity_opresult_per_call_label():
    def op(n):
        return OpResult(n - 1, label=f"->{n - 1}")

    def make(engine):
        return (viter(5, max_depth=None, max_nodes=None, engine=engine)
                .case(lambda n: n >= 1, op, label="dec")
                .build())
    py, nat = _both(make)
    assert py == nat


@native_only
def test_parity_tags_and_key_type():
    def make(engine):
        return (viter(10, max_depth=None, max_nodes=None, engine=engine,
                      tags={"hl": lambda n: n % 4 == 0}, key_type="integer")
                .case(lambda n: n >= 1, lambda n: n - 1, label="t")
                .build())
    py, nat = _both(make)
    assert py == nat


@native_only
def test_parity_tuple_values_grid():
    side = 5

    def make(engine):
        return (viter([(0, 0)], max_depth=None, max_nodes=None, engine=engine)
                .case(lambda s: s[0] < side - 1, lambda s: (s[0] + 1, s[1]),
                      label="R")
                .case(lambda s: s[1] < side - 1, lambda s: (s[0], s[1] + 1),
                      label="U")
                .build())
    py, nat = _both(make)
    assert py == nat


@native_only
def test_parity_multiple_roots():
    def make(engine):
        return (viter([10, 7], max_depth=None, max_nodes=None, engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1, label="t1")
                .case(lambda n: n >= 2, lambda n: n - 2, label="t2")
                .build())
    py, nat = _both(make)
    assert py == nat


# --- bounded parity: limits must run natively, byte-identical to Python ------


def _both_quiet(make):
    """Like _both but swallow truncation UserWarnings on both paths."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return make("python"), make("native")


@native_only
def test_parity_max_depth_pseudo_edges():
    def make(engine):
        return (viter(10, max_depth=3, max_nodes=None, engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1, label="take 1")
                .case(lambda n: n >= 2, lambda n: n - 2, label="take 2")
                .case(lambda n: n >= 3, lambda n: n - 3, label="take 3")
                .build())
    py, nat = _both_quiet(make)
    assert py == nat
    assert py["pseudo_edges"], "expected depth truncation to emit pseudo-edges"


@native_only
def test_parity_max_depth_default_branch_pseudo():
    def make(engine):
        return (viter([8], max_depth=2, max_nodes=None, engine=engine)
                .case(lambda n: n % 2 == 0 and n > 0, lambda n: n // 2,
                      label="half")
                .default(lambda n: n - 1 if n > 0 else n, label="dec")
                .build())
    py, nat = _both_quiet(make)
    assert py == nat
    assert py["pseudo_edges"]


@native_only
def test_parity_max_nodes_truncation_single_chain():
    def make(engine):
        return (viter(1000, max_depth=None, max_nodes=8, engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1, label="dec")
                .build())
    py, nat = _both_quiet(make)
    assert py == nat
    assert len(py["nodes"]) <= 8


@native_only
def test_parity_max_nodes_truncation_branching():
    # branching frontier makes the exact truncation point order-sensitive —
    # the strongest byte-parity check for max_nodes.
    side = 20

    def make(engine):
        return (viter([(0, 0)], max_depth=None, max_nodes=37, engine=engine)
                .case(lambda s: s[0] < side - 1, lambda s: (s[0] + 1, s[1]),
                      label="R")
                .case(lambda s: s[1] < side - 1, lambda s: (s[0], s[1] + 1),
                      label="U")
                .build())
    py, nat = _both_quiet(make)
    assert py == nat
    assert len(py["nodes"]) <= 37


@native_only
def test_parity_bound_pseudo_edges():
    def make(engine):
        return (viter(10, max_depth=None, max_nodes=None, engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1,
                      bound=lambda n: n > 5, label="dec")
                .build())
    py, nat = _both_quiet(make)
    assert py == nat
    assert py["pseudo_edges"], "bound=False must record a pseudo-edge"


@native_only
def test_parity_bound_with_match_first():
    def make(engine):
        return (viter(12, max_depth=None, max_nodes=None,
                      match=Match.FIRST, engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1,
                      bound=lambda n: n > 4, label="a")
                .case(lambda n: n >= 2, lambda n: n - 2, label="b")
                .build())
    py, nat = _both_quiet(make)
    assert py == nat


@native_only
def test_parity_time_limit_not_hit():
    # a generous limit never fires → still byte-identical to Python.
    def make(engine):
        return (viter(10, max_depth=None, max_nodes=None,
                      time_limit="01:00:00", engine=engine)
                .case(lambda n: n >= 1, lambda n: n - 1, label="dec")
                .build())
    py, nat = _both_quiet(make)
    assert py == nat


@native_only
def test_native_time_limit_truncates_infinite_chain():
    # best-effort: native must honor time_limit on an otherwise infinite graph
    # (terminate + truncate), without a byte-parity guarantee.
    import time as _t

    def slow_inc(n):
        _t.sleep(0.05)
        return n + 1

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = (viter(0, max_depth=None, max_nodes=None,
                   time_limit="00:00:01", engine="native")
             .case(lambda n: True, slow_inc, label="inc")
             .build())
    # ~1s / 50ms ≈ a couple dozen nodes — bounded, didn't hang or OOM.
    assert 1 <= len(g["nodes"]) < 5000


# --- selection / fallback (run regardless of native availability) ------------

def test_invalid_engine_raises():
    with pytest.raises(ValueError, match="engine must be"):
        viter(10, engine="bogus").build()


def test_native_requested_but_unavailable_raises(monkeypatch):
    # When the extension isn't importable, an explicit engine='native' must
    # fail loudly rather than silently fall back. (The native engine now covers
    # the full subset, so unavailability is the only remaining failure mode.)
    monkeypatch.setattr(_accel, "_native", None)
    with pytest.raises(RuntimeError, match="engine='native'"):
        (viter(10, engine="native")
         .case(lambda n: n >= 1, lambda n: n - 1, label="t")
         .build())


def test_auto_bounded_build_just_works():
    # engine='auto' with a depth limit must just work (native if installed,
    # else pure Python), limit and all — i.e. produce the bounded graph.
    g = (viter(10, max_depth=3, engine="auto")
         .case(lambda n: n >= 1, lambda n: n - 1, label="t")
         .build())
    # depth-limited to 3 hops from 10 → nodes 10,9,8,7 reachable as real nodes.
    assert g["nodes"]["10"]["depth"] == 0
    assert max(info["depth"] for info in g["nodes"].values()) <= 3


def test_python_engine_explicit_matches_default():
    g_default = (viter(10, max_depth=None, max_nodes=None)
                 .case(lambda n: n >= 1, lambda n: n - 1, label="t")
                 .build())
    g_python = (viter(10, max_depth=None, max_nodes=None, engine="python")
                .case(lambda n: n >= 1, lambda n: n - 1, label="t")
                .build())
    assert g_default == g_python
