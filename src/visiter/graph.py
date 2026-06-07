"""Graph — dict subclass returned by ``Builder.build()``.

The Graph class inherits from dict, so all existing dict-based operations
(indexing, json.dump, etc.) work unchanged. It adds fluent methods for
the visiter pipeline:

    viter(...).case(...).default(...).build()   → Graph
      .tap(func)                                → Graph (side effect, returns self)
      .filter(filter_obj)                       → Graph (transform via filter protocol)
      .to_dot(...)                              → Dot   (convert to Graphviz representation)

Side effects (saving, logging, inspection) are always wrapped in .tap()
to make them visually distinct from transformations when reading a chain.
"""

import json
import logging
import sys

logger = logging.getLogger("visiter")


class Graph(dict):
    """A visiter graph dict with fluent pipeline methods.

    Inherits from dict so it is fully backward-compatible with code
    that treats the build() result as a plain dict.
    """

    def tap(self, func):
        """Call *func(self)* for its side effect, then return self.

        Use for saving snapshots, logging, or inspection without
        breaking the chain::

            viter(...).case(...).default(...).build() \\
                .tap(write(file="g.json")) \\
                .to_dot().render()
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
        # Lazy import: to_dot imports Graph for typing, so pulling it in
        # at the top would cycle.
        from .to_dot import to_dot as _to_dot
        return _to_dot(self, **kwargs)

    def write(self, file=None, **kwargs):
        """Write the graph as JSON.

        With no arguments, writes to stdout.  With ``file=``, writes to
        that path.  Extra *kwargs* are forwarded to ``json.dump``
        (e.g. ``indent``).

        This is a convenience for use inside ``.tap()``::

            viter(...).case(...).default(...).build() \\
                .tap(write(file="g.json"))

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

    def to_arrow(self):
        """Return ``(nodes, edges, pseudo_edges)`` as pyarrow Tables.

        The columnar view for analytics: edges reference nodes by int32 id,
        categorical columns are dictionary-encoded. Requires the ``[storage]``
        extra (pyarrow).
        """
        from .storage import to_arrow
        return to_arrow(self)

    def to_vitgraph(self, path, *, compression="zstd"):
        """Write this graph to a single columnar ``.vitgraph`` file.

        Arrow IPC + zstd in a zip container — ~10-26x smaller than JSON with
        much faster load. Requires the ``[storage]`` extra (pyarrow). Returns
        self for chaining (usable inside ``.tap()``).
        """
        from .storage import to_vitgraph
        return to_vitgraph(self, path, compression=compression)

    @classmethod
    def from_vitgraph(cls, path):
        """Read a ``.vitgraph`` file back into a Graph."""
        from .storage import from_vitgraph
        return from_vitgraph(path)


def _subset_graph(graph, anchor, radius, direction):
    """Induce the radius-hop neighborhood plus its boundary as a new Graph.

    Mirrors the native ``view_vitgraph`` subset exactly: kept nodes (within
    ``radius`` hops of ``anchor`` under ``direction``) plus the non-kept
    endpoints of any boundary-crossing edge, all edges incident to a kept node,
    and pseudo-edges from kept nodes. The boundary is what lets a later
    ``to_dot(anchor, radius)`` reproduce ghost stubs at the cut.
    """
    from .to_dot import _bfs_neighborhood
    keep = _bfs_neighborhood(graph, anchor, radius, direction)
    in_subset = set(keep)
    for e in graph["edges"]:
        s, d = str(e["from"]), str(e["to"])
        if (s in keep) != (d in keep):
            in_subset.add(s)
            in_subset.add(d)
    return Graph({
        "schema_version": graph.get("schema_version", "1"),
        "roots": graph.get("roots", []),
        "nodes": {v: info for v, info in graph["nodes"].items()
                  if v in in_subset},
        "edges": [e for e in graph["edges"]
                  if str(e["from"]) in keep or str(e["to"]) in keep],
        "pseudo_edges": [pe for pe in graph.get("pseudo_edges", [])
                         if str(pe["from"]) in keep],
        "op_order": graph.get("op_order", []),
        "op_labels": graph.get("op_labels", {}),
    })


