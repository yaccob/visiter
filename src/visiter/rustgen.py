"""Path B: inline Rust-expression callbacks, compiled on the fly.

When a chain is started with ``viter(..., lang="rust")``, the ``.case()`` /
``.default()`` / ``bound=`` / ``tags=`` arguments are **Rust expression strings**
(the current value is bound to the name given by the chain's required ``bind=``
option) instead of Python callables. At
``.build()`` time the expressions are spliced into a fixed Rust BFS engine,
compiled once with ``rustc`` (cached on a hash of the generated source), and run
natively. The resulting graph is byte-identical to the pure-Python build —
including default bounds, ghost-stub pseudo-edges, ``max_nodes`` truncation,
``tags`` and ``key_type``.

``rustc`` must be on PATH; there is no Python fallback for Rust source, so use
``lang="python"`` in toolchain-less environments.

Supported state values (inferred from the start values): ``int``, ``tuple`` of
ints (arity >= 2), ``str``, and ``Fraction`` (exact rationals via
``num-rational``/``num-bigint``, compiled through ``cargo``). ``max_depth`` /
``max_nodes`` / ``time_limit`` bounds, ``bound=`` predicates, ``tags=`` and
per-call edge labels (``label_rs=``, the ``OpResult`` analogue) all match the
Python path. Heterogeneous value types are one gap — rustc rejects the type
mix, which surfaces as a clear compile error rather than a silent divergence.

Integer state values are ``i128`` (range ~±1.7e38), not Python's unbounded
``int``: this covers Collatz-like reverse maps that exceed 2^63 at modest depth.
Compilation enables overflow-checks, so a build that exceeds i128 **panics**
(surfaced as an error) instead of silently wrapping into a wrong graph. For
unbounded integers use ``Fraction`` here, or the ``engine=`` paths (Python
bignums).
"""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from fractions import Fraction
from pathlib import Path

_CACHE = Path(tempfile.gettempdir()) / "visiter-rustgen-cache"

# The fixed, unique parameter every generated callback takes. The chain's bind=
# name is re-exposed from it via a `let`, so the bind name never has to dodge
# the engine's internal symbols — it can be any valid Rust identifier (it only
# shadows a same-named helper inside its own expression).
_BIND_PARAM = "__viter_value"

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Rust keywords (2021 strict + reserved); a `let <kw> = …` rebind won't compile,
# so reject them up front with a clearer message than rustc's. This set is
# fixed by the language, not by the engine, so it never grows with internals.
_RUST_KEYWORDS = frozenset("""
    as break const continue crate dyn else enum extern false fn for if impl in
    let loop match mod move mut pub ref return self Self static struct super
    trait true type unsafe use where while async await
    abstract become box do final macro override priv typeof unsized virtual
    yield try
""".split())


