//! Optional native BFS engine for visiter (Path A / ①).
//!
//! `build_raw` mirrors the pure-Python `visiter.iteration.build` BFS — now
//! including the bounded subset (`max_depth` / `max_nodes` / `time_limit` /
//! per-rule `bound`). It calls the Python condition/op/bound callables per
//! node, so the callbacks stay Python — only the BFS expansion, deduplication,
//! interning, depth/node/time gating and pseudo-edge bookkeeping run natively.
//!
//! It returns the raw discovered structure (node objects in BFS order, their
//! depths, deduplicated edges as `(from_idx, to_idx, op_idx, label?)`,
//! deduplicated pseudo-edges as `(from_idx, op_idx)`, a `depth_limited` flag
//! and an optional `(kind, context)` stop record for node/time truncation).
//! The Python shim assembles the final Graph dict (string keys, key_type,
//! tags, op labels, pseudo-edges) and emits the truncation warnings / raises,
//! so the output is byte-identical to the pure-Python build for the
//! deterministic limits (`max_depth` / `max_nodes` / `bound`). `time_limit` is
//! best-effort: it terminates and truncates, but the cut point is wall-clock
//! dependent, so byte-parity is not guaranteed (the pure-Python path diverges
//! the same way).
//!
//! Node order, edge order, depth assignment, pseudo-edge order and dedup
//! semantics are kept faithful to the Python loop so a Graph-level parity test
//! passes exactly for the deterministic limits.

use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};
use std::time::{Duration, Instant};

/// A Python object used as a node key: hashed by the value's Python `hash()`
/// (computed once), equality resolved by Python `==` only on hash collision.
struct Key {
    obj: Py<PyAny>,
    hash: isize,
}

impl std::hash::Hash for Key {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        state.write_isize(self.hash);
    }
}

impl PartialEq for Key {
    fn eq(&self, other: &Self) -> bool {
        if self.hash != other.hash {
            return false;
        }
        Python::with_gil(|py| self.obj.bind(py).eq(other.obj.bind(py)).unwrap_or(false))
    }
}
impl Eq for Key {}

type Edge = (u32, u32, usize, Option<String>);
type Pseudo = (u32, usize);
type BuildResult = (
    Vec<Py<PyAny>>,           // values (node objects, BFS order)
    Vec<u32>,                 // depths (parallel to values)
    Vec<Edge>,                // real edges
    Vec<Pseudo>,              // pseudo-edges (from_idx, op_idx)
    bool,                     // depth_limited
    Option<(String, String)>, // stop: (kind, context) for max_nodes/time_limit
);

/// Run the BFS natively. `op_result_type` is the Python `OpResult` class, used
/// to detect per-call label overrides. `bounds[ri]` is an optional Python
/// predicate for rule `ri`; `max_depth`/`max_nodes`/`time_limit_secs` gate the
/// expansion (any of them may be `None` to disable that limit).
#[pyfunction]
#[pyo3(signature = (starts, conditions, ops, bounds, exclusive, default_op,
                    op_result_type, max_depth, max_nodes, time_limit_secs))]
