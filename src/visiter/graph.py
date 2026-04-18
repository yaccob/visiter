"""Graph — dict subclass returned by build(), entry point for the fluent API.

The Graph class inherits from dict, so all existing dict-based operations
(indexing, json.dump, etc.) work unchanged. It adds fluent methods for
the visiter pipeline:

    build(...)                       → Graph
      .tap(func)                     → Graph (side effect, returns self)
      .filter(filter_obj)            → Graph (transform via filter protocol)
      .to_dot(...)                   → Dot   (convert to Graphviz representation)

Side effects (saving, logging, inspection) are always wrapped in .tap()
to make them visually distinct from transformations when reading a chain.
"""

import json
import sys


class Graph(dict):
    """A visiter graph dict with fluent pipeline methods.

    Inherits from dict so it is fully backward-compatible with code
    that treats the build() result as a plain dict.
    """

    def tap(self, func):
        """Call *func(self)* for its side effect, then return self.

        Use for saving snapshots, logging, or inspection without
        breaking the chain::

            build(...).tap(write(file="g.json")).to_dot().render()
        """
        func(self)
        return self

    peek = tap  # alias

    def filter(self, filter_obj):
        """Apply a filter and return the transformed Graph.

        *filter_obj* must be a callable that accepts a Graph and returns
        a Graph (or a dict that will be wrapped in Graph).  For filters
        that work in a foreign domain (e.g. NetworkX), the filter object
        is responsible for converting to/from that domain internally.

        See ``NxFilter`` for the predefined NetworkX bridge.
        """
        result = filter_obj(self)
        if isinstance(result, Graph):
            return result
        return Graph(result)

    def to_dot(self, **kwargs):
        """Convert this graph to a Dot object for rendering.

        All keyword arguments are forwarded to the standalone
        ``to_dot()`` function (anchor, radius, direction, op_colors, …).
        Returns a ``Dot`` instance.
        """
        from .to_dot import to_dot as _to_dot
        return _to_dot(self, **kwargs)

    def write(self, file=None, **kwargs):
        """Write the graph as JSON.

        With no arguments, writes to stdout.  With ``file=``, writes to
        that path.  Extra *kwargs* are forwarded to ``json.dump``
        (e.g. ``indent``).

        This is a convenience for use inside ``.tap()``::

            build(...).tap(write(file="g.json"))

        But can also be called directly on a Graph instance.
        Returns self for chaining.
        """
        kwargs.setdefault("indent", 2)
        kwargs.setdefault("default", str)
        if file is None:
            json.dump(self, sys.stdout, **kwargs)
            sys.stdout.write("\n")
        else:
            with open(file, "w") as f:
                json.dump(self, f, **kwargs)
                f.write("\n")
        return self
