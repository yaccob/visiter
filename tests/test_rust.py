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
from fractions import Fraction

import pytest

from visiter import Match, OpResult, viter

rustc = pytest.mark.skipif(
    shutil.which("rustc") is None, reason="rustc not on PATH")
cargo = pytest.mark.skipif(
    shutil.which("cargo") is None, reason="cargo not on PATH")


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
        lambda: (viter(10, max_depth=None, max_nodes=None, lang="rust", bind="s")
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
                       bind="s", consts={"N": side})
                 .case("s.0 < N - 1", "(s.0 + 1, s.1)", label="R", id="R")
                 .case("s.1 < N - 1", "(s.0, s.1 + 1)", label="U", id="U")))


@rustc
def test_parity_parallel_edges_same_target():
    # Two distinct ops landing on the same successor are two edges, in the
    # rust codegen path too — dedup keys on (from, to, op), not (from, to).
    _assert_parity(
        lambda: (viter([6], max_depth=None, max_nodes=None, engine="python")
                 .case(lambda x: x == 6, lambda x: 3, label="div2", id="div2")
                 .case(lambda x: x == 6, lambda x: 3, label="sub3", id="sub3")),
        lambda: (viter([6], max_depth=None, max_nodes=None, lang="rust", bind="s")
                 .case("s == 6", "3", label="div2", id="div2")
                 .case("s == 6", "3", label="sub3", id="sub3")))


@rustc
def test_parity_i128_beyond_i64():
    # Doubling past 2^63 overflows i64 (silent wrap) but fits i128; the rust
    # path must match Python's exact integers up to the i128 ceiling.
    _assert_parity(
        lambda: (viter([1], max_depth=70, max_nodes=None, engine="python")
                 .case(lambda s: s >= 0, lambda s: s * 2, label="x2", id="x2")),
        lambda: (viter([1], max_depth=70, max_nodes=None, lang="rust", bind="s")
                 .case("s >= 0", "s * 2", label="x2", id="x2")))


@rustc
def test_rust_int_overflow_raises_not_silent():
    # Past the i128 ceiling the rust path must fail loudly (overflow-checks),
    # not silently wrap into a wrong graph.
    import subprocess
    chain = (viter([1], max_depth=130, max_nodes=None, lang="rust", bind="s")
             .case("s >= 0", "s * 2", label="x2", id="x2"))
    with pytest.raises(subprocess.CalledProcessError):
        chain.build()


