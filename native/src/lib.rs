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

use std::fs::File;
use std::io::{Cursor, Read, Write};
use std::sync::Arc;

use arrow_array::builder::{ListBuilder, StringBuilder};
use arrow_array::{Array, ArrayRef, Int32Array, ListArray, RecordBatch, StringArray};
use arrow_ipc::reader::FileReader;
use arrow_ipc::writer::{FileWriter, IpcWriteOptions};
use arrow_ipc::CompressionType;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, ZipArchive, ZipWriter};

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

// ---------------------------------------------------------------------------
// Native .vitgraph writer (Path B / lang="rust").
//
// Reads the lean dump that the generated rustc program writes (the same format
// `visiter.rustgen` parses) and emits the columnar `.vitgraph` store — Arrow
// IPC (file format, zstd-compressed) for the nodes/edges/pseudo tables plus a
// meta.json, in a stored (uncompressed) zip container, exactly the layout
// `visiter.storage` produces. Doing this natively avoids materializing the
// full graph into a Python dict first (the whole point: no round-trip wall).
//
// Op indices are resolved to op ids and labels via tables passed from Python
// (`op_ids`, `op_default_labels`), and edges/pseudo-edges are re-deduplicated
// on the *resolved* op id — byte-for-byte the same dedup `rustgen.build_rust`
// does — so distinct rule indices sharing one op id collapse like pure Python.
// ---------------------------------------------------------------------------

fn err<E: std::fmt::Display>(e: E) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

struct DumpReader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> DumpReader<'a> {
    fn line(&mut self) -> PyResult<&'a [u8]> {
        let start = self.pos;
        while self.pos < self.data.len() && self.data[self.pos] != b'\n' {
            self.pos += 1;
        }
        if self.pos >= self.data.len() {
            return Err(err("unexpected end of dump"));
        }
        let out = &self.data[start..self.pos];
        self.pos += 1; // consume the newline
        Ok(out)
    }

    fn blob(&mut self, n: usize) -> PyResult<&'a str> {
        if self.pos + n > self.data.len() {
            return Err(err("unexpected end of dump (blob)"));
        }
        let out = std::str::from_utf8(&self.data[self.pos..self.pos + n]).map_err(err)?;
        self.pos += n + 1; // skip the trailing newline
        Ok(out)
    }
}

fn parse_one(line: &[u8]) -> PyResult<i64> {
    std::str::from_utf8(line).map_err(err)?.trim().parse::<i64>().map_err(err)
}

fn parse_ints(line: &[u8]) -> PyResult<Vec<i64>> {
    std::str::from_utf8(line)
        .map_err(err)?
        .split_whitespace()
        .map(|t| t.parse::<i64>().map_err(err))
        .collect()
}

fn write_ipc(batch: &RecordBatch) -> PyResult<Vec<u8>> {
    let mut buf: Vec<u8> = Vec::new();
    let opts = IpcWriteOptions::default()
        .try_with_compression(Some(CompressionType::ZSTD))
        .map_err(err)?;
    let schema = batch.schema();
    {
        let mut w =
            FileWriter::try_new_with_options(&mut buf, schema.as_ref(), opts).map_err(err)?;
        w.write(batch).map_err(err)?;
        w.finish().map_err(err)?;
    }
    Ok(buf)
}

#[pyfunction]
#[pyo3(signature = (dump_path, out_path, key_type, tag_names, op_ids,
                    op_default_labels, roots_json, op_order, op_labels_json,
                    schema_version))]
