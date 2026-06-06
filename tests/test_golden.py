"""Golden-hash cross-engine guard.

Pins the exact byte-shape of a fixed build so that an *unintended* change to the
output is caught (the test breaks → update the constant consciously, bumping
``rustgen._SEMANTICS_EPOCH`` if the cache must invalidate too). It also asserts
the three execution paths — pure Python, the native PyO3 engine, and the
``lang="rust"`` codegen — agree byte-for-byte, guarding the path-divergence class
of bug (the 0.17.0 dedup fix that missed ``rustgen.py``).
"""
import hashlib
import json
import shutil

import pytest

from visiter import viter

# sha256 of json.dumps(graph, sort_keys=True, default=str) for the fixed build
# below. Regenerate intentionally (and bump _SEMANTICS_EPOCH) if output changes.
GOLDEN = "88a0b6492b4f3fe91bfdbdd238534c30b1f00ee30869a26f16e8f42f26f6bb9b"

rustc = pytest.mark.skipif(
    shutil.which("rustc") is None, reason="rustc not on PATH")


def _hash(graph):
    return hashlib.sha256(
        json.dumps(graph, sort_keys=True, default=str).encode()).hexdigest()


def _python_build():
    return (viter(10, max_depth=None, max_nodes=None, engine="python")
            .case(lambda n: n >= 1, lambda n: n - 1, label="t1", id="o1")
            .case(lambda n: n >= 2, lambda n: n - 2, label="t2", id="o2")).build()


def _rust_build():
    return (viter(10, max_depth=None, max_nodes=None, lang="rust", bind="s")
            .case("s >= 1", "s - 1", label="t1", id="o1")
            .case("s >= 2", "s - 2", label="t2", id="o2")).build()


def test_golden_pure_python():
    assert _hash(_python_build()) == GOLDEN


def test_golden_native_engine_matches():
    from visiter import _accel
    if not _accel.native_available():
        pytest.skip("native engine (visiter_native) not installed")
    g = (viter(10, max_depth=None, max_nodes=None, engine="native")
         .case(lambda n: n >= 1, lambda n: n - 1, label="t1", id="o1")
         .case(lambda n: n >= 2, lambda n: n - 2, label="t2", id="o2")).build()
    assert _hash(g) == GOLDEN


@rustc
def test_golden_rust_codegen_matches():
    # Materialize the lazy handle to a plain dict before hashing.
    assert _hash(dict(_rust_build().materialize())) == GOLDEN
