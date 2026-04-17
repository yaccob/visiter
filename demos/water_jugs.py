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
