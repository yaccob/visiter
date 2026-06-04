"""VisIter — build and visualize iteration graphs.

Public API:

    viter(iterable, *, max_depth=64, max_nodes=1024, match=Match.ALL, ...)
        Start a fluent Builder chain. Add cases via .case() / .cases(),
        optionally a .default(), then terminate with .build() (returns
        Graph) or .render() (shortcut for build().to_dot().render()).

    Match, OnLimit
        Enums controlling chain-level semantics:
        - Match.ALL / Match.FIRST: how case conditions compose (additive
          vs. first-match-wins).
        - OnLimit.STOP / OnLimit.RAISE: behavior when max_depth,
          max_nodes, or time_limit is hit.

    OpResult
        Optional return type for case/default fns that want a per-call
        edge label. Returning ``OpResult(value, label="…")`` overrides
        the case's static label for that one edge; returning a plain
        value (or ``OpResult(value)`` / ``OpResult(value, label=None)``)
        keeps the static label.

    Graph
        dict subclass returned by .build(), with fluent methods
        .to_dot(), .filter(), .tap(), .write().

    Dot
        Wrapper around graphviz.Digraph: .render(), .tap(), .source.

    to_dot(graph, *, anchor=..., radius=..., op_colors=..., ...)
        Standalone converter (equivalent to Graph.to_dot()).

Fluent pipeline::

    viter(range(1, 28)).case(...).default(...).render()
    viter(...).case(...).default(...).build().to_dot(...).render(...)
    viter(...).case(...).build().tap(write(file="g.json")).to_dot().render()
    viter(...).case(...).build().filter(NxFilter(nx.condensation)).to_dot().render()
"""

from .builder import Builder, Match, OnLimit, viter
from .dot import Dot
from .filters import NxFilter
from .graph import Graph
from .io import write
from .iteration import OpResult, parse_range
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

__version__ = "0.14.0"

__all__ = [
    # Core API
    "viter",
    "Builder",
    "Match",
    "OnLimit",
    "OpResult",
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
