"""Path B: inline Rust-expression callbacks, compiled on the fly.

When a chain is started with ``viter(..., lang="rust")``, the ``.case()`` /
``.default()`` arguments are **Rust expression strings** (the current value is
bound to ``s``) instead of Python callables. At ``.build()`` time the
expressions are spliced into a fixed Rust BFS engine, compiled once with
``rustc`` (cached on a hash of the generated source), and run natively. The
result is materialised into the same Graph dict the pure-Python build produces.

This keeps the callbacks **co-located** at the call site (the expression *is*
the edge label) while running them as native code — the big win for
expensive-callback graphs. ``rustc`` must be on PATH; there is no Python
fallback for Rust source, so use ``lang="python"`` in toolchain-less
environments.

v1 scope: ``int`` or ``tuple``-of-ints state values (inferred from the start
values), ``consts`` (i64), ``key_type`` override, ``Match.ALL`` / ``Match.FIRST``
(exclusive), and **unbounded** expansion only (no max_depth / max_nodes /
time_limit / bound / tags / OpResult yet — those stay on the Python path).
"""
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

_CACHE = Path(tempfile.gettempdir()) / "visiter-rustgen-cache"

_TEMPLATE = """\
#![allow(unused, non_upper_case_globals)]
use std::collections::{{HashMap, HashSet, VecDeque}};
use std::io::Write;

type V = {rust_type};
{consts}

{callbacks}

#[inline(always)]
fn key(s: V) -> String {{ {keyfmt} }}

fn main() {{
    let out = std::env::args().nth(1).unwrap();
    let starts: Vec<V> = vec![{starts}];

    let mut id_of: HashMap<V, u32> = HashMap::new();
    let mut values: Vec<V> = Vec::new();
    let mut depths: Vec<u32> = Vec::new();
    let mut edges: Vec<(u32, u32, usize)> = Vec::new();
    let mut seen_edges: HashSet<(u32, u32)> = HashSet::new();

    macro_rules! visit {{
        ($xid:expr, $nv:expr, $op:expr) => {{{{
            let nv = $nv;
            let (nid, is_new) = match id_of.get(&nv) {{
                Some(&i) => (i, false),
                None => {{
                    let i = values.len() as u32;
                    id_of.insert(nv, i);
                    values.push(nv);
                    depths.push(depths[$xid as usize] + 1);
                    (i, true)
                }}
            }};
            if seen_edges.insert(($xid, nid)) {{ edges.push(($xid, nid, $op)); }}
            (nid, is_new)
        }}}};
    }}

    let mut frontier: Vec<u32> = Vec::new();
    for s in starts {{
        if !id_of.contains_key(&s) {{
            let id = values.len() as u32;
            id_of.insert(s, id);
            values.push(s);
            depths.push(0);
            frontier.push(id);
        }}
    }}

    while !frontier.is_empty() {{
        let mut next: Vec<u32> = Vec::new();
        for &xid in &frontier {{
            let s = values[xid as usize];
            let mut matched = false;
            'cases: {{
{cases_body}
            }}
        }}
        frontier = next;
    }}

    let mut f = std::io::BufWriter::new(std::fs::File::create(&out).unwrap());
    writeln!(f, "{{}}", values.len()).unwrap();
    for i in 0..values.len() {{
        writeln!(f, "{{}}\\t{{}}", depths[i], key(values[i])).unwrap();
    }}
    writeln!(f, "{{}}", edges.len()).unwrap();
    for &(a, b, o) in &edges {{
        writeln!(f, "{{}}\\t{{}}\\t{{}}", a, b, o).unwrap();
    }}
}}
"""


def _value_type(sample):
    """Infer the Rust value type from a start value. Returns
    ``(rust_type, key_format_expr, render_start_fn, json_type)``."""
    if isinstance(sample, bool):
        raise ValueError("lang='rust' does not support bool state values")
    if isinstance(sample, int):
        return "i64", 'format!("{}", s)', lambda v: f"{v}i64", "integer"
    if (isinstance(sample, tuple) and len(sample) >= 2
            and all(isinstance(x, int) and not isinstance(x, bool)
                    for x in sample)):
        k = len(sample)
        rust_type = "(" + ", ".join(["i64"] * k) + ")"
        placeholders = ", ".join("{}" for _ in range(k))
        accessors = ", ".join(f"s.{i}" for i in range(k))
        keyfmt = f'format!("({placeholders})", {accessors})'
        render = lambda v: "(" + ", ".join(f"{x}i64" for x in v) + ")"
        return rust_type, keyfmt, render, "array"
    raise ValueError(
        "lang='rust' supports int or tuple-of-ints (arity >= 2) start values; "
        f"got {type(sample).__name__} {sample!r}")


