"""VisIter — build and visualize iteration graphs.

Public API:

    iterate(start, rules, *, default, max_depth=None, max_nodes=..., ...)
        Build a graph by applying guard-and-operation Rules from each start
        via BFS, tracking per-node depth and optional pseudo-edges for
        structural bounds.

    Op(func, label)
        An operation: a callable taking the current value, plus a label
        used for edge display and color keying.

    Rule(condition, op, bound=None)
        A guarded operation. Condition decides applicability; optional
        bound distinguishes "stop here" from "not applicable".

    to_dot(graph, *, anchor=..., radius=..., op_colors=..., ...)
        Turn an iterate-result into a Graphviz Digraph, with cropping,
        coloring, ghost stubs, and node annotations.
"""

from .iteration import Op, Rule, iterate, parse_range
from .to_dot import to_dot
from .render_helpers import (
    DEFAULT_OP_PALETTE,
    build_dot,
    darken,
    format_binary,
    format_op_label,
    format_prime_factors,
    format_ternary,
    node_attrs,
    parse_time_limit,
    resolve_op_colors,
)

__version__ = "0.3.0"

__all__ = [
    "Op",
    "Rule",
    "iterate",
    "parse_range",
    "to_dot",
    "DEFAULT_OP_PALETTE",
    "build_dot",
    "darken",
    "format_binary",
    "format_op_label",
    "format_prime_factors",
    "format_ternary",
    "node_attrs",
    "parse_time_limit",
    "resolve_op_colors",
    "__version__",
]