#[allow(clippy::too_many_arguments)]
fn dump_to_vitgraph(
    dump_path: &str,
    out_path: &str,
    key_type: &str,
    tag_names: Vec<String>,
    op_ids: Vec<String>,
    op_default_labels: Vec<String>,
    roots_json: &str,
    op_order: Vec<String>,
    op_labels_json: &str,
    schema_version: &str,
) -> PyResult<()> {
    let bytes = std::fs::read(dump_path).map_err(err)?;
    let mut r = DumpReader { data: &bytes, pos: 0 };

    // --- nodes ---
    let n_nodes = parse_one(r.line()?)? as usize;
    let mut keys: Vec<String> = Vec::with_capacity(n_nodes);
    let mut depths: Vec<i32> = Vec::with_capacity(n_nodes);
    let mut node_tags: Vec<Vec<String>> = Vec::with_capacity(n_nodes);
    for _ in 0..n_nodes {
        let parts = parse_ints(r.line()?)?; // depth, tagbits, klen
        let depth = parts[0] as i32;
        let tagbits = parts[1] as u32;
        let klen = parts[2] as usize;
        let key = r.blob(klen)?.to_string();
        depths.push(depth);
        let mut tags = Vec::new();
        for (j, name) in tag_names.iter().enumerate() {
            if tagbits & (1u32 << j) != 0 {
                tags.push(name.clone());
            }
        }
        node_tags.push(tags);
        keys.push(key);
    }

    // --- edges (dedup on (from, to, resolved op id)) ---
    let n_edges = parse_one(r.line()?)? as usize;
    let mut e_src: Vec<i32> = Vec::new();
    let mut e_dst: Vec<i32> = Vec::new();
    let mut e_op: Vec<String> = Vec::new();
    let mut e_label: Vec<String> = Vec::new();
    let mut seen_e: HashSet<(i64, i64, String)> = HashSet::new();
    for _ in 0..n_edges {
        let parts = parse_ints(r.line()?)?; // a, b, o, llen
        let (a, b, o, llen) = (parts[0], parts[1], parts[2] as usize, parts[3]);
        let label = if llen >= 0 {
            r.blob(llen as usize)?.to_string()
        } else {
            op_default_labels[o].clone()
        };
        let oid = op_ids[o].clone();
        if seen_e.insert((a, b, oid.clone())) {
            e_src.push(a as i32);
            e_dst.push(b as i32);
            e_op.push(oid);
            e_label.push(label);
        }
    }

    // --- pseudo-edges (dedup on (from, resolved op id)) ---
    let n_pseudo = parse_one(r.line()?)? as usize;
    let mut p_src: Vec<i32> = Vec::new();
    let mut p_op: Vec<String> = Vec::new();
    let mut p_label: Vec<String> = Vec::new();
    let mut seen_p: HashSet<(i64, String)> = HashSet::new();
    for _ in 0..n_pseudo {
        let parts = parse_ints(r.line()?)?; // x, o
        let (x, o) = (parts[0], parts[1] as usize);
        let oid = op_ids[o].clone();
        if seen_p.insert((x, oid.clone())) {
            p_src.push(x as i32);
            p_op.push(oid);
            p_label.push(op_default_labels[o].clone());
        }
    }
    // The trailing depth_limited/trunc_reason/tkey lines are intentionally not
    // read: truncation warnings are emitted by the Python lean-dump path.

    let roots_val: serde_json::Value = serde_json::from_str(roots_json).map_err(err)?;
    let labels_val: serde_json::Value = serde_json::from_str(op_labels_json).map_err(err)?;
    let meta = serde_json::json!({
        "schema_version": schema_version,
        "roots": roots_val,
        "op_order": op_order,
        "op_labels": labels_val,
    });
    let meta_str = serde_json::to_string(&meta).map_err(err)?;

    let key_types = vec![key_type.to_string(); n_nodes];
    write_store(
        out_path, keys, depths, key_types, node_tags, e_src, e_dst, e_op, e_label,
        p_src, p_op, p_label, &meta_str,
    )
}