def _render_source(starts, cases, default, consts, value_type):
    rust_type, keyfmt, render_start, _jtype = value_type
    const_lines = "\n".join(f"const {k}: i64 = {v};" for k, v in consts.items())

    cb, body = [], []
    for i, (cond, op, _label, _id, exclusive) in enumerate(cases):
        cb.append(f"#[inline(always)] fn cond{i}(s: V) -> bool {{ ({cond}) }}")
        cb.append(f"#[inline(always)] fn op{i}(s: V) -> V {{ ({op}) }}")
        line = (f"                if cond{i}(s) {{ matched = true; "
                f"let (nid, isn) = visit!(xid, op{i}(s), {i}); "
                f"if isn {{ next.push(nid); }}")
        line += " break 'cases; }" if exclusive else " }"
        body.append(line)

    if default is not None:
        dop, _dl, _did = default
        di = len(cases)
        cb.append(f"#[inline(always)] fn opd(s: V) -> V {{ ({dop}) }}")
        body.append(
            f"                if !matched {{ let (nid, isn) = "
            f"visit!(xid, opd(s), {di}); if isn {{ next.push(nid); }} }}")

    return _TEMPLATE.format(
        rust_type=rust_type,
        consts=const_lines,
        callbacks="\n".join(cb),
        keyfmt=keyfmt,
        starts=", ".join(render_start(s) for s in starts),
        cases_body="\n".join(body),
    )


def _compile(source):
    """Compile *source* to a cached binary; return its path. Cached on hash."""
    if shutil.which("rustc") is None:
        raise RuntimeError(
            "lang='rust' needs the Rust compiler (rustc) on PATH. Install Rust "
            "(https://rustup.rs) or use lang='python'.")
    _CACHE.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(source.encode()).hexdigest()[:16]
    binary = _CACHE / h
    if not binary.exists():
        src = _CACHE / f"{h}.rs"
        src.write_text(source)
        subprocess.run(
            ["rustc", "--edition", "2021", "-C", "opt-level=3",
             "-C", "codegen-units=1", "-o", str(binary), str(src)],
            check=True, capture_output=True, text=True)
    return binary


def _parse_result(text, cases, default, op_ids, op_labels, key_type, jtype,
                  starts):
    from .graph import Graph
    lines = text.splitlines()
    pos = 0
    n_nodes = int(lines[pos]); pos += 1
    keys = []
    nodes = {}
    kt = key_type if key_type is not None else jtype
    for _ in range(n_nodes):
        depth_s, key_s = lines[pos].split("\t", 1); pos += 1
        keys.append(key_s)
        nodes[key_s] = {"depth": int(depth_s), "key_type": kt}
    n_edges = int(lines[pos]); pos += 1
    edges = []
    for _ in range(n_edges):
        a, b, o = lines[pos].split("\t"); pos += 1
        oi = int(o)
        edges.append({"from": keys[int(a)], "to": keys[int(b)],
                      "op": op_ids[oi], "label": op_labels[op_ids[oi]]})
    op_order = []
    seen = set()
    for oid in op_ids:
        if oid not in seen:
            seen.add(oid)
            op_order.append(oid)
    return Graph({
        "schema_version": "1",
        "roots": list(starts),
        "nodes": nodes,
        "edges": edges,
        "pseudo_edges": [],
        "op_order": op_order,
        "op_labels": {oid: op_labels[oid] for oid in op_order},
    })


def build_rust(starts, cases, default, *, consts=None, key_type=None):
    """Compile the Rust-string cases and run the native BFS → Graph.

    *cases* is a list of ``(cond_str, op_str, label, id, exclusive)``; *default*
    is ``(op_str, label, id)`` or None. ``label``/``id`` default to the op
    string (the expression is the label).
    """
    consts = consts or {}
    if not starts:
        raise ValueError("lang='rust' needs at least one start value")
    value_type = _value_type(starts[0])
    jtype = value_type[3]

    # Resolve label/id: default to the op expression itself.
    norm_cases = []
    op_ids = []          # op index -> id (rules then default)
    op_labels = {}
    for cond, op, label, id_, exclusive in cases:
        oid = id_ if id_ is not None else op
        lab = label if label is not None else op
        norm_cases.append((cond, op, lab, oid, exclusive))
        op_ids.append(oid)
        op_labels.setdefault(oid, lab)
    norm_default = None
    if default is not None:
        dop, dlabel, did = default
        oid = did if did is not None else dop
        lab = dlabel if dlabel is not None else dop
        norm_default = (dop, lab, oid)
        op_ids.append(oid)
        op_labels.setdefault(oid, lab)

    source = _render_source(starts, norm_cases, norm_default, consts, value_type)
    binary = _compile(source)
    with tempfile.NamedTemporaryFile(mode="r", suffix=".graph") as tf:
        subprocess.run([str(binary), tf.name], check=True,
                       capture_output=True, text=True)
        text = Path(tf.name).read_text()
    return _parse_result(text, norm_cases, norm_default, op_ids, op_labels,
                         key_type, jtype, starts)
