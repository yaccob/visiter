"""Water jug helpers for the VisIter demo.

Two jugs with capacities A and B (default 3 and 5). Six actions:

    fill A      (a, b) → (A, b)
    fill B      (a, b) → (a, B)
    empty A     (a, b) → (0, b)
    empty B     (a, b) → (a, 0)
    A → B       pour A into B until B full or A empty
    B → A       pour B into A until A full or B empty

State is a (current_a, current_b) tuple. The graph from (0, 0)
contains cycles of varying length — filling, pouring, and emptying
create non-trivial round-trips because the actions are not
self-inverse.

Classic puzzle: "How do you measure exactly 4 litres with a 3L and
a 5L jug?" — the answer is a shortest path in this graph.
"""

from visiter import Op, Rule


def make_rules(cap_a, cap_b):
    """Return 6 Rules for the two-jug system."""
    return [
        # Fill
        Rule(lambda s, A=cap_a: s[0] < A,
             Op(lambda s, A=cap_a: (A, s[1]),
                label=f"fill {cap_a}L", id="fill_a")),
        Rule(lambda s, B=cap_b: s[1] < B,
             Op(lambda s, B=cap_b: (s[0], B),
                label=f"fill {cap_b}L", id="fill_b")),

        # Empty
        Rule(lambda s: s[0] > 0,
             Op(lambda s: (0, s[1]),
                label=f"empty {cap_a}L", id="empty_a")),
        Rule(lambda s: s[1] > 0,
             Op(lambda s: (s[0], 0),
                label=f"empty {cap_b}L", id="empty_b")),

        # Pour A → B
        Rule(lambda s, B=cap_b: s[0] > 0 and s[1] < B,
             Op(lambda s, B=cap_b: (max(0, s[0] - (B - s[1])),
                                    min(B, s[0] + s[1])),
                label=f"{cap_a}L→{cap_b}L", id="a_to_b")),

        # Pour B → A
        Rule(lambda s, A=cap_a: s[1] > 0 and s[0] < A,
             Op(lambda s, A=cap_a: (min(A, s[0] + s[1]),
                                    max(0, s[1] - (A - s[0]))),
                label=f"{cap_b}L→{cap_a}L", id="b_to_a")),
    ]


def state_label(state, target=None):
    """Format a (a, b) state as an HTML table for Graphviz display.

    When *target* is given, any cell whose value equals the target is
    rendered in bold — a visual marker for "this jug holds the goal
    amount", independent of the highlight tag (which marks the
    shortest-path nodes via fill-darkening).
    """
    a, b = state

    def _cell(val):
        display = f"<B>{val}</B>" if target is not None and val == target else str(val)
        return f'<TD WIDTH="20" HEIGHT="18" FIXEDSIZE="TRUE">{display}</TD>'

    return (f'<<TABLE BORDER="0" CELLSPACING="2" CELLPADDING="2">'
            f'<TR>{_cell(a)}{_cell(b)}</TR></TABLE>>')


def make_node_label(target):
    """Return a ``node_label`` callback for ``to_dot``.

    The callback formats each node key as an HTML table and bolds
    cell values that equal *target*.
    """
    def _label(key, _info):
        state = tuple(int(x) for x in key.strip("()").split(", "))
        return state_label(state, target=target)
    return _label


def shortest_path_subgraph(graph, source, target):
    """Return a NetworkX subgraph of all shortest paths to *target*.

    *graph* is a ``networkx.DiGraph`` (as provided by ``visiter
    analyze``'s eval namespace). *source* is the start node id
    (string). *target* is the integer target amount — any node where
    either jug holds that amount is a goal.

    Returns a ``networkx.DiGraph`` containing only the nodes and edges
    on the globally shortest path(s). Goal nodes carry a ``highlight``
    tag so ``to_dot`` darkens them.
    """
    import networkx as nx

    goals = [n for n in graph.nodes
             if any(int(x) == target
                    for x in n.strip("()").split(", "))]

    best_len = None
    all_paths = []
    for g in goals:
        try:
            paths = list(nx.all_shortest_paths(graph, source, g))
        except nx.NetworkXNoPath:
            continue
        plen = len(paths[0])
        if best_len is None or plen < best_len:
            best_len = plen
            all_paths = paths
        elif plen == best_len:
            all_paths.extend(paths)

    path_edges = set()
    for path in all_paths:
        for i in range(len(path) - 1):
            path_edges.add((path[i], path[i + 1]))

    sub = graph.edge_subgraph(path_edges).copy()

    # Tag goal nodes for highlighting.
    goal_set = set(p[-1] for p in all_paths)
    for n in sub.nodes:
        if n in goal_set:
            tags = list(sub.nodes[n].get("tags", []))
            if "highlight" not in tags:
                tags.append("highlight")
            sub.nodes[n]["tags"] = tags

    return sub
