"""VisIter — build and visualize iteration graphs.

Public API:

    build(start, rules, default, *, max_depth=64, max_nodes=1024, ...)
        Build a graph by applying guard-and-operation Rules from each start
        via BFS.  Returns a Graph (dict subclass) supporting fluent chaining.

    Op(func, *, label=None, id=None)
        An operation: a callable taking the current value, plus
        keyword-only fields — `label` (display string) and `id`
        (stable key for `op_order` and `op_colors` pinning).

    Rule(condition, op, bound=None)
        A guarded operation. Condition decides applicability; optional
        bound distinguishes "stop here" from "not applicable".

    to_dot(graph, *, anchor=..., radius=..., op_colors=..., ...)
        Turn a build-result into a Dot object for rendering.

    Graph
        dict subclass with fluent methods: .to_dot(), .filter(), .tap()

    Dot
        Wrapper around graphviz.Digraph: .render(), .tap(), .source

Fluent pipeline::

    build(...).to_dot().render()
    build(...).tap(write(file="g.json")).to_dot().render(file="out.svg")
    build(...).filter(NxFilter(nx.condensation)).to_dot().render()
"""

from .dot import Dot
from .filters import NxFilter
from .graph import Graph
from .io import write
from .iteration import Op, Rule, build, parse_range, viter
from .to_dot import to_dot
from .render_helpers import (
    DEFAULT_OP_PALETTE,
    build_dot,
    darken,
    format_binary,
    format_op_label,
    format_prime_factors,
    node_attrs,
    parse_time_limit,
    resolve_op_colors,
)

__version__ = "0.11.0"

__all__ = [
    # Core API
    "Op",
    "Rule",
    "build",
    "viter",
    "to_dot",
    "Graph",
    "Dot",
    # Filters
    "NxFilter",
    # I/O
    "write",
    # Utilities
    "parse_range",
    # Render helpers
    "DEFAULT_OP_PALETTE",
    "build_dot",
    "darken",
    "format_binary",
    "format_op_label",
    "format_prime_factors",
    "node_attrs",
    "parse_time_limit",
    "resolve_op_colors",
    # Version
    "__version__",
]
