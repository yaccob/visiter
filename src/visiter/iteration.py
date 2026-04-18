import ast
import inspect
import linecache
import time
import warnings
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

    # Read the *full* source (whole file or whole eval string) via
    # linecache — a lambda embedded in a multi-line expression would
    # otherwise come back from inspect.getsourcelines as a syntactically
    # incomplete fragment that ast.parse rejects. linecache is how
    # inspect finds source anyway, and the CLI pre-populates it for
    # eval'd argstrings so this path works for both real modules and
    # synthetic eval sources.
    code = getattr(func, "__code__", None)
    filename = getattr(code, "co_filename", None) if code else None
    lines = linecache.getlines(filename) if filename else []
    if not lines:
        try:
            lines, _ = inspect.getsourcelines(func)
        except (OSError, TypeError) as exc:
            raise ValueError(
                "Op could not derive a label from an anonymous callable "
                "(source unavailable — REPL, built-in, or partial). "
                "Pass label=... explicitly."
            ) from exc

    src = "".join(lines)
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise ValueError(
            "Op could not parse the retrieved source. "
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
    # a real source span (skip zero-span entries like RESUME). Both
    # co_positions and ast node positions are absolute to the parsed
    # source, so they match directly.
    body_line = body_col = None
    try:
        for line_start, _, col_start, col_end in code.co_positions():
            if line_start is None:
                continue
            if col_start == 0 and col_end == 0:
                continue
            body_line, body_col = line_start, col_start
            break
    except AttributeError:
        pass  # Python <3.11: co_positions unavailable

    if body_line is not None:
        matches = [
            n for n in lambdas
            if getattr(n.body, "lineno", None) == body_line
            and (body_col is None
                 or getattr(n.body, "col_offset", None) == body_col)
        ]
        if len(matches) == 1:
            return ast.unparse(matches[0].body)

    raise ValueError(
        "Op found multiple lambdas in the retrieved source and "
        "could not uniquely identify the intended one. "
        "Pass label=... explicitly."
    )


class Op(namedtuple("_Op", ["func", "label", "id"])):
    """A guarded operation's callable, its display label, and its id.

    - ``label`` is the display string on edges (can carry Unicode,
      whitespace, emoji — anything that reads well in the SVG). Free
      for the user to choose.
    - ``id`` is the stable key used by ``op_order``, ``op_colors``
      pinning, and JSON round-trips. Defaults to the *auto-derived*
      form of ``func`` (``__name__`` for named functions, lambda body
      source for lambdas), **independent of whatever the user chose
      for label**. That way two ops built from the same ``func`` always
      share an id, even when their display labels differ; and two ops
      with accidentally-equal labels but different ``func`` don't
      collide silently.

    Both ``label`` and ``id`` are optional and **keyword-only** —
    only ``func`` is accepted positionally. That prevents the ambiguity
    that two adjacent positional strings would invite (which of them is
    the label, which the id?) and makes the intent of an overriding
    label or id visible at the call site: ``Op(f, label="÷3", id="div3")``.

    Pass ``id=`` explicitly when you want to split two ops whose
    auto-derived id coincides (e.g. two lambdas whose bodies happen
    to unparse the same way), when you want a stable pin target that
    survives func refactors, or simply when you prefer a short custom
    string.

    When ``_derive_label(func)`` can't recover a source representation
    (REPL lambdas, ``functools.partial``, C extensions) the label
    falls back as usual, and ``id`` falls back to whatever label the
    user supplied — single-string behavior because that's the only
    key we have.
    """
    __slots__ = ()

    def __new__(cls, func, *, label=None, id=None):
        derived = None
        derive_error = None
        if label is None or id is None:
            try:
                derived = _derive_label(func)
            except ValueError as exc:
                derive_error = exc
        if label is None:
            if derived is None:
                raise derive_error
            label = derived
        if id is None:
            id = derived if derived is not None else label
        return super().__new__(cls, func, label, id)


Rule = namedtuple("Rule", ["condition", "op", "bound"])
Rule.__new__.__defaults__ = (None,)


JSON_SCHEMA_TYPES = frozenset({
    "null", "boolean", "integer", "number", "string", "array", "object",
})


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


def _make_key_type_resolver(key_type):
    """Return a callable value → JSON Schema type string.

    - ``None``: ``json_type`` — infer from the Python type of each value.
    - string: a fixed type applied to every value (must be one of the
      seven JSON Schema primitives).
    - callable: user hook called per value. Return one of the seven
      primitives to override, or ``None`` to delegate to ``json_type``
      for that value.

    Raises ``ValueError`` when the argument (or the callable's return
    value) is not one of the allowed strings.
    """
    if key_type is None:
        return json_type
    if callable(key_type):
        def resolve(x):
            t = key_type(x)
            if t is None:
                return json_type(x)
            if t not in JSON_SCHEMA_TYPES:
                raise ValueError(
                    f"key_type callable returned {t!r}; must be one of "
                    f"{sorted(JSON_SCHEMA_TYPES)} or None"
                )
            return t
        return resolve
    if isinstance(key_type, str):
        if key_type not in JSON_SCHEMA_TYPES:
            raise ValueError(
                f"key_type={key_type!r}; must be one of "
                f"{sorted(JSON_SCHEMA_TYPES)} (or a callable, or None)"
            )
        return lambda x: key_type
    raise TypeError(
        f"key_type must be None, a string, or a callable; "
        f"got {type(key_type).__name__}"
    )


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


def build(start, rules, default, *, max_depth=64,
            max_nodes=1024, time_limit=None,
            on_limit="stop", tags=None, key_type=None):
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
      - `max_depth` caps the BFS frontier (default 64). Nodes at exactly
        `max_depth` are kept but not expanded; any rule (or default) that
        would fire for them becomes a pseudo-edge, so the renderer marks
        them as frontier stubs with the op's color (same visual vocabulary
        as `bound`). Pass ``None`` to disable the depth limit.
      - `max_nodes` bounds the total graph size (default 1024). Pass ``None``
        to disable.
      - `time_limit` ("hh:mm:ss") bounds wall-clock time.
      - `on_limit`: "stop" (default) returns the partial graph and emits a
        warning to stderr when any limit is hit. "raise" aborts with
        RuntimeError instead.
        `max_depth` is always a soft topological stop, never raises.

    Args:
        start: an int or an iterable of ints
        rules: iterable of Rule
        default: Op or None (REQUIRED, no Python default)
        max_depth: optional int; None (default) disables the depth limit.
        max_nodes, time_limit, on_limit: resource-limit controls
        tags: optional dict {name: callable}
        key_type: optional override for the per-node `key_type` field.
            `None` (default) infers the JSON Schema type from each value's
            Python type via `json_type`. A string fixes a single type for
            every node (must be one of the seven JSON Schema primitives —
            `null`, `boolean`, `integer`, `number`, `string`, `array`,
            `object`). A callable is invoked per value and may return one
            of those strings or `None` to fall back to `json_type` for
            that value. Useful for domain types that JSON-serialise as
            strings but should be classified numerically (`Fraction`,
            `Decimal`) to participate in type-sensitive rendering.

    Returns:
        Graph (dict subclass) with keys:
        {
            "schema_version": "1",
            "roots": [int, ...],
            "nodes": {str(value): {"depth": int, "tags"?: [str, ...]}, ...},
            "edges": [{"from": A, "to": B, "op": op_id}, ...],
            "pseudo_edges": [{"from": A, "op": op_id}, ...],
            "op_order": [str, ...],          # distinct op ids, rule-then-default order
            "op_labels": {op_id: label, ...}  # display label per op id
        }

        The returned Graph supports fluent chaining::

            build(...).to_dot().render()
            build(...).tap(write(file="g.json")).to_dot().render()

    `schema_version` matches the path segment of the bundled JSON Schema
    (`schemas/v1/graph.schema.json`). Breaking changes bump the major and
    ship under `/v2/` with v1 frozen.
    """
    from .graph import Graph
    if on_limit not in ("raise", "stop"):
        raise ValueError(f"on_limit must be 'raise' or 'stop', got {on_limit!r}")
    if isinstance(start, int):
        start = [start]
    tags = tags or {}
    resolve_key_type = _make_key_type_resolver(key_type)

    rules = list(rules)
    for r in rules:
        if not isinstance(r, Rule):
            raise TypeError(f"rules must contain Rule instances; "
                            f"got {type(r).__name__}")
    if default is not None and not isinstance(default, Op):
        raise TypeError(f"default must be Op or None; "
                        f"got {type(default).__name__}")

    op_order = []
    op_labels = {}
    seen_ops = set()
    id_funcs = {}  # op.id → first func seen; used for collision check

    def _register_op(op):
        if op.id not in seen_ops:
            seen_ops.add(op.id)
            op_order.append(op.id)
            op_labels[op.id] = op.label
            id_funcs[op.id] = op.func
            return
        # Same id twice — benign if the funcs are the same Python
        # object (user reused a bound Op) or if the labels also agree.
        # Otherwise there is likely a collision that will silently merge
        # two semantically distinct ops in op_order and op_colors.
        prior_func = id_funcs[op.id]
        prior_label = op_labels[op.id]
        if prior_func is op.func:
            return
        if prior_label == op.label:
            return
        import warnings
        # stacklevel=3: warn → _register_op → build() body → user's
        # call to build().  Fragile if the nesting depth changes — if
        # _register_op is inlined, drop to 2; if an intermediate helper
        # is added between build() and _register_op, raise to 4.
        warnings.warn(
            f"Op id collision on {op.id!r}: "
            f"two distinct callables produce the same id "
            f"(labels {prior_label!r} and {op.label!r}). "
            "Pass id=... on one of them to disambiguate, or "
            "accept the merge if this is intentional.",
            UserWarning,
            stacklevel=3,
        )

    for rule in rules:
        _register_op(rule.op)
    if default is not None:
        _register_op(default)

    deadline = None
    if time_limit is not None:
        h, m, s = map(int, time_limit.split(":"))
        deadline = time.time() + h * 3600 + m * 60 + s

    graph = Graph({"schema_version": "1",
                   "roots": list(start), "nodes": {}, "edges": [],
                   "pseudo_edges": [], "op_order": op_order,
                   "op_labels": op_labels})
    seen_edges = set()
    seen_pseudo = set()

    def make_node(x, depth):
        info = {"depth": depth, "key_type": resolve_key_type(x)}
        node_tags = [name for name, fn in tags.items() if fn(x)]
        if node_tags:
            info["tags"] = node_tags
        return info

    def add_edge(a, b, op):
        key = (str(a), str(b))
        if key not in seen_edges:
            graph["edges"].append({"from": str(a), "to": str(b), "op": op})
            seen_edges.add(key)

    def add_pseudo(x, label):
        key = (str(x), label)
        if key not in seen_pseudo:
            graph["pseudo_edges"].append({"from": str(x), "op": label})
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
        warnings.warn(
            f"build: {reason} reached {context}; output is truncated. "
            f"Pass a higher limit or None to disable.",
            UserWarning,
            stacklevel=4,
        )
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
        add_edge(x, nxt, op.id)
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
    depth_limited = False
    while frontier:
        at_max = max_depth is not None and depth >= max_depth
        if at_max:
            depth_limited = True
        next_frontier = []
        for x in frontier:
            any_matched = False
            for rule in rules:
                if not rule.condition(x):
                    continue
                any_matched = True
                if at_max or (rule.bound is not None and not rule.bound(x)):
                    add_pseudo(x, rule.op.id)
                    continue
                done, nxt = fire(x, rule.op, depth + 1)
                if done is not None:
                    return done
                if nxt is not None:
                    next_frontier.append(nxt)
            if not any_matched and default is not None:
                if at_max:
                    add_pseudo(x, default.id)
                else:
                    done, nxt = fire(x, default, depth + 1)
                    if done is not None:
                        return done
                    if nxt is not None:
                        next_frontier.append(nxt)
        depth += 1
        frontier = next_frontier

    if depth_limited and on_limit != "raise":
        warnings.warn(
            f"build: max_depth={max_depth} reached; output is truncated. "
            f"Pass a higher max_depth or None to disable.",
            UserWarning,
            stacklevel=2,
        )

    return graph