@rustc
def test_parity_match_first_exclusive():
    _assert_parity(
        lambda: (viter(10, max_depth=None, max_nodes=None, engine="python",
                       match=Match.FIRST)
                 .case(lambda n: n >= 1, lambda n: n - 1, label="a", id="a")
                 .case(lambda n: n >= 2, lambda n: n - 2, label="b", id="b")),
        lambda: (viter(10, max_depth=None, max_nodes=None, lang="rust",
                       bind="s", match=Match.FIRST)
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
        lambda: (viter([6], max_depth=None, max_nodes=None, lang="rust", bind="s")
                 .case("s % 2 == 0 && s > 0", "s / 2", label="half", id="half")
                 .default("if s > 0 { s - 1 } else { s }", label="dec",
                          id="dec")))


@rustc
def test_parity_parallel_edges_same_target_distinct_ops():
    # Two distinct ops mapping the same x onto the same y are TWO edges: the
    # edge dedup keys on (from, to, op), not (from, to). Mirrors the pure-Python
    # test of the same name — this is what lets a self-reference loop coexist
    # with a genuine same-target edge (reverse_collatz show_even at node 1).
    _assert_parity(
        lambda: (viter([6], max_depth=None, max_nodes=None, engine="python")
                 .case(lambda x: x == 6, lambda x: 3, label="div2", id="div2")
                 .case(lambda x: x == 6, lambda x: 3, label="sub3", id="sub3")),
        lambda: (viter([6], max_depth=None, max_nodes=None, lang="rust", bind="s")
                 .case("s == 6", "3", label="div2", id="div2")
                 .case("s == 6", "3", label="sub3", id="sub3")))


@rustc
def test_parity_parallel_edges_same_op_collapse():
    # Same op (same id) firing for the same x→y under two conditions stays ONE
    # edge — the op, not the condition, is the edge's identity. Mirrors the
    # pure-Python test of the same name.
    _assert_parity(
        lambda: (viter([6], max_depth=None, max_nodes=None, engine="python")
                 .case(lambda x: x == 6, lambda x: 3, label="to3", id="same")
                 .case(lambda x: x < 10, lambda x: 3, label="to3", id="same")),
        lambda: (viter([6], max_depth=None, max_nodes=None, lang="rust", bind="s")
                 .case("s == 6", "3", label="to3", id="same")
                 .case("s < 10", "3", label="to3", id="same")))


# --- bounds and pseudo-edges (the behavioral-parity cases) -------------------

@rustc
def test_parity_default_max_depth_on_infinite_space():
    # Infinite space with NO explicit limit: both paths must apply the default
    # max_depth=64 and emit the ghost-stub pseudo-edge at the boundary. (This is
    # the case that previously diverged silently — rust ran unbounded.)
    _assert_parity(
        lambda: (viter(0, engine="python")
                 .case(lambda s: True, lambda s: s + 1, label="inc", id="inc")),
        lambda: (viter(0, lang="rust", bind="s")
                 .case("true", "s + 1", label="inc", id="inc")))


@rustc
def test_parity_explicit_max_depth_pseudo_edges():
    _assert_parity(
        lambda: (viter(0, max_depth=5, engine="python")
                 .case(lambda s: True, lambda s: s + 1, label="inc", id="inc")),
        lambda: (viter(0, max_depth=5, lang="rust", bind="s")
                 .case("true", "s + 1", label="inc", id="inc")))


@rustc
def test_parity_max_nodes_truncation():
    _assert_parity(
        lambda: (viter(0, max_nodes=10, max_depth=None, engine="python")
                 .case(lambda s: True, lambda s: s + 1, label="i", id="i")),
        lambda: (viter(0, max_nodes=10, max_depth=None, lang="rust", bind="s")
                 .case("true", "s + 1", label="i", id="i")))


@rustc
def test_parity_bound_predicate_pseudo_edges():
    # bound() False where condition() True records a pseudo-edge instead of a
    # real successor — same ghost stubs in both paths.
    _assert_parity(
        lambda: (viter(0, max_depth=None, engine="python")
                 .case(lambda s: s < 10, lambda s: s + 1,
                       bound=lambda s: s < 5, label="i", id="i")),
        lambda: (viter(0, max_depth=None, lang="rust", bind="s")
                 .case("s < 10", "s + 1", bound="s < 5", label="i", id="i")))


@rustc
def test_parity_string_values_and_tags():
    _assert_parity(
        lambda: (viter("a", max_depth=4, engine="python",
                       tags={"hl": lambda s: len(s) % 2 == 0})
                 .case(lambda s: len(s) < 6, lambda s: s + "a",
                       label="grow", id="grow")),
        lambda: (viter("a", max_depth=4, lang="rust", bind="s",
                       tags={"hl": "s.len() % 2 == 0"})
                 .case("s.len() < 6", 's.to_string() + "a"',
                       label="grow", id="grow")))


@rustc
def test_parity_match_first_with_max_depth():
    _assert_parity(
        lambda: (viter(20, max_depth=4, match=Match.FIRST, engine="python")
                 .case(lambda n: n % 2 == 0, lambda n: n // 2, label="h", id="h")
                 .case(lambda n: True, lambda n: n - 1, label="d", id="d")),
        lambda: (viter(20, max_depth=4, match=Match.FIRST, lang="rust", bind="s")
                 .case("s % 2 == 0", "s / 2", label="h", id="h")
                 .case("true", "s - 1", label="d", id="d")))


@rustc
def test_bind_custom_name_parity():
    # The bound value's identifier is chosen via bind=; the name must not change
    # the resulting graph (it only renames the value the expressions read from).
    _assert_parity(
        lambda: (viter(10, max_depth=None, max_nodes=None, engine="python",
                       tags={"hl": lambda n: n % 4 == 0})
                 .case(lambda n: n >= 1, lambda n: n - 1, label="t1", id="o1")
                 .case(lambda n: n >= 2, lambda n: n - 2, label="t2", id="o2")),
        lambda: (viter(10, max_depth=None, max_nodes=None, lang="rust",
                       bind="n", tags={"hl": "n % 4 == 0"})
                 .case("n >= 1", "n - 1", label="t1", id="o1")
                 .case("n >= 2", "n - 2", label="t2", id="o2")))


@rustc
def test_bind_tuple_member_access_parity():
    # A custom bind name also threads through tuple member access (bind.0,
    # bind.1), bound predicates and the default branch.
    _assert_parity(
        lambda: (viter([(0, 0)], max_depth=4, engine="python")
                 .case(lambda p: p[0] < 3, lambda p: (p[0] + 1, p[1]),
                       label="R", id="R")
                 .default(lambda p: (p[0], p[1] + 1), label="U", id="U")),
        lambda: (viter([(0, 0)], max_depth=4, lang="rust", bind="p")
                 .case("p.0 < 3", "(p.0 + 1, p.1)", label="R", id="R")
                 .default("(p.0, p.1 + 1)", label="U", id="U")))


@rustc
def test_bind_name_matching_internal_helper_is_allowed():
    # `key` used to be a reserved name; with the fixed internal param it is just
    # a normal bind name now (it only shadows the helper inside its expression,
    # which here doesn't call it), so the graph still matches the Python build.
    _assert_parity(
        lambda: (viter(5, max_depth=None, engine="python")
                 .case(lambda key: key >= 1, lambda key: key - 1,
                       label="dec", id="dec")),
        lambda: (viter(5, max_depth=None, lang="rust", bind="key")
                 .case("key >= 1", "key - 1", label="dec", id="dec")))


def test_bind_required_for_rust():
    with pytest.raises(ValueError, match="requires a bind="):
        (viter(5, lang="rust").case("true", "s").build())


def test_bind_invalid_identifier_rejected():
    with pytest.raises(ValueError, match="valid Rust identifier"):
        (viter(5, lang="rust", bind="2x").case("true", "x").build())


def test_bind_keyword_rejected():
    with pytest.raises(ValueError, match="Rust keyword"):
        (viter(5, lang="rust", bind="match").case("true", "match").build())


@rustc
def test_expression_is_default_label_and_id():
    # With no explicit label/id, the Rust expression itself is both.
    g = (viter(3, max_depth=None, lang="rust", bind="s")
         .case("s >= 1", "s - 1").build())
    assert g["op_order"] == ["s - 1"]
    assert g["op_labels"] == {"s - 1": "s - 1"}
    assert g["edges"][0]["label"] == "s - 1"


@rustc
@cargo
def test_parity_golden_ratio_rational():
    # Exact rationals: x -> 1 + 1/x from Fraction(1). Rust uses BigRational
    # (num-rational, compiled via cargo); must match Python's Fraction exactly,
    # including the Fibonacci-ratio keys (1, 2, 3/2, 5/3, 8/5, ...).
    _assert_parity(
        lambda: (viter([Fraction(1)], max_depth=7, key_type="number",
                       engine="python")
                 .case(lambda x: True, lambda x: 1 + 1 / x, label="g", id="g")),
        lambda: (viter([Fraction(1)], max_depth=7, key_type="number",
                       lang="rust", bind="s")
                 .case("true", "r(1) + s.recip()", label="g", id="g")))


@rustc
def test_parity_time_limit_not_hit():
    # A generous time_limit that is never reached must not change the graph.
    _assert_parity(
        lambda: (viter(10, max_depth=None, max_nodes=None,
                       time_limit="01:00:00", engine="python")
                 .case(lambda n: n >= 1, lambda n: n - 1, label="t", id="t")),
        lambda: (viter(10, max_depth=None, max_nodes=None,
                       time_limit="01:00:00", lang="rust", bind="s")
                 .case("s >= 1", "s - 1", label="t", id="t")))


@rustc
def test_parity_time_limit_zero_truncates():
    # time_limit=0 truncates before any expansion: both paths yield an empty
    # graph (no nodes) and warn. (Deterministic because elapsed >= 0 always.)
    kw = dict(max_depth=None, max_nodes=None, time_limit="00:00:00")
    py = (viter(10, engine="python", **kw)
          .case(lambda n: n >= 1, lambda n: n - 1, label="t", id="t").build())
    rs = (viter(10, lang="rust", bind="s", **kw)
          .case("s >= 1", "s - 1", label="t", id="t").build())
    assert py == rs
    assert py["nodes"] == {}


@rustc
def test_parity_opresult_per_call_labels():
    # Python returns OpResult for a per-call edge label; the rust analogue is
    # label_rs (a Rust expression over `s`). max_depth=2 also produces
    # pseudo-edges, which keep the *static* label in both paths.
    _assert_parity(
        lambda: (viter(5, max_depth=2, engine="python")
                 .case(lambda n: n >= 1,
                       lambda n: OpResult(n - 1, label=f"-1 from {n}"),
                       label="dec", id="dec")),
        lambda: (viter(5, max_depth=2, lang="rust", bind="s")
                 .case("s >= 1", "s - 1", label="dec", id="dec",
                       label_rs='format!("-1 from {}", s)')))


# --- validation (run regardless of rustc) ------------------------------------

def test_label_rs_rejected_in_python_path():
    with pytest.raises(ValueError, match="label_rs"):
        (viter(5).case(lambda n: n >= 1, lambda n: n - 1,
                       label_rs='format!("{}", s)').build())


def test_rust_rejects_unsupported_value_type():
    with pytest.raises(ValueError, match="int, tuple"):
        (viter([1.5], lang="rust", bind="s").case("true", "s").build())


# --- Phase 1a: GraphHandle (lazy materialization + content-addressed reuse) --

@rustc
def test_rust_build_returns_lazy_handle():
    from visiter import GraphHandle
    h = (viter([1], max_depth=8, max_nodes=None, lang="rust", bind="s")
         .case("s >= 0", "s * 2", label="x2", id="x2")).build()
    assert isinstance(h, GraphHandle)
    assert h.is_materialized is False
    # First dict-ish access materializes exactly once.
    _ = h["nodes"]
    assert h.is_materialized is True
    # materialize() is idempotent and returns self.
    assert h.materialize() is h


@rustc
def test_rust_handle_parity_through_eq_both_directions():
    # The lazy handle compares equal to the eager pure-Python Graph, with the
    # handle on either side of ==.
    py = (viter([1], max_depth=8, max_nodes=None, engine="python")
          .case(lambda s: s >= 0, lambda s: s * 2, label="x2", id="x2")).build()
    h = (viter([1], max_depth=8, max_nodes=None, lang="rust", bind="s")
         .case("s >= 0", "s * 2", label="x2", id="x2")).build()
    assert h == py
    assert py == h


@rustc
def test_rust_handle_content_addressed_reuse():
    from visiter.rustgen import _GRAPH_CACHE

    def mk():
        return (viter([1], max_depth=10, max_nodes=None, lang="rust", bind="s")
                .case("s >= 0", "s * 2", label="x2", id="x2")).build()

    h1 = mk()
    key1 = h1.graph_key
    assert isinstance(key1, str) and key1
    dump = _GRAPH_CACHE / f"{key1}.graphdump"
    h1.materialize()
    assert dump.exists()
    mtime = dump.stat().st_mtime_ns
    # Identical inputs → same content address; the dump is reused, the native
    # binary is not re-run, so the file is not rewritten.
    h2 = mk()
    assert h2.graph_key == key1
    assert dump.stat().st_mtime_ns == mtime
    assert h1 == h2


# --- Phase 1b: native .vitgraph writer (no Python materialization) -----------

@rustc
def test_rust_native_vitgraph_matches_python(tmp_path):
    pytest.importorskip("pyarrow")
    from visiter import Graph, _accel
    if not _accel.native_available():
        pytest.skip("native engine (visiter_native) not installed")

    def mk():
        return (viter([1], max_depth=8, max_nodes=None, lang="rust", bind="s")
                .case("s >= 0", "s * 2", label="x2", id="x2")
                .case("s % 3 == 0", "s + 1", label="p1", id="p1")).build()

    # Native writer: straight from the dump; the handle must stay unmaterialized.
    h = mk()
    native_path = tmp_path / "native.vitgraph"
    h.to_vitgraph(str(native_path))
    assert h.is_materialized is False
    g_native = Graph.from_vitgraph(str(native_path))

    # Python reference: materialize, then write via the pure-Python storage
    # path (a plain Graph copy carries no native writer).
    ref = Graph(dict(mk().materialize()))
    py_path = tmp_path / "py.vitgraph"
    ref.to_vitgraph(str(py_path))
    g_py = Graph.from_vitgraph(str(py_path))

    assert g_native == g_py


# --- Phase 2: native view query (subset render without full materialization) -

@rustc
def test_rust_native_view_dot_parity():
    pytest.importorskip("pyarrow")
    from visiter import _accel
    if not _accel.native_available():
        pytest.skip("native engine (visiter_native) not installed")

    def mk():
        return (viter([1], max_depth=10, max_nodes=None, lang="rust", bind="s")
                .case("s >= 1", "s * 2", label="x2", id="x2")
                .case("(s - 1) % 3 == 0 && (s - 1) / 3 > 1 "
                      "&& ((s - 1) / 3) % 2 == 1",
                      "(s - 1) / 3", label="d3", id="d3")).build()

    anchor, radius = "8", 2
    for direction in ("both", "forward", "backward"):
        # Reference: full materialization + Python crop.
        ref = mk().materialize().to_dot(anchor=anchor, radius=radius,
                                        direction=direction)
        # Native fast path: the handle must stay unmaterialized and yield the
        # byte-identical DOT (including ghost stubs at the boundary).
        h = mk()
        got = h.to_dot(anchor=anchor, radius=radius, direction=direction)
        assert h.is_materialized is False
        assert got.source == ref.source


@rustc
def test_rust_view_returns_neighborhood_subgraph():
    pytest.importorskip("pyarrow")
    from visiter import _accel
    if not _accel.native_available():
        pytest.skip("native engine (visiter_native) not installed")
    h = (viter([1], max_depth=10, max_nodes=None, lang="rust", bind="s")
         .case("s >= 1", "s * 2", label="x2", id="x2")).build()
    view = h.view("4", 1, "both")
    # Neighborhood of 4 within 1 hop (undirected): {2, 4, 8} kept; 1 and 16 are
    # boundary (direct neighbors), so present as nodes but reachable only at the
    # cut. The kept set is what a radius-1 crop renders.
    assert h.is_materialized is False
    assert "4" in view["nodes"] and "8" in view["nodes"] and "2" in view["nodes"]


@rustc
def test_rust_native_crop_dot_parity_all_modes():
    # The native crop fast path must reproduce the full-materialize + Python-crop
    # DOT byte-for-byte for EVERY crop mode and combination — not just
    # anchor/radius — without materializing the handle.
    pytest.importorskip("pyarrow")
    from visiter import _accel
    if not _accel.native_available():
        pytest.skip("native engine (visiter_native) not installed")

    def mk():
        return (viter([1], max_depth=12, max_nodes=None, lang="rust", bind="s")
                .case("s >= 1", "s * 2", label="x2", id="x2")
                .case("(s - 1) % 3 == 0 && (s - 1) / 3 > 1 "
                      "&& ((s - 1) / 3) % 2 == 1",
                      "(s - 1) / 3", label="d3", id="d3")).build()

    specs = [
        dict(max_depth=4),                                              # depth only
        dict(value_range=(1, 64)),                                      # range only
        dict(anchor="8", radius=2, direction="both"),                  # nbhd only
        dict(anchor="8", radius=3, direction="both", max_depth=5),     # nbhd ∩ depth
        dict(anchor="16", radius=3, direction="forward",
             value_range=(1, 200)),                                    # nbhd ∩ range
        dict(max_depth=6, value_range=(1, 100)),                       # depth ∩ range
        dict(anchor="8", radius=4, direction="both", max_depth=6,
             value_range=(1, 300)),                                    # all three
    ]
    for spec in specs:
        ref = mk().materialize().to_dot(**spec)
        h = mk()
        got = h.to_dot(**spec)
        assert h.is_materialized is False, f"handle materialized for {spec}"
        assert got.source == ref.source, f"DOT mismatch for {spec}"
