"""Dot — wrapper around graphviz.Digraph with fluent pipeline methods.

Returned by ``to_dot()`` and ``Graph.to_dot()``.  Provides:

    .render(format=, file=)   — render via Graphviz to stdout or file
    .tap(func)                — side-effect hook (returns self)
    .source                   — the raw DOT source text

Side effects (saving DOT source, logging) are wrapped in .tap() to
keep them visually distinct from the terminal .render() action.
"""

import sys
from pathlib import Path


class Dot:
    """Wrapper around a ``graphviz.Digraph`` with fluent pipeline methods."""

    def __init__(self, digraph):
        self._digraph = digraph

    @property
    def source(self):
        """The DOT source text."""
        return self._digraph.source

    def render(self, format="svg", file=None):
        """Render the graph via Graphviz.

        Without *file*, writes the rendered bytes to stdout.
        With *file*, writes to that path instead.

        Returns self so the call can be chained (e.g. to render
        multiple formats).
        """
        if format == "dot":
            # DOT source is text, not binary.
            text = self._digraph.source
            if file is None:
                sys.stdout.write(text)
                if not text.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.flush()
            else:
                Path(file).write_text(text, encoding="utf-8")
        else:
            data = self._digraph.pipe(format=format)
            if file is None:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            else:
                Path(file).write_bytes(data)
        return self

    def tap(self, func):
        """Call *func(self)* for its side effect, then return self.

        Use for saving DOT source snapshots or inspection::

            build(...).to_dot().tap(write(file="g.dot")).render()
        """
        func(self)
        return self

    peek = tap  # alias

    def write(self, file=None):
        """Write the DOT source text.

        Without *file*, writes to stdout.  With *file*, writes to that path.

        This is a convenience for use inside ``.tap()``::

            build(...).to_dot().tap(write(file="g.dot")).render()

        But can also be called directly.  Returns self for chaining.
        """
        if file is None:
            sys.stdout.write(self.source)
            if not self.source.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            Path(file).write_text(self.source, encoding="utf-8")
        return self