def _check_bind(bind):
    """Reject a ``bind=`` that cannot name the bound value in Rust."""
    if bind is None:
        raise ValueError(
            'lang="rust" requires a bind= name for the current value, e.g. '
            'viter(..., lang="rust", bind="n"); there is no default')
    if not isinstance(bind, str) or bind == "_" or not _IDENT_RE.match(bind):
        raise ValueError(
            f"bind={bind!r} is not a valid Rust identifier for the bound value")
    if bind in _RUST_KEYWORDS:
        raise ValueError(f"bind={bind!r} is a Rust keyword; pick another name")

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
overflow-checks = true
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
        # i128 (not i64): the BFS values of Collatz-like reverse maps blow past
        # 2^63 well before 2^127, so i64 silently wraps where Python stays exact.
        # i128 lifts the ceiling to ~1.7e38 and keeps the bare-rustc speed and
        # bitwise ops; beyond it, overflow-checks (see _compile) panic instead
        # of wrapping. True unbounded precision would need BigInt (and lose
        # bitwise ops), which Fraction already uses for the rational case.
        return dict(base, vtype="i128", ptype="i128", copy=True, int_width="i128",
                    keyfmt='format!("{}", s)',
                    render_start=lambda v: f"{v}i128", json_type="integer")
    if (isinstance(sample, tuple) and len(sample) >= 2
            and all(isinstance(x, int) and not isinstance(x, bool)
                    for x in sample)):
        k = len(sample)
        vtype = "(" + ", ".join(["i128"] * k) + ")"
        placeholders = ", ".join("{}" for _ in range(k))
        accessors = ", ".join(f"s.{i}" for i in range(k))
        return dict(base, vtype=vtype, ptype=vtype, copy=True, int_width="i128",
                    keyfmt=f'format!("({placeholders})", {accessors})',
                    render_start=lambda v: "(" + ", ".join(f"{x}i128" for x in v)
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
use std::time::Instant;

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
    let time_limit: f64 = args[4].parse().unwrap();  // -1 = unbounded
    let start_time = Instant::now();

    let mut id_of: HashMap<V, u32> = HashMap::new();
    let mut values: Vec<V> = Vec::new();
    let mut depths: Vec<i64> = Vec::new();
    let mut tagbits: Vec<u32> = Vec::new();
    let mut edges: Vec<(u32, u32, usize)> = Vec::new();
    let mut edge_labels: Vec<Option<String>> = Vec::new();
    let mut seen_edges: HashSet<(u32, u32, usize)> = HashSet::new();
    let mut pseudo: Vec<(u32, usize)> = Vec::new();
    let mut seen_pseudo: HashSet<(u32, usize)> = HashSet::new();
    let mut depth_limited = false;
    let mut truncated_key: Option<String> = None;
    let mut trunc_reason: u8 = 0;  // 0 none, 1 max_nodes, 2 time_limit

    let mut frontier: Vec<u32> = Vec::new();
    let mut cur_depth: i64 = 0;

    'bfs: {{
        for s0 in vec![{starts}] {{
            if !id_of.contains_key(&s0) {{
                if time_limit >= 0.0 && start_time.elapsed().as_secs_f64() >= time_limit {{
                    trunc_reason = 2; truncated_key = Some(key({start_ref})); break 'bfs;
                }}
                if max_nodes >= 0 && values.len() as i64 >= max_nodes {{
                    trunc_reason = 1; truncated_key = Some(key({start_ref})); break 'bfs;
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
    for i in 0..edges.len() {{
        let (a, b, o) = edges[i];
        match &edge_labels[i] {{
            Some(l) => {{
                writeln!(f, "{{}} {{}} {{}} {{}}", a, b, o, l.len()).unwrap();
                f.write_all(l.as_bytes()).unwrap();
                writeln!(f).unwrap();
            }}
            None => {{ writeln!(f, "{{}} {{}} {{}} -1", a, b, o).unwrap(); }}
        }}
    }}
    writeln!(f, "{{}}", pseudo.len()).unwrap();
    for &(x, o) in &pseudo {{ writeln!(f, "{{}} {{}}", x, o).unwrap(); }}
    writeln!(f, "{{}} {{}}", depth_limited as u8, trunc_reason).unwrap();
    if let Some(tk) = &truncated_key {{
        writeln!(f, "{{}}", tk.len()).unwrap();
        f.write_all(tk.as_bytes()).unwrap();
        writeln!(f).unwrap();
    }}
}}
"""


def _render_source(starts, cases, default, consts, tag_items, vt, bind):
    ptype, vtype = vt["ptype"], vt["vtype"]
    copy = vt["copy"]
    carg = "s" if copy else "&s"        # call arg for the bound value `s`
    bind_s = (f"let s = values[xid as usize];" if copy
              else "let s = values[xid as usize].clone();")
    start_ref = "s0" if copy else "&s0"
    start_ins = "s0" if copy else "s0.clone()"
    emit_ref = "values[i]" if copy else "&values[i]"

    # Consts share the state's integer width so `s.0 < N - 1` etc. typecheck
    # (i128 for int/tuple states; i64 otherwise, unchanged).
    const_int = vt.get("int_width", "i64")
    const_lines = "\n".join(f"const {k}: {const_int} = {v};"
                            for k, v in consts.items())

    # Every user callback takes the fixed internal param and rebinds it to the
    # chain's bind= name, so the expressions read from `bind` while the bind
    # name stays decoupled from the engine's own symbols. No textual rewriting
    # of the expressions — rustc keeps identifiers and string literals apart.
    p = _BIND_PARAM
    rebind = f"let {bind} = {p};"

    cb = []
    op_label_rs = []   # op index -> label_rs expr (per-call label) or None
    for i, (cond, op, _l, _id, bound, _ex, lrs) in enumerate(cases):
        cb.append(f"#[inline(always)] fn cond{i}({p}: {ptype}) -> bool "
                  f"{{ {rebind} ({cond}) }}")
        cb.append(f"#[inline(always)] fn op{i}({p}: {ptype}) -> V "
                  f"{{ {rebind} ({op}) }}")
        if bound is not None:
            cb.append(f"#[inline(always)] fn bound{i}({p}: {ptype}) -> bool "
                      f"{{ {rebind} ({bound}) }}")
        if lrs is not None:
            cb.append(f"#[inline(always)] fn label{i}({p}: {ptype}) -> String "
                      f"{{ {rebind} ({lrs}) }}")
        op_label_rs.append(lrs)
    if default is not None:
        # The default op gets index len(cases); name it op{n} so the generated
        # visit code (which calls op{op_idx}) resolves it.
        di = len(cases)
        cb.append(f"#[inline(always)] fn op{di}({p}: {ptype}) -> V "
                  f"{{ {rebind} ({default[0]}) }}")
        if default[3] is not None:
            cb.append(f"#[inline(always)] fn label{di}({p}: {ptype}) -> String "
                      f"{{ {rebind} ({default[3]}) }}")
        op_label_rs.append(default[3])
    for j, (_name, expr) in enumerate(tag_items):
        cb.append(f"#[inline(always)] fn tag{j}({p}: {ptype}) -> bool "
                  f"{{ {rebind} ({expr}) }}")

    tag_checks = " ".join(f"if tag{j}(s) {{ b |= {1 << j}u32; }}"
                          for j in range(len(tag_items)))

    # The visit (fire) and pseudo helpers, generated with the right copy/clone
    # forms. `visit` interns the successor, honours max_nodes, and adds the edge.
    def visit(op_idx):
        v_ins = "id_of.insert(v, i);" if copy else "id_of.insert(v.clone(), i);"
        vref = "v" if copy else "&v"
        # Per-call edge label (OpResult analogue) computed from the source `s`,
        # else None (the Python side fills in the static op label).
        edge_label = (f"Some(label{op_idx}({carg}))"
                      if op_label_rs[op_idx] is not None else "None")
        return (
            "{ let v = " + f"op{op_idx}({carg}); "
            "let nid = match id_of.get(&v) { Some(&i) => i, None => { "
            "if time_limit >= 0.0 && start_time.elapsed().as_secs_f64() >= time_limit { "
            f"trunc_reason = 2; truncated_key = Some(key({vref})); break 'bfs; }} "
            "if max_nodes >= 0 && values.len() as i64 >= max_nodes { "
            f"trunc_reason = 1; truncated_key = Some(key({vref})); break 'bfs; }} "
            "let i = values.len() as u32; "
            f"let tb = tags_of({vref}); "
            "depths.push(cur_depth + 1); tagbits.push(tb); "
            f"{v_ins} values.push(v); next.push(i); i }} }}; "
            # Key on (from, to, op): distinct ops to the same successor are
            # distinct edges. build_rust re-dedups on the resolved op.id so two
            # rule indices sharing one id still collapse like pure Python.
            f"if seen_edges.insert((xid, nid, {op_idx})) {{ "
            f"edges.push((xid, nid, {op_idx})); "
            f"edge_labels.push({edge_label}); }} }}")

    def add_pseudo(op_idx):
        return (f"if seen_pseudo.insert((xid, {op_idx})) {{ "
                f"pseudo.push((xid, {op_idx})); }}")

    body = []
    n = len(cases)
    for i, (cond, op, _l, _id, bound, exclusive, _lrs) in enumerate(cases):
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
        "(the value is bound to the chain's `bind=` name). "
        f"Generated source:\n  {src}\n\n{stderr}")


def _compile(source, needs_cargo=False):
    _CACHE.mkdir(parents=True, exist_ok=True)
    # Fold the compile flags into the cache key: flags (e.g. overflow-checks)
    # are not part of the source text, so a flag change would otherwise reuse a
    # stale binary built without them.
    h = hashlib.sha256((source + "\n//flags:ovf=on").encode()).hexdigest()[:16]

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
             "-C", "overflow-checks=on",
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


def build_rust(starts, cases, default, *, bind, consts=None, key_type=None,
               tags=None, max_depth=64, max_nodes=1024, time_limit=None,
               on_limit="stop"):
    """Compile the Rust-string cases and run the native BFS → Graph.

    *cases* is a list of ``(cond, op, label, id, bound, exclusive)``; *default*
    is ``(op, label, id)`` or None; *tags* is a ``dict[str, rust_expr]``. *bind*
    is the (required) identifier the expressions read the current value from.
    Mirrors ``visiter.iteration.build`` semantics for the supported subset.
    """
    from .graph import Graph
    consts = consts or {}
    tags = tags or {}
    _check_bind(bind)
    if not starts:
        raise ValueError("lang='rust' needs at least one start value")
    vt = _value_type(starts[0])
    tag_items = list(tags.items())

    # Resolve label/id: default to the op expression itself; build op metadata.
    op_ids = []           # op index -> id (rules then default)
    op_labels = {}
    for cond, op, label, id_, bound, exclusive, label_rs in cases:
        oid = id_ if id_ is not None else op
        op_ids.append(oid)
        op_labels.setdefault(oid, label if label is not None else op)
    if default is not None:
        dop, dlabel, did, dlabel_rs = default
        oid = did if did is not None else dop
        op_ids.append(oid)
        op_labels.setdefault(oid, dlabel if dlabel is not None else dop)

    source = _render_source(starts, cases, default, consts, tag_items, vt, bind)
    binary = _compile(source, vt.get("needs_cargo", False))
    md = -1 if max_depth is None else int(max_depth)
    mn = -1 if max_nodes is None else int(max_nodes)
    if time_limit is None:
        tl = -1.0
    else:
        h, m, s = (int(x) for x in time_limit.split(":"))
        tl = float(h * 3600 + m * 60 + s)
    with tempfile.NamedTemporaryFile(suffix=".graph") as tf:
        subprocess.run([str(binary), tf.name, str(md), str(mn), repr(tl)],
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

    # Real edges dedup on (from, to, op.id) — the rust side dedups on
    # (from_idx, to_idx, op_idx); re-dedup here so distinct rule indices sharing
    # one op.id collapse exactly like pure Python (which keys on op.id).
    n_edges = int(r.line())
    edges = []
    seen_edges = set()
    for _ in range(n_edges):
        a, b, o, llen = (int(x) for x in r.line().split())
        # llen >= 0: a per-call (OpResult-style) label follows; else static.
        lab = r.blob(llen) if llen >= 0 else op_labels[op_ids[o]]
        oid = op_ids[o]
        key = (keys[a], keys[b], oid)
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"from": keys[a], "to": keys[b], "op": oid,
                          "label": lab})

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

    depth_limited, trunc_reason = (int(x) for x in r.line().split())
    if trunc_reason:
        tkey = r.blob(int(r.line()))
        reason = (f"max_nodes={max_nodes}" if trunc_reason == 1
                  else f"time_limit={time_limit}")
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
