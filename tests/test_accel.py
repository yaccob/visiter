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


# --- selection / fallback (run regardless of native availability) ------------

def test_invalid_engine_raises():
    with pytest.raises(ValueError, match="engine must be"):
        viter(10, engine="bogus").build()


def test_native_requested_but_unsupported_raises():
    # default max_depth=64 is outside the native subset, so an explicit
    # engine='native' must fail loudly rather than silently fall back.
    with pytest.raises(RuntimeError, match="engine='native'"):
        (viter(10, engine="native")
         .case(lambda n: n >= 1, lambda n: n - 1, label="t")
         .build())


def test_auto_falls_back_for_bounded_builds():
    # engine='auto' with a depth limit must just work (pure Python), limit and
    # all — i.e. produce the bounded graph, not error.
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