class GraphHandle(Graph):
    """A lazily-materialized :class:`Graph`.

    ``build()`` returns this for the ``lang="rust"`` path. The native BFS
    output is persisted content-addressed, but it is **not** parsed into a
    Python dict until the graph is first touched. Until then the handle is an
    empty dict that carries only the build recipe (its ``materializer``).

    On the first dict-ish access (indexing, ``==``, ``len``, iteration, the
    fluent methods, …) the handle materializes **once**: it parses the build
    output, fills its own storage in place and then behaves exactly like a
    fully-populated :class:`Graph`. ``materialize()`` forces this explicitly.

    The deferral is what removes the build-time materialization wall: a build
    you never read (e.g. one you only persist or hand to another tool) never
    pays the parse, and an identical re-build is served from the content-
    addressed cache without re-running the native binary.

    Visible cost: an info-level log on first materialization and the
    :attr:`is_materialized` flag. **C-API caveat:** ``json.dumps(handle)``,
    ``dict(handle)`` and ``{**handle}`` read the underlying storage directly
    and bypass these hooks — on an *untouched* handle they see an empty dict.
    Use ``handle.write()`` (the blessed JSON path, which materializes first)
    or call ``handle.materialize()`` before such operations.
    """

    @classmethod
    def materialized(cls, graph, *, vitgraph_writer=None, crop_fn=None):
        """Wrap an already-built :class:`Graph` as a pre-materialized handle.

        The non-deferred build paths (pure Python, the native PyO3 engine) have
        the graph in hand already; wrapping it here gives them the uniform
        handle API (``.view()``, ``.to_vitgraph()``, ``.is_materialized``)
        while behaving exactly like the populated dict they returned before.
        """
        h = cls(lambda: graph, graph_key=None,
                vitgraph_writer=vitgraph_writer, crop_fn=crop_fn)
        dict.update(h, graph)
        h._materialized = True
        h._materializer = None
        return h

    def __init__(self, materializer, *, graph_key=None, vitgraph_writer=None,
                 crop_fn=None):
        super().__init__()
        # Plain attributes; a dict subclass keeps a normal __dict__.
        self._materializer = materializer
        self._materialized = False
        self._graph_key = graph_key
        # Optional native fast path: write the columnar .vitgraph straight from
        # the build output without materializing the full graph in Python.
        self._vitgraph_writer = vitgraph_writer
        # Optional native fast path: compute a crop (anchor/radius, max_depth,
        # value_range, or any combination) without materializing the full graph.
        # Called as crop_fn(anchor=, radius=, direction=, max_depth=, value_range=)
        # and returns (subset_handle, keep_keys), or None to signal fallback.
        self._crop_fn = crop_fn

    @property
    def is_materialized(self):
        """Whether the graph has been parsed into this dict yet."""
        return self._materialized

    @property
    def graph_key(self):
        """Content-address of the persisted build output (or ``None``)."""
        return self._graph_key

    def materialize(self):
        """Force materialization and return ``self`` (now a populated Graph)."""
        self._ensure()
        return self

    def _ensure(self):
        if self._materialized:
            return
        data = self._materializer()
        # Fill at the C level so the underlying storage is populated without
        # recursing back through the overridden Python hooks.
        dict.update(self, data)
        self._materialized = True
        self._materializer = None
        logger.info("materialized graph: %d nodes [%s]",
                    len(dict.__getitem__(self, "nodes")), self._graph_key)

    # --- access hooks: each triggers a one-time materialization -------------
    def __getitem__(self, key):
        self._ensure()
        return super().__getitem__(key)

    def __contains__(self, key):
        self._ensure()
        return super().__contains__(key)

    def __iter__(self):
        self._ensure()
        return super().__iter__()

    def __len__(self):
        self._ensure()
        return super().__len__()

    def __eq__(self, other):
        self._ensure()
        if isinstance(other, GraphHandle):
            other._ensure()
        return dict.__eq__(self, other)

    __hash__ = None

    def get(self, key, default=None):
        self._ensure()
        return super().get(key, default)

    def keys(self):
        self._ensure()
        return super().keys()

    def values(self):
        self._ensure()
        return super().values()

    def items(self):
        self._ensure()
        return super().items()

    def write(self, file=None, **kwargs):
        # json.dump reads the underlying storage via the C API and bypasses
        # the access hooks, so materialize explicitly before serializing.
        self._ensure()
        return super().write(file=file, **kwargs)

    def to_vitgraph(self, path, *, compression="zstd"):
        # Native fast path: emit the columnar store straight from the build
        # output, leaving the handle unmaterialized. Falls back to the Python
        # storage path (which materializes) if the native writer is absent or
        # declines (e.g. native engine not installed).
        if self._vitgraph_writer is not None and compression == "zstd":
            if self._vitgraph_writer(path):
                return self
        self._ensure()
        return super().to_vitgraph(path, compression=compression)

    def view(self, anchor, radius, direction="both"):
        """Return the *radius*-hop neighborhood of *anchor* as a new graph.

        Uses the native subset query (no full-graph materialization) when
        available; otherwise materializes and crops in Python. The result
        contains the kept nodes plus their direct edge-neighbors (the boundary),
        so a subsequent ``to_dot(anchor, radius)`` reproduces the same crop —
        including ghost stubs — as cropping the full graph.
        """
        if self._crop_fn is not None and not self._materialized:
            r = self._crop_fn(anchor=anchor, radius=radius, direction=direction)
            if r is not None:
                return r[0]
        self._ensure()
        return _subset_graph(self, anchor, radius, direction)

    def to_dot(self, **kwargs):
        # Native crop fast path: any crop (anchor/radius, max_depth, value_range,
        # or a combination) is computed natively — keep set plus boundary — so the
        # full graph is never materialized; to_dot then renders from the
        # precomputed keep, reproducing the same DOT (ghost stubs included).
        anchor = kwargs.get("anchor")
        radius = kwargs.get("radius")
        max_depth = kwargs.get("max_depth")
        value_range = kwargs.get("value_range")
        has_crop = (anchor is not None or radius is not None
                    or max_depth is not None or value_range is not None)
        anchor_paired = (anchor is None) == (radius is None)
        if (self._crop_fn is not None and not self._materialized
                and has_crop and anchor_paired):
            r = self._crop_fn(anchor=anchor, radius=radius,
                              direction=kwargs.get("direction", "both"),
                              max_depth=max_depth, value_range=value_range)
            if r is not None:
                subset, keep_keys = r
                styling = {k: v for k, v in kwargs.items()
                           if k not in ("anchor", "radius", "direction",
                                        "max_depth", "value_range")}
                return subset.to_dot(_keep=keep_keys, **styling)
        self._ensure()
        return super().to_dot(**kwargs)

    def __repr__(self):
        if not self._materialized:
            return f"<GraphHandle unmaterialized graph_key={self._graph_key}>"
        return super().__repr__()
