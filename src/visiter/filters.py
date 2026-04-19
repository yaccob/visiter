"""Filter protocol and predefined filters for the visiter fluent pipeline.

Filters transform a Graph in the chain::

    viter(...).case(...).default(...).build() \\
        .filter(NxFilter(nx.condensation)) \\
        .to_dot().render()

A filter is a callable that accepts a Graph (dict subclass) and returns
a Graph (or a plain dict, which Graph.filter() wraps automatically).
The filter is responsible for converting to/from any foreign domain
(e.g. NetworkX) internally.
"""

from .graph import Graph


class NxFilter:
    """Filter that bridges to NetworkX for graph-to-graph transforms.

    Wraps a NetworkX function that takes a ``nx.DiGraph`` and returns
    a ``nx.DiGraph``.  Handles the VisIter ↔ NetworkX conversion
    internally::

        from visiter import NxFilter
        import networkx as nx

        viter(...).case(...).default(...).build() \\
            .filter(NxFilter(nx.condensation)) \\
            .to_dot().render()

    The filter uses ``visiter.analytics.to_networkx`` and
    ``from_networkx`` for the round-trip.
    """

    def __init__(self, func):
        self._func = func

    def __call__(self, graph):
        from .analytics import to_networkx, from_networkx
        nxg = to_networkx(graph)
        result = self._func(nxg)
        return Graph(from_networkx(result))

    def __repr__(self):
        return f"NxFilter({self._func!r})"
