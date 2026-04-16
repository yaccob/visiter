import ast
import inspect
import textwrap
import time
from collections import namedtuple


def _derive_label(func):
    """Derive a human-readable op label from a callable.

    - Named functions: ``func.__name__`` (e.g. ``"square"``).
    - Lambdas: ``ast.unparse`` of the body after parsing the retrieved
      source (e.g. ``lambda x: x * 2`` → ``"x * 2"``).

    When multiple lambdas share a source line (``Rule(lambda x: cond,
    Op(lambda x: body))`` is the common case), the right one is picked
    by matching ``func.__code__.co_firstlineno`` and the column of the
    first bytecode instruction against each AST lambda's body position.
    Falls back to a ``ValueError`` asking for an explicit ``label=``
    when the source isn't retrievable (REPL, built-in, ``functools.partial``)
    or when ambiguity cannot be resolved.
    """
    name = getattr(func, "__name__", None)
    if name and name != "<lambda>":
        return name
    try:
        src_lines, start_lineno = inspect.getsourcelines(func)
    except (OSError, TypeError) as exc:
        raise ValueError(
            "Op could not derive a label from an anonymous callable "
            "(source unavailable — REPL, built-in, or partial). "
            "Pass label=... explicitly."
        ) from exc
    raw = "".join(src_lines)
    src = textwrap.dedent(raw)
    indent = len(raw.split("\n", 1)[0]) - len(src.split("\n", 1)[0])
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise ValueError(
            "Op could not parse the lambda's source snippet. "
            "Pass label=... explicitly."
        ) from exc
    lambdas = [n for n in ast.walk(tree) if isinstance(n, ast.Lambda)]
    if not lambdas:
        raise ValueError(
            "Op could not find a lambda in the retrieved source. "
            "Pass label=... explicitly."
        )
    if len(lambdas) == 1:
        return ast.unparse(lambdas[0].body)

    # Disambiguate by position of the first bytecode instruction with
    # a real source span (skip zero-span entries like RESUME).
    body_line = body_col = None
    try:
        for line_start, _, col_start, col_end in func.__code__.co_positions():
            if line_start is None:
                continue
            if col_start == 0 and col_end == 0:
                continue
            body_line, body_col = line_start, col_start
            break
    except AttributeError:
        pass  # Python <3.11: co_positions unavailable

    if body_line is not None:
        rel_line = body_line - start_lineno + 1
        rel_col = body_col - indent if body_col is not None else None
        matches = [
            n for n in lambdas
            if getattr(n.body, "lineno", None) == rel_line
            and (rel_col is None
                 or getattr(n.body, "col_offset", None) == rel_col)
        ]
        if len(matches) == 1:
            return ast.unparse(matches[0].body)

    raise ValueError(
        "Op found multiple lambdas in the retrieved source and "
        "could not uniquely identify the intended one. "
        "Pass label=... explicitly."
    )


class Op(namedtuple("_Op", ["func", "label"])):
    """A guarded operation's callable + its display/identity label.

    ``label`` is optional: when omitted, it is derived from ``func`` —
    the function's ``__name__`` for named functions, or the lambda's
    body source for lambdas. See ``_derive_label`` for the full rules
    and fallbacks.
    """
    __slots__ = ()

    def __new__(cls, func, label=None):
        if label is None:
            label = _derive_label(func)
        return super().__new__(cls, func, label)


Rule = namedtuple("Rule", ["condition", "op", "bound"])
Rule.__new__.__defaults__ = (None,)


def json_type(x):
    """Return the JSON Schema type name for a Python value.

    Maps Python types to the seven JSON primitives
    (``null``, ``boolean``, ``integer``, ``number``, ``string``,
    ``array``, ``object``) so the graph-dict's ``key_type`` field is
    language-neutral: any JSON consumer understands it without
    Python-specific knowledge.

    Order matters: ``bool`` must be checked before ``int`` because
    Python's ``bool`` is a subclass of ``int``.
    """
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "boolean"
    if isinstance(x, int):
        return "integer"
    if isinstance(x, float):
        return "number"
    if isinstance(x, str):
        return "string"
    if isinstance(x, (list, tuple, set, frozenset)):
        return "array"
    if isinstance(x, dict):
        return "object"
    # Anything else goes through default=str in JSON output → treat
    # as string for round-trip purposes.
    return "string"


def parse_range(s):
    """Parse a comma-separated range string like '1-5,8,11-13' into a list of ints.

    Ranges are inclusive on both ends (print-dialog convention).
    """
    result = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.extend(range(int(lo.strip()), int(hi.strip()) + 1))
        else:
            result.append(int(part))
    return result


