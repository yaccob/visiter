import time
from collections import namedtuple

Op = namedtuple("Op", ["func", "label"])
Rule = namedtuple("Rule", ["condition", "op", "bound"])
Rule.__new__.__defaults__ = (None,)


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
        info = {"depth": depth}
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


def main():
    """CLI: pass iterate's argument list as a single Python expression.

    The argument string is spliced into `iterate(<argstring>)` and evaluated
    with `Rule`, `Op`, and `iterate` itself available in the namespace. The
    resulting graph is dumped as JSON on stdout.

    Example:
        visiter iterate 'range(1, 30),
            [Rule(lambda x: x%3==0, Op(lambda x: x//3, "÷3"))],
            default=Op(lambda x: x+2, "+2")'
    """
    import json
    import sys

    if len(sys.argv) != 2:
        sys.stderr.write(
            "usage: visiter iterate 'ARGSTRING'\n"
            "  ARGSTRING is spliced into iterate(<ARGSTRING>) and eval'd.\n"
            "  Example:\n"
            "    visiter iterate 'range(1, 30), "
            "[Rule(lambda x: x%3==0, Op(lambda x: x//3, \"÷3\"))], "
            "default=Op(lambda x: x+2, \"+2\")'\n"
        )
        sys.exit(2)

    ns = {"Rule": Rule, "Op": Op, "iterate": iterate}
    graph = eval(f"iterate({sys.argv[1]})", ns)
    json.dump(graph, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