/// Build the columnar `.vitgraph` (Arrow IPC + zstd, in a stored zip) from
/// already-assembled column vectors. Shared by `dump_to_vitgraph` and the view
/// query so both produce the exact same on-disk layout `visiter.storage` reads.
#[allow(clippy::too_many_arguments)]
fn write_store(
    out_path: &str,
    keys: Vec<String>,
    depths: Vec<i32>,
    key_types: Vec<String>,
    node_tags: Vec<Vec<String>>,
    e_src: Vec<i32>,
    e_dst: Vec<i32>,
    e_op: Vec<String>,
    e_label: Vec<String>,
    p_src: Vec<i32>,
    p_op: Vec<String>,
    p_label: Vec<String>,
    meta_str: &str,
) -> PyResult<()> {
    let mut tags_builder = ListBuilder::new(StringBuilder::new());
    for tags in &node_tags {
        for t in tags {
            tags_builder.values().append_value(t);
        }
        tags_builder.append(true);
    }
    let nodes_batch = RecordBatch::try_from_iter(vec![
        ("key", Arc::new(StringArray::from(keys)) as ArrayRef),
        ("depth", Arc::new(Int32Array::from(depths)) as ArrayRef),
        ("key_type", Arc::new(StringArray::from(key_types)) as ArrayRef),
        ("tags", Arc::new(tags_builder.finish()) as ArrayRef),
    ])
    .map_err(err)?;
    let edges_batch = RecordBatch::try_from_iter(vec![
        ("src", Arc::new(Int32Array::from(e_src)) as ArrayRef),
        ("dst", Arc::new(Int32Array::from(e_dst)) as ArrayRef),
        ("op", Arc::new(StringArray::from(e_op)) as ArrayRef),
        ("label", Arc::new(StringArray::from(e_label)) as ArrayRef),
    ])
    .map_err(err)?;
    let pseudo_batch = RecordBatch::try_from_iter(vec![
        ("src", Arc::new(Int32Array::from(p_src)) as ArrayRef),
        ("op", Arc::new(StringArray::from(p_op)) as ArrayRef),
        ("label", Arc::new(StringArray::from(p_label)) as ArrayRef),
    ])
    .map_err(err)?;

    let nodes_ipc = write_ipc(&nodes_batch)?;
    let edges_ipc = write_ipc(&edges_batch)?;
    let pseudo_ipc = write_ipc(&pseudo_batch)?;

    let file = File::create(out_path).map_err(err)?;
    let mut zip = ZipWriter::new(file);
    let opts = SimpleFileOptions::default().compression_method(CompressionMethod::Stored);
    for (name, data) in [
        ("meta.json", meta_str.as_bytes()),
        ("nodes.arrow", nodes_ipc.as_slice()),
        ("edges.arrow", edges_ipc.as_slice()),
        ("pseudo.arrow", pseudo_ipc.as_slice()),
    ] {
        zip.start_file(name, opts).map_err(err)?;
        zip.write_all(data).map_err(err)?;
    }
    zip.finish().map_err(err)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Native view query (Path B / lang="rust").
//
// Reads a full `.vitgraph`, runs the same multi-source BFS neighborhood as
// `to_dot._bfs_neighborhood`, and writes a *subset* `.vitgraph` containing the
// kept nodes PLUS their direct edge-neighbors (the boundary). That boundary is
// exactly what `to_dot` needs to reproduce ghost stubs at the cut, so
// `to_dot(subset, anchor, radius, direction)` renders byte-for-byte the same
// DOT as `to_dot(full, …)` — without materializing the full graph in Python.
// ---------------------------------------------------------------------------

struct VitGraph {
    meta: String,
    keys: Vec<String>,
    depths: Vec<i32>,
    key_types: Vec<String>,
    node_tags: Vec<Vec<String>>,
    e_src: Vec<i32>,
    e_dst: Vec<i32>,
    e_op: Vec<String>,
    e_label: Vec<String>,
    p_src: Vec<i32>,
    p_op: Vec<String>,
    p_label: Vec<String>,
}

fn read_batch(buf: Vec<u8>) -> PyResult<RecordBatch> {
    let reader = FileReader::try_new(Cursor::new(buf), None).map_err(err)?;
    for b in reader {
        return b.map_err(err);
    }
    Err(err("empty arrow file"))
}

fn col_str<'a>(b: &'a RecordBatch, name: &str) -> PyResult<&'a StringArray> {
    b.column_by_name(name)
        .ok_or_else(|| err(format!("missing column {name}")))?
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| err(format!("column {name} is not Utf8")))
}

fn col_i32<'a>(b: &'a RecordBatch, name: &str) -> PyResult<&'a Int32Array> {
    b.column_by_name(name)
        .ok_or_else(|| err(format!("missing column {name}")))?
        .as_any()
        .downcast_ref::<Int32Array>()
        .ok_or_else(|| err(format!("column {name} is not Int32")))
}

