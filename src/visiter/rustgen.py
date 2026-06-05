"""Path B: inline Rust-expression callbacks, compiled on the fly.

When a chain is started with ``viter(..., lang="rust")``, the ``.case()`` /
``.default()`` / ``bound=`` / ``tags=`` arguments are **Rust expression strings**
(the current value is bound to ``s``) instead of Python callables. At
``.build()`` time the expressions are spliced into a fixed Rust BFS engine,
compiled once with ``rustc`` (cached on a hash of the generated source), and run
natively. The resulting graph is byte-identical to the pure-Python build —
including default bounds, ghost-stub pseudo-edges, ``max_nodes`` truncation,
``tags`` and ``key_type``.

``rustc`` must be on PATH; there is no Python fallback for Rust source, so use
``lang="python"`` in toolchain-less environments.

Supported state values (inferred from the start values): ``int``, ``tuple`` of
ints (arity >= 2), ``str``, and ``Fraction`` (exact rationals via
``num-rational``/``num-bigint``, compiled through ``cargo``). ``OpResult``
(per-call labels) and ``time_limit`` are not yet supported — the Builder raises
rather than diverging silently.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import warnings
from fractions import Fraction
from pathlib import Path

_CACHE = Path(tempfile.gettempdir()) / "visiter-rustgen-cache"

# Rational state values need num-bigint/num-rational, which bare rustc cannot
# fetch, so they compile through cargo. The shared target dir means the deps
# compile once and are reused across every generated program.
_CARGO_TARGET = _CACHE / "cargo-target"
_CARGO_TOML = """\
[package]
name = "{name}"
version = "0.0.0"
edition = "2021"

[[bin]]
name = "{name}"
path = "main.rs"

[dependencies]
num-bigint = "0.4"
num-rational = "0.4"

[profile.release]
opt-level = 3
"""

_RATIONAL_PRELUDE = (
    "use num_bigint::BigInt;\n"
    "use num_rational::BigRational;\n"
    "#[inline(always)] fn r(n: i64) -> BigRational "
    "{ BigRational::from_integer(BigInt::from(n)) }"
)


def _escape_rs(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))


def _value_type(sample):
    """Infer Rust codegen parameters from a start value.

    Returns a dict with: ``vtype`` (stored type), ``ptype`` (callback param
    type), ``copy`` (bool), ``keyfmt`` (expr over a param ``s`` of ``ptype``),
    ``render_start`` (value -> Rust literal), ``json_type``.
    """
    base = dict(prelude="", needs_cargo=False)
    if isinstance(sample, bool):
        raise ValueError("lang='rust' does not support bool state values")
    if isinstance(sample, Fraction):
        # Python str(Fraction) drops the denominator when it is 1 (e.g. "2",
        # not "2/1"); match that exactly so node keys agree.
        return dict(base, vtype="BigRational", ptype="&BigRational", copy=False,
                    prelude=_RATIONAL_PRELUDE, needs_cargo=True,
                    keyfmt='if s.denom() == &BigInt::from(1) '
                           '{ format!("{}", s.numer()) } '
                           'else { format!("{}/{}", s.numer(), s.denom()) }',
                    render_start=lambda v: f"BigRational::new(BigInt::from"
                    f"({v.numerator}i64), BigInt::from({v.denominator}i64))",
                    json_type="string")
    if isinstance(sample, int):
        return dict(base, vtype="i64", ptype="i64", copy=True,
                    keyfmt='format!("{}", s)',
                    render_start=lambda v: f"{v}i64", json_type="integer")
    if (isinstance(sample, tuple) and len(sample) >= 2
            and all(isinstance(x, int) and not isinstance(x, bool)
                    for x in sample)):
        k = len(sample)
        vtype = "(" + ", ".join(["i64"] * k) + ")"
        placeholders = ", ".join("{}" for _ in range(k))
        accessors = ", ".join(f"s.{i}" for i in range(k))
        return dict(base, vtype=vtype, ptype=vtype, copy=True,
                    keyfmt=f'format!("({placeholders})", {accessors})',
                    render_start=lambda v: "(" + ", ".join(f"{x}i64" for x in v)
                    + ")", json_type="array")
    if isinstance(sample, str):
        return dict(base, vtype="String", ptype="&str", copy=False,
                    keyfmt="s.to_string()",
                    render_start=lambda v: f'String::from("{_escape_rs(v)}")',
                    json_type="string")
    raise ValueError(
        "lang='rust' supports int, tuple-of-ints (arity >= 2), str, or "
        f"Fraction start values; got {type(sample).__name__} {sample!r}")


_TEMPLATE = """\
#![allow(unused, non_upper_case_globals)]
use std::collections::{{HashMap, HashSet}};
use std::io::Write;