def iterate(start, rules, *, default, max_depth=None,
            max_nodes=1_000_000, time_limit=None,
            on_limit="raise", tags=None):
    """Build a graph by applying rules repeatedly from each starting value.

    At each value x, every Rule whose condition(x) is True contributes an
    outgoing edge (so out-degree can be 0..N per node). If NO rule matches
    and `default` is not None, `default` fires instead — it's the explicit
    fallback operation for "none of the rules apply".

    A Rule may carry an optional `bound` predicate that separates "the op
    is applicable" (`condition`) from "we want to stop here anyway, even
    though the op would apply" (`bound`). Semantics:
      - condition False                → rule skipped (as usual).
      - condition True, bound True     → normal edge fires.
      - condition True, bound False    → pseudo-edge recorded (no real
        successor, no recursion); the renderer shows these as ghost stubs.
      - bound is None                  → treated as always True.

    `default` is required. Pass `None` to signal explicitly that a value
    for which no rule matches is a leaf (no outgoing edge). Pass `Op(...)`
    to fire that op as the else branch — useful for binary mutually
    exclusive cases where "everything that isn't covered by the rules
    takes this other path".

    Expansion is BFS-ordered from the starts, so each node's recorded
    `depth` equals its minimum hop count from the nearest start.

    Termination:
      - A node is expanded at most once. Reaching a known node adds the edge
        but does not recurse — natural stop for cycles and joins.
      - `max_depth` caps the BFS frontier. Nodes at exactly `max_depth` are
        kept but not expanded; any rule (or default) that would fire for
        them becomes a pseudo-edge, so the renderer marks them as frontier
        stubs with the op's color (same visual vocabulary as `bound`).
      - `max_nodes` bounds the total graph size.
      - `time_limit` ("hh:mm:ss") bounds wall-clock time.
      - `on_limit`: "raise" aborts with RuntimeError when max_nodes or
        time_limit is hit (default — treats resource limits as a
        divergence assertion). "stop" returns the partial graph.
        `max_depth` is always a soft topological stop, never raises.

    Args:
        start: an int or an iterable of ints
        rules: iterable of Rule
        default: Op or None (REQUIRED, no Python default)
        max_depth: optional int; None (default) disables the depth limit.
        max_nodes, time_limit, on_limit: resource-limit controls
        tags: optional dict {name: callable}

    Returns:
        {
            "schema_version": "1",
            "roots": [int, ...],
            "nodes": {str(value): {"depth": int, "tags"?: [str, ...]}, ...},
            "edges": [{"from": A, "to": B, "op": label}, ...],
            "pseudo_edges": [{"from": A, "op": label}, ...],
            "op_order": [str, ...]  # distinct op labels in rule-then-default order
        }

    `schema_version` matches the path segment of the bundled JSON Schema
    (`schemas/v1/graph.schema.json`). Breaking changes bump the major and
    ship under `/v2/` with v1 frozen.
    """
    if on_limit not in ("raise", "stop"):
        raise ValueError(f"on_limit must be 'raise' or 'stop', got {on_limit!r}")
    if isinstance(start, int):
        start = [start]
    tags = tags or {}

    rules = list(rules)
    for r in rules:
        if not isinstance(r, Rule):
            raise TypeError(f"rules must contain Rule instances; "
                            f"got {type(r).__name__}")
    if default is not None and not isinstance(default, Op):
        raise TypeError(f"default must be Op or None; "
                        f"got {type(default).__name__}")

    op_order = []
    seen_ops = set()
    for rule in rules:
        if rule.op.label not in seen_ops:
            seen_ops.add(rule.op.label)
            op_order.append(rule.op.label)
    if default is not None and default.label not in seen_ops:
        seen_ops.add(default.label)
        op_order.append(default.label)

    deadline = None
    if time_limit is not None:
        h, m, s = map(int, time_limit.split(":"))
        deadline = time.time() + h * 3600 + m * 60 + s

    graph = {"schema_version": "1",
             "roots": list(start), "nodes": {}, "edges": [],
             "pseudo_edges": [], "op_order": op_order}
    seen_edges = set()
    seen_pseudo = set()

    def make_node(x, depth):
        info = {"depth": depth, "key_type": json_type(x)}
        node_tags = [name for name, fn in tags.items() if fn(x)]
        if node_tags:
            info["tags"] = node_tags
        return info

    def add_edge(a, b, op):
        if (a, b) not in seen_edges:
            graph["edges"].append({"from": a, "to": b, "op": op})
            seen_edges.add((a, b))

    def add_pseudo(x, label):
        key = (x, label)
        if key not in seen_pseudo:
            graph["pseudo_edges"].append({"from": x, "op": label})
            seen_pseudo.add(key)

    def limit_reason():
        if deadline is not None and time.time() >= deadline:
            return f"time_limit={time_limit}"
        if max_nodes is not None and len(graph["nodes"]) >= max_nodes:
            return f"max_nodes={max_nodes}"
        return None

    def handle_limit(reason, context):
        if on_limit == "raise":
            raise RuntimeError(f"{reason} reached {context}")
        return graph

    def fire(x, op, next_depth):
        """Apply op to x at the given next_depth; return (done, nxt_if_new).

        `done` is non-None iff the iteration should abort with that graph.
        `nxt_if_new` is the successor value if newly created, else None.
        """
        nxt = op.func(x)
        new_node = str(nxt) not in graph["nodes"]
        if new_node:
            reason = limit_reason()
            if reason:
                result = handle_limit(reason, f"at value={nxt}")
                if result is not None:
                    return result, None
            graph["nodes"][str(nxt)] = make_node(nxt, next_depth)
        add_edge(x, nxt, op.label)
        return None, (nxt if new_node else None)

    frontier = []
    for n in start:
        if str(n) in graph["nodes"]:
            continue
        reason = limit_reason()
        if reason:
            result = handle_limit(reason, f"before start={n}")
            if result is not None:
                return result
        graph["nodes"][str(n)] = make_node(n, 0)
        frontier.append(n)

    depth = 0
    while frontier:
        at_max = max_depth is not None and depth >= max_depth
        next_frontier = []
        for x in frontier:
            any_matched = False
            for rule in rules:
                if not rule.condition(x):
                    continue
                any_matched = True
                if at_max or (rule.bound is not None and not rule.bound(x)):
                    add_pseudo(x, rule.op.label)
                    continue
                done, nxt = fire(x, rule.op, depth + 1)
                if done is not None:
                    return done
                if nxt is not None:
                    next_frontier.append(nxt)
            if not any_matched and default is not None:
                if at_max:
                    add_pseudo(x, default.label)
                else:
                    done, nxt = fire(x, default, depth + 1)
                    if done is not None:
                        return done
                    if nxt is not None:
                        next_frontier.append(nxt)
        depth += 1
        frontier = next_frontier

    return graph