fn read_vitgraph(path: &str) -> PyResult<VitGraph> {
    let mut archive = ZipArchive::new(File::open(path).map_err(err)?).map_err(err)?;
    let meta = {
        let mut f = archive.by_name("meta.json").map_err(err)?;
        let mut s = String::new();
        f.read_to_string(&mut s).map_err(err)?;
        s
    };
    let read_member = |archive: &mut ZipArchive<File>, name: &str| -> PyResult<Vec<u8>> {
        let mut f = archive.by_name(name).map_err(err)?;
        let mut b = Vec::new();
        f.read_to_end(&mut b).map_err(err)?;
        Ok(b)
    };
    let nodes_buf = read_member(&mut archive, "nodes.arrow")?;
    let edges_buf = read_member(&mut archive, "edges.arrow")?;
    let pseudo_buf = read_member(&mut archive, "pseudo.arrow")?;

    let nb = read_batch(nodes_buf)?;
    let keys_a = col_str(&nb, "key")?;
    let depth_a = col_i32(&nb, "depth")?;
    let kt_a = col_str(&nb, "key_type")?;
    let tags_a = nb
        .column_by_name("tags")
        .ok_or_else(|| err("missing column tags"))?
        .as_any()
        .downcast_ref::<ListArray>()
        .ok_or_else(|| err("column tags is not List"))?;
    let n = keys_a.len();
    let mut keys = Vec::with_capacity(n);
    let mut depths = Vec::with_capacity(n);
    let mut key_types = Vec::with_capacity(n);
    let mut node_tags = Vec::with_capacity(n);
    for i in 0..n {
        keys.push(keys_a.value(i).to_string());
        depths.push(depth_a.value(i));
        key_types.push(kt_a.value(i).to_string());
        let row = tags_a.value(i);
        let row = row
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| err("tags element is not Utf8"))?;
        node_tags.push((0..row.len()).map(|j| row.value(j).to_string()).collect());
    }

    let eb = read_batch(edges_buf)?;
    let es = col_i32(&eb, "src")?;
    let ed = col_i32(&eb, "dst")?;
    let eo = col_str(&eb, "op")?;
    let el = col_str(&eb, "label")?;
    let ne = es.len();
    let mut e_src = Vec::with_capacity(ne);
    let mut e_dst = Vec::with_capacity(ne);
    let mut e_op = Vec::with_capacity(ne);
    let mut e_label = Vec::with_capacity(ne);
    for i in 0..ne {
        e_src.push(es.value(i));
        e_dst.push(ed.value(i));
        e_op.push(eo.value(i).to_string());
        e_label.push(el.value(i).to_string());
    }

    let pb = read_batch(pseudo_buf)?;
    let ps = col_i32(&pb, "src")?;
    let po = col_str(&pb, "op")?;
    let pl = col_str(&pb, "label")?;
    let np = ps.len();
    let mut p_src = Vec::with_capacity(np);
    let mut p_op = Vec::with_capacity(np);
    let mut p_label = Vec::with_capacity(np);
    for i in 0..np {
        p_src.push(ps.value(i));
        p_op.push(po.value(i).to_string());
        p_label.push(pl.value(i).to_string());
    }

    Ok(VitGraph {
        meta,
        keys,
        depths,
        key_types,
        node_tags,
        e_src,
        e_dst,
        e_op,
        e_label,
        p_src,
        p_op,
        p_label,
    })
}

