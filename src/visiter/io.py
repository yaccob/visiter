"""I/O utilities for the visiter fluent pipeline.

Provides the ``write`` factory function used with ``.tap()``::

    build(...).tap(write()).to_dot().render()           # JSON → stdout
    build(...).tap(write(file="g.json")).to_dot().render()  # JSON → file
    build(...).to_dot().tap(write(file="g.dot")).render()   # DOT → file
    build(...).to_dot().tap(write())                        # DOT → stdout

``write`` auto-detects the format from the object type:
  - ``Graph`` (dict) → JSON
  - ``Dot`` → DOT source text
"""


def write(file=None, **kwargs):
    """Return a callable that writes an object in its natural format.

    Intended for use with ``.tap()``::

        graph.tap(write())                  # JSON to stdout
        graph.tap(write(file="out.json"))   # JSON to file
        dot.tap(write())                    # DOT source to stdout
        dot.tap(write(file="out.dot"))      # DOT source to file

    The returned callable delegates to the object's own ``.write()``
    method, passing through *file* and any extra keyword arguments.
    """
    def _writer(obj):
        obj.write(file=file, **kwargs)
    return _writer