type V = {vtype};
{prelude}
{consts}

{callbacks}

#[inline(always)]
fn key(s: {ptype}) -> String {{ {keyfmt} }}

#[inline(always)]
fn tags_of(s: {ptype}) -> u32 {{ let mut b = 0u32; {tag_checks} b }}

fn main() {{
    let args: Vec<String> = std::env::args().collect();
    let out = &args[1];
    let max_depth: i64 = args[2].parse().unwrap();   // -1 = unbounded
    let max_nodes: i64 = args[3].parse().unwrap();   // -1 = unbounded

    let mut id_of: HashMap<V, u32> = HashMap::new();
    let mut values: Vec<V> = Vec::new();
    let mut depths: Vec<i64> = Vec::new();
    let mut tagbits: Vec<u32> = Vec::new();
    let mut edges: Vec<(u32, u32, usize)> = Vec::new();
    let mut seen_edges: HashSet<(u32, u32)> = HashSet::new();
    let mut pseudo: Vec<(u32, usize)> = Vec::new();
    let mut seen_pseudo: HashSet<(u32, usize)> = HashSet::new();
    let mut depth_limited = false;
    let mut truncated_key: Option<String> = None;

    let mut frontier: Vec<u32> = Vec::new();
    let mut cur_depth: i64 = 0;

    'bfs: {{
        for s0 in vec![{starts}] {{
            if !id_of.contains_key(&s0) {{
                if max_nodes >= 0 && values.len() as i64 >= max_nodes {{
                    truncated_key = Some(key({start_ref})); break 'bfs;
                }}
                let i = values.len() as u32;
                let tb = tags_of({start_ref});
                depths.push(0);
                tagbits.push(tb);
                id_of.insert({start_ins}, i);
                values.push(s0);
                frontier.push(i);
            }}
        }}

        while !frontier.is_empty() {{
            let at_max = max_depth >= 0 && cur_depth >= max_depth;
            if at_max {{ depth_limited = true; }}
            let mut next: Vec<u32> = Vec::new();
            for fi in 0..frontier.len() {{
                let xid = frontier[fi];
                {bind_s}
                let mut matched = false;
                'cases: {{
{cases_body}
                }}
            }}
            frontier = next;
            cur_depth += 1;
        }}
    }}

    let mut f = std::io::BufWriter::new(std::fs::File::create(out).unwrap());
    writeln!(f, "{{}}", values.len()).unwrap();
    for i in 0..values.len() {{
        let k = key({emit_ref});
        writeln!(f, "{{}} {{}} {{}}", depths[i], tagbits[i], k.len()).unwrap();
        f.write_all(k.as_bytes()).unwrap();
        writeln!(f).unwrap();
    }}
    writeln!(f, "{{}}", edges.len()).unwrap();
    for &(a, b, o) in &edges {{ writeln!(f, "{{}} {{}} {{}}", a, b, o).unwrap(); }}
    writeln!(f, "{{}}", pseudo.len()).unwrap();
    for &(x, o) in &pseudo {{ writeln!(f, "{{}} {{}}", x, o).unwrap(); }}
    writeln!(f, "{{}} {{}}", depth_limited as u8,
             truncated_key.is_some() as u8).unwrap();
    if let Some(tk) = &truncated_key {{
        writeln!(f, "{{}}", tk.len()).unwrap();
        f.write_all(tk.as_bytes()).unwrap();
        writeln!(f).unwrap();
    }}
}}
"""


def _render_source(starts, cases, default, consts, tag_items, vt):
    ptype, vtype = vt["ptype"], vt["vtype"]
    copy = vt["copy"]
    carg = "s" if copy else "&s"        # call arg for the bound value `s`
    bind_s = (f"let s = values[xid as usize];" if copy
              else "let s = values[xid as usize].clone();")
    start_ref = "s0" if copy else "&s0"
    start_ins = "s0" if copy else "s0.clone()"
    emit_ref = "values[i]" if copy else "&values[i]"

    const_lines = "\n".join(f"const {k}: i64 = {v};" for k, v in consts.items())

    cb = []
    for i, (cond, op, _l, _id, bound, _ex) in enumerate(cases):
        cb.append(f"#[inline(always)] fn cond{i}(s: {ptype}) -> bool {{ ({cond}) }}")
        cb.append(f"#[inline(always)] fn op{i}(s: {ptype}) -> V {{ ({op}) }}")
        if bound is not None:
            cb.append(f"#[inline(always)] fn bound{i}(s: {ptype}) -> bool "
                      f"{{ ({bound}) }}")
    if default is not None:
        # The default op gets index len(cases); name it op{n} so the generated
        # visit code (which calls op{op_idx}) resolves it.
        cb.append(f"#[inline(always)] fn op{len(cases)}(s: {ptype}) -> V "
                  f"{{ ({default[0]}) }}")
    for j, (_name, expr) in enumerate(tag_items):
        cb.append(f"#[inline(always)] fn tag{j}(s: {ptype}) -> bool {{ ({expr}) }}")

    tag_checks = " ".join(f"if tag{j}(s) {{ b |= {1 << j}u32; }}"
                          for j in range(len(tag_items)))

    # The visit (fire) and pseudo helpers, generated with the right copy/clone
    # forms. `visit` interns the successor, honours max_nodes, and adds the edge.
    def visit(op_idx):
        v_ins = "id_of.insert(v, i);" if copy else "id_of.insert(v.clone(), i);"
        vref = "v" if copy else "&v"
        return (
            "{ let v = " + f"op{op_idx}({carg}); "
            "let nid = match id_of.get(&v) { Some(&i) => i, None => { "
            "if max_nodes >= 0 && values.len() as i64 >= max_nodes { "
            f"truncated_key = Some(key({vref})); break 'bfs; }} "
            "let i = values.len() as u32; "
            f"let tb = tags_of({vref}); "
            "depths.push(cur_depth + 1); tagbits.push(tb); "
            f"{v_ins} values.push(v); next.push(i); i }} }}; "
            f"if seen_edges.insert((xid, nid)) {{ edges.push((xid, nid, {op_idx})); }} }}")

    def add_pseudo(op_idx):
        return (f"if seen_pseudo.insert((xid, {op_idx})) {{ "
                f"pseudo.push((xid, {op_idx})); }}")

    body = []
    n = len(cases)
    for i, (cond, op, _l, _id, bound, exclusive) in enumerate(cases):
        if bound is not None:
            pseudo_cond = f"at_max || !bound{i}({carg})"
        else:
            pseudo_cond = "at_max"
        line = (f"                    if cond{i}({carg}) {{ matched = true; "
                f"if {pseudo_cond} {{ {add_pseudo(i)} }} else {visit(i)} ")
        line += "break 'cases; }" if exclusive else "}"
        body.append(line)
    if default is not None:
        di = n
        body.append(
            f"                    if !matched {{ if at_max {{ {add_pseudo(di)} }} "
            f"else {visit(di)} }}")

    return _TEMPLATE.format(
        vtype=vtype, prelude=vt.get("prelude", ""), consts=const_lines,
        ptype=ptype, callbacks="\n".join(cb), keyfmt=vt["keyfmt"],
        tag_checks=tag_checks,
        starts=", ".join(vt["render_start"](s) for s in starts),
        start_ref=start_ref, start_ins=start_ins, emit_ref=emit_ref,
        bind_s=bind_s, cases_body="\n".join(body),
    )


def _compile_error(src, stderr):
    return RuntimeError(
        "Rust compilation of the generated callbacks failed — a Rust "
        "expression in .case()/.default()/bound=/tags= is likely invalid "
        f"(the value is bound to `s`). Generated source:\n  {src}\n\n{stderr}")


def _compile(source, needs_cargo=False):
    _CACHE.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(source.encode()).hexdigest()[:16]

    if needs_cargo:
        # Rational values: compile via cargo (num-bigint/num-rational deps),
        # sharing one target dir so the deps build once.
        if shutil.which("cargo") is None:
            raise RuntimeError(
                "lang='rust' with Fraction values needs cargo on PATH "
                "(https://rustup.rs) or use lang='python'.")
        proj = _CACHE / f"proj_{h}"
        binary = _CARGO_TARGET / "release" / f"p{h}"
        if not binary.exists():
            proj.mkdir(parents=True, exist_ok=True)
            (proj / "Cargo.toml").write_text(_CARGO_TOML.format(name=f"p{h}"))
            (proj / "main.rs").write_text(source)
            proc = subprocess.run(
                ["cargo", "build", "--release",
                 "--manifest-path", str(proj / "Cargo.toml")],
                capture_output=True, text=True,
                env={**os.environ, "CARGO_TARGET_DIR": str(_CARGO_TARGET)})
            if proc.returncode != 0:
                raise _compile_error(proj / "main.rs", proc.stderr)
        return binary

    if shutil.which("rustc") is None:
        raise RuntimeError(
            "lang='rust' needs the Rust compiler (rustc) on PATH. Install Rust "
            "(https://rustup.rs) or use lang='python'.")
    binary = _CACHE / h
    if not binary.exists():
        src = _CACHE / f"{h}.rs"
        src.write_text(source)
        proc = subprocess.run(
            ["rustc", "--edition", "2021", "-C", "opt-level=3",
             "-C", "codegen-units=1", "-o", str(binary), str(src)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise _compile_error(src, proc.stderr)
    return binary


class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def line(self):
        nl = self.data.index(b"\n", self.pos)
        out = self.data[self.pos:nl]
        self.pos = nl + 1
        return out

    def blob(self, n):
        out = self.data[self.pos:self.pos + n]
        self.pos += n + 1  # skip the trailing newline
        return out.decode("utf-8")


def build_rust(starts, cases, default, *, consts=None, key_type=None, tags=None,
               max_depth=64, max_nodes=1024, on_limit="stop"):
    """Compile the Rust-string cases and run the native BFS → Graph.

    *cases* is a list of ``(cond, op, label, id, bound, exclusive)``; *default*
    is ``(op, label, id)`` or None; *tags* is a ``dict[str, rust_expr]``.
    Mirrors ``visiter.iteration.build`` semantics for the supported subset.
    """
    from .graph import Graph
    consts = consts or {}
    tags = tags or {}
    if not starts:
        raise ValueError("lang='rust' needs at least one start value")
    vt = _value_type(starts[0])
    tag_items = list(tags.items())

    # Resolve label/id: default to the op expression itself; build op metadata.
    op_ids = []           # op index -> id (rules then default)
    op_labels = {}
    for cond, op, label, id_, bound, exclusive in cases:
        oid = id_ if id_ is not None else op
        op_ids.append(oid)
        op_labels.setdefault(oid, label if label is not None else op)
    if default is not None:
        dop, dlabel, did = default
        oid = did if did is not None else dop
        op_ids.append(oid)
        op_labels.setdefault(oid, dlabel if dlabel is not None else dop)

    source = _render_source(starts, cases, default, consts, tag_items, vt)
    binary = _compile(source, vt.get("needs_cargo", False))
    md = -1 if max_depth is None else int(max_depth)
    mn = -1 if max_nodes is None else int(max_nodes)
    with tempfile.NamedTemporaryFile(suffix=".graph") as tf:
        subprocess.run([str(binary), tf.name, str(md), str(mn)],
                       check=True, capture_output=True, text=True)
        r = _Reader(Path(tf.name).read_bytes())

    kt = key_type if key_type is not None else vt["json_type"]
    n_nodes = int(r.line())
    keys, nodes = [], {}
    for _ in range(n_nodes):
        depth, tb, klen = (int(x) for x in r.line().split())
        k = r.blob(klen)
        keys.append(k)
        info = {"depth": depth, "key_type": kt}
        node_tags = [tag_items[j][0] for j in range(len(tag_items))
                     if tb & (1 << j)]
        if node_tags:
            info["tags"] = node_tags
        nodes[k] = info

    n_edges = int(r.line())
    edges = []
    for _ in range(n_edges):
        a, b, o = (int(x) for x in r.line().split())
        edges.append({"from": keys[a], "to": keys[b], "op": op_ids[o],
                      "label": op_labels[op_ids[o]]})

    n_pseudo = int(r.line())
    seen_pseudo = set()
    pseudo_edges = []
    for _ in range(n_pseudo):
        x, o = (int(v) for v in r.line().split())
        oid = op_ids[o]
        if (keys[x], oid) not in seen_pseudo:   # dedup on (from, op id)
            seen_pseudo.add((keys[x], oid))
            pseudo_edges.append({"from": keys[x], "op": oid,
                                 "label": op_labels[oid]})

    depth_limited, truncated = (int(x) for x in r.line().split())
    if truncated:
        tkey = r.blob(int(r.line()))
        reason = f"max_nodes={max_nodes}"
        if on_limit == "raise":
            raise RuntimeError(f"{reason} reached at value={tkey}")
        warnings.warn(
            f"build: {reason} reached at value={tkey}; output is truncated. "
            f"Pass a higher limit or None to disable.", UserWarning, stacklevel=2)
    if depth_limited and on_limit != "raise":
        warnings.warn(
            f"build: max_depth={max_depth} reached; output is truncated. "
            f"Pass a higher max_depth or None to disable.", UserWarning,
            stacklevel=2)

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
        "pseudo_edges": pseudo_edges,
        "op_order": op_order,
        "op_labels": {oid: op_labels[oid] for oid in op_order},
    })