#[pyfunction]
#[pyo3(signature = (in_path, out_path, anchors, radius, direction))]
fn view_vitgraph(
    in_path: &str,
    out_path: &str,
    anchors: Vec<String>,
    radius: i64,
    direction: &str,
) -> PyResult<()> {
    if direction != "forward" && direction != "backward" && direction != "both" {
        return Err(PyValueError::new_err(format!(
            "direction must be 'forward', 'backward', or 'both'; got {direction:?}"
        )));
    }
    let vg = read_vitgraph(in_path)?;
    let n = vg.keys.len();
    let index_of: HashMap<&str, u32> =
        vg.keys.iter().enumerate().map(|(i, k)| (k.as_str(), i as u32)).collect();

    // Directional adjacency for the BFS, matching `_bfs_neighborhood`.
    let mut adj: Vec<Vec<u32>> = vec![Vec::new(); n];
    for i in 0..vg.e_src.len() {
        let (s, d) = (vg.e_src[i] as u32, vg.e_dst[i] as u32);
        if direction == "forward" || direction == "both" {
            adj[s as usize].push(d);
        }
        if direction == "backward" || direction == "both" {
            adj[d as usize].push(s);
        }
    }

    // Multi-source BFS bounded by radius (same expansion rule as Python).
    let mut dist: Vec<i64> = vec![-1; n];
    let mut frontier: Vec<u32> = Vec::new();
    for a in &anchors {
        let &idx = index_of
            .get(a.as_str())
            .ok_or_else(|| PyValueError::new_err(format!("anchor {a:?} is not a node in the graph")))?;
        if dist[idx as usize] < 0 {
            dist[idx as usize] = 0;
            frontier.push(idx);
        }
    }
    while !frontier.is_empty() {
        let mut nxt = Vec::new();
        for &v in &frontier {
            if dist[v as usize] >= radius {
                continue;
            }
            for &nb in &adj[v as usize] {
                if dist[nb as usize] < 0 {
                    dist[nb as usize] = dist[v as usize] + 1;
                    nxt.push(nb);
                }
            }
        }
        frontier = nxt;
    }
    let keep: Vec<bool> = dist.iter().map(|&d| d >= 0).collect();

    // Subset nodes = kept ∪ boundary (the non-kept endpoint of any edge with
    // exactly one endpoint kept). The boundary lets to_dot draw ghost stubs.
    let mut in_subset = keep.clone();
    for i in 0..vg.e_src.len() {
        let (s, d) = (vg.e_src[i] as usize, vg.e_dst[i] as usize);
        if keep[s] != keep[d] {
            in_subset[s] = true;
            in_subset[d] = true;
        }
    }

    // Old → new index map, preserving original node order.
    let mut new_id: Vec<i32> = vec![-1; n];
    let mut keys = Vec::new();
    let mut depths = Vec::new();
    let mut key_types = Vec::new();
    let mut node_tags = Vec::new();
    for i in 0..n {
        if in_subset[i] {
            new_id[i] = keys.len() as i32;
            keys.push(vg.keys[i].clone());
            depths.push(vg.depths[i]);
            key_types.push(vg.key_types[i].clone());
            node_tags.push(vg.node_tags[i].clone());
        }
    }

    // Subset edges = edges incident to a kept node (both endpoints are then in
    // the subset by construction), preserving original order.
    let mut e_src = Vec::new();
    let mut e_dst = Vec::new();
    let mut e_op = Vec::new();
    let mut e_label = Vec::new();
    for i in 0..vg.e_src.len() {
        let (s, d) = (vg.e_src[i] as usize, vg.e_dst[i] as usize);
        if keep[s] || keep[d] {
            e_src.push(new_id[s]);
            e_dst.push(new_id[d]);
            e_op.push(vg.e_op[i].clone());
            e_label.push(vg.e_label[i].clone());
        }
    }

    // Subset pseudo-edges = those from a kept node.
    let mut p_src = Vec::new();
    let mut p_op = Vec::new();
    let mut p_label = Vec::new();
    for i in 0..vg.p_src.len() {
        let s = vg.p_src[i] as usize;
        if keep[s] {
            p_src.push(new_id[s]);
            p_op.push(vg.p_op[i].clone());
            p_label.push(vg.p_label[i].clone());
        }
    }

    write_store(
        out_path, keys, depths, key_types, node_tags, e_src, e_dst, e_op, e_label,
        p_src, p_op, p_label, &vg.meta,
    )
}

#[pymodule]
fn visiter_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(build_raw, m)?)?;
    m.add_function(wrap_pyfunction!(dump_to_vitgraph, m)?)?;
    m.add_function(wrap_pyfunction!(view_vitgraph, m)?)?;
    m.add("__version__", "0.3.0")?;
    Ok(())
}
