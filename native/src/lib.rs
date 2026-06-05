//! Optional native BFS engine for visiter (Path A / ①).
//!
//! `build_raw` mirrors the pure-Python `visiter.iteration.build` BFS for the
//! **unbounded** subset (no max_depth / max_nodes / time_limit / bound). It
//! calls the Python condition/op callables per node, so the callbacks stay
//! Python — only the BFS expansion, deduplication and interning run natively.
//!
//! It returns the raw discovered structure (node objects in BFS order, their
//! depths, and deduplicated edges as `(from_idx, to_idx, op_idx, label?)`).
//! The Python shim assembles the final Graph dict (string keys, key_type,
//! tags, op labels) from this, so the output is byte-identical to the
//! pure-Python build for the supported subset.
//!
//! Node order, edge order, depth assignment and dedup semantics are kept
//! faithful to the Python loop so a Graph-level parity test passes exactly.

use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};

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
        Python::with_gil(|py| {
            self.obj.bind(py).eq(other.obj.bind(py)).unwrap_or(false)
        })
    }
}
impl Eq for Key {}

type Edge = (u32, u32, usize, Option<String>);

/// Run the unbounded BFS natively. `op_result_type` is the Python `OpResult`
/// class, used to detect per-call label overrides.
#[pyfunction]
#[pyo3(signature = (starts, conditions, ops, exclusive, default_op, op_result_type))]
fn build_raw(
    py: Python<'_>,
    starts: Vec<Py<PyAny>>,
    conditions: Vec<Py<PyAny>>,
    ops: Vec<Py<PyAny>>,
    exclusive: Vec<bool>,
    default_op: Option<Py<PyAny>>,
    op_result_type: Py<PyAny>,
) -> PyResult<(Vec<Py<PyAny>>, Vec<u32>, Vec<Edge>)> {
    let n_rules = conditions.len();
    let default_idx = n_rules; // op index reserved for the default op
    let ort = op_result_type.bind(py);

    let mut id_of: HashMap<Key, u32> = HashMap::new();
    let mut values: Vec<Py<PyAny>> = Vec::new();
    let mut depths: Vec<u32> = Vec::new();
    let mut edges: Vec<Edge> = Vec::new();
    let mut seen_edges: HashSet<(u32, u32)> = HashSet::new();

    // `fire` is a macro (not a fn) so it can mutate the locals in place without
    // fighting the borrow checker over a dozen &mut parameters.
    macro_rules! fire {
        ($xid:expr, $xb:expr, $op_idx:expr, $op_func:expr, $next:expr) => {{
            let result = $op_func.bind(py).call1(($xb,))?;
            let (nv, label): (Py<PyAny>, Option<String>) =
                if result.is_instance(ort)? {
                    let v = result.getattr("value")?.unbind();
                    let l: Option<String> = result.getattr("label")?.extract()?;
                    (v, l)
                } else {
                    (result.unbind(), None)
                };
            let h = nv.bind(py).hash()?;
            let key = Key { obj: nv.clone_ref(py), hash: h };
            let (nid, is_new) = match id_of.get(&key) {
                Some(&i) => (i, false),
                None => {
                    let i = values.len() as u32;
                    values.push(nv);
                    depths.push(depths[$xid as usize] + 1);
                    id_of.insert(key, i);
                    (i, true)
                }
            };
            if seen_edges.insert(($xid, nid)) {
                edges.push(($xid, nid, $op_idx, label));
            }
            if is_new {
                $next.push(nid);
            }
        }};
    }

    let mut frontier: Vec<u32> = Vec::new();
    for s in starts {
        let h = s.bind(py).hash()?;
        let key = Key { obj: s.clone_ref(py), hash: h };
        if !id_of.contains_key(&key) {
            let id = values.len() as u32;
            values.push(s);
            depths.push(0);
            id_of.insert(key, id);
            frontier.push(id);
        }
    }

    while !frontier.is_empty() {
        let mut next: Vec<u32> = Vec::new();
        for &xid in &frontier {
            let x = values[xid as usize].clone_ref(py);
            let xb = x.bind(py);
            let mut any_matched = false;
            for ri in 0..n_rules {
                if conditions[ri].bind(py).call1((xb,))?.is_truthy()? {
                    any_matched = true;
                    fire!(xid, xb, ri, ops[ri], next);
                    if exclusive[ri] {
                        break;
                    }
                }
            }
            if !any_matched {
                if let Some(ref dop) = default_op {
                    fire!(xid, xb, default_idx, dop, next);
                }
            }
        }
        frontier = next;
    }

    Ok((values, depths, edges))
}

#[pymodule]
fn visiter_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(build_raw, m)?)?;
    m.add("__version__", "0.0.0")?;
    Ok(())
}