#[allow(clippy::too_many_arguments)]
fn build_raw(
    py: Python<'_>,
    starts: Vec<Py<PyAny>>,
    conditions: Vec<Py<PyAny>>,
    ops: Vec<Py<PyAny>>,
    bounds: Vec<Option<Py<PyAny>>>,
    exclusive: Vec<bool>,
    default_op: Option<Py<PyAny>>,
    op_result_type: Py<PyAny>,
    max_depth: Option<u32>,
    max_nodes: Option<usize>,
    time_limit_secs: Option<f64>,
) -> PyResult<BuildResult> {
    let n_rules = conditions.len();
    let default_idx = n_rules; // op index reserved for the default op
    let ort = op_result_type.bind(py);

    let mut id_of: HashMap<Key, u32> = HashMap::new();
    let mut values: Vec<Py<PyAny>> = Vec::new();
    let mut depths: Vec<u32> = Vec::new();
    let mut edges: Vec<Edge> = Vec::new();
    let mut seen_edges: HashSet<(u32, u32, usize)> = HashSet::new();
    let mut pseudo: Vec<Pseudo> = Vec::new();
    let mut seen_pseudo: HashSet<(u32, usize)> = HashSet::new();
    let mut depth_limited = false;
    let mut stop: Option<(String, String)> = None;

    let deadline = time_limit_secs.map(|s| Instant::now() + Duration::from_secs_f64(s));

    // `fire` is a macro (not a fn) so it can mutate the locals in place without
    // fighting the borrow checker over a dozen &mut parameters. On a new node
    // it checks the time/node limit *before* creating it (mirroring the Python
    // `fire`/`limit_reason` order). It expands to `true` iff a limit was hit;
    // the caller then `break 'build`s (the label can't be referenced from
    // inside the macro body due to macro hygiene, so the break stays outside).
    macro_rules! fire {
        ($xid:expr, $xb:expr, $op_idx:expr, $op_func:expr, $next:expr) => {{
            let result = $op_func.bind(py).call1(($xb,))?;
            let (nv, label): (Py<PyAny>, Option<String>) = if result.is_instance(ort)? {
                let v = result.getattr("value")?.unbind();
                let l: Option<String> = result.getattr("label")?.extract()?;
                (v, l)
            } else {
                (result.unbind(), None)
            };
            let h = nv.bind(py).hash()?;
            let key = Key {
                obj: nv.clone_ref(py),
                hash: h,
            };
            let mut limit_hit = false;
            let nid = match id_of.get(&key) {
                Some(&i) => Some(i),
                None => {
                    // New node: gate on time/node limits before creating it.
                    let hit_time = deadline.map_or(false, |dl| Instant::now() >= dl);
                    let hit_nodes = max_nodes.map_or(false, |mn| values.len() >= mn);
                    if hit_time || hit_nodes {
                        let kind = if hit_time { "time_limit" } else { "max_nodes" };
                        let ctx = format!("at value={}", nv.bind(py).str()?);
                        stop = Some((kind.to_string(), ctx));
                        limit_hit = true;
                        None
                    } else {
                        let i = values.len() as u32;
                        values.push(nv);
                        depths.push(depths[$xid as usize] + 1);
                        id_of.insert(key, i);
                        $next.push(i);
                        Some(i)
                    }
                }
            };
            if let Some(nid) = nid {
                // Key on (from, to, op): distinct ops to the same successor are
                // distinct edges. Python re-dedups on the resolved op.id so two
                // rule indices sharing one id still collapse like pure Python.
                if seen_edges.insert(($xid, nid, $op_idx)) {
                    edges.push(($xid, nid, $op_idx, label));
                }
            }
            limit_hit
        }};
    }

    'build: {
        let mut frontier: Vec<u32> = Vec::new();
        for s in starts.iter() {
            let h = s.bind(py).hash()?;
            let key = Key {
                obj: s.clone_ref(py),
                hash: h,
            };
            if id_of.contains_key(&key) {
                continue;
            }
            // Gate the start nodes too (Python checks the limit before each).
            let hit_time = deadline.is_some_and(|dl| Instant::now() >= dl);
            let hit_nodes = max_nodes.is_some_and(|mn| values.len() >= mn);
            if hit_time || hit_nodes {
                let kind = if hit_time { "time_limit" } else { "max_nodes" };
                let ctx = format!("before start={}", s.bind(py).str()?);
                stop = Some((kind.to_string(), ctx));
                break 'build;
            }
            let id = values.len() as u32;
            values.push(s.clone_ref(py));
            depths.push(0);
            id_of.insert(key, id);
            frontier.push(id);
        }

        while !frontier.is_empty() {
            let mut next: Vec<u32> = Vec::new();
            for &xid in &frontier {
                let d = depths[xid as usize];
                let at_max = max_depth.is_some_and(|md| d >= md);
                if at_max {
                    depth_limited = true;
                }
                let x = values[xid as usize].clone_ref(py);
                let xb = x.bind(py);
                let mut any_matched = false;
                for ri in 0..n_rules {
                    if conditions[ri].bind(py).call1((xb,))?.is_truthy()? {
                        any_matched = true;
                        // At max depth, or condition-true-but-bound-false, the
                        // op does not fire: record a pseudo-edge instead.
                        let bounded_out = if at_max {
                            true
                        } else if let Some(ref b) = bounds[ri] {
                            !b.bind(py).call1((xb,))?.is_truthy()?
                        } else {
                            false
                        };
                        if bounded_out {
                            if seen_pseudo.insert((xid, ri)) {
                                pseudo.push((xid, ri));
                            }
                            if exclusive[ri] {
                                break;
                            }
                            continue;
                        }
                        if fire!(xid, xb, ri, ops[ri], next) {
                            break 'build;
                        }
                        if exclusive[ri] {
                            break;
                        }
                    }
                }
                if !any_matched {
                    if let Some(ref dop) = default_op {
                        if at_max {
                            if seen_pseudo.insert((xid, default_idx)) {
                                pseudo.push((xid, default_idx));
                            }
                        } else if fire!(xid, xb, default_idx, dop, next) {
                            break 'build;
                        }
                    }
                }
            }
            frontier = next;
        }
    }

    Ok((values, depths, edges, pseudo, depth_limited, stop))
}

#[pymodule]
fn visiter_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(build_raw, m)?)?;
    m.add("__version__", "0.2.0")?;
    Ok(())
}
