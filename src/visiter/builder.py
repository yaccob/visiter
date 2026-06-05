"""Fluent builder API for viter().

`viter(iterable, **options)` returns a Builder. Chain .case()/.cases()/
.default() to describe the iteration graph, then .build() to materialize
a Graph (or .render() as a one-shot shortcut for
build().to_dot().render()).

Every chain method returns a new Builder; the original is unchanged,
which lets callers branch a shared prefix into divergent graphs.
"""

from collections import namedtuple
from enum import Enum


class Match(str, Enum):
    """How case conditions compose into outgoing edges.

    - Match.ALL (default): every case whose condition matches fires,
      which may produce a multi-edge fan-out at a node. Default fires
      only if no case matched.
    - Match.FIRST: the first matching case fires exclusively; later
      cases and the default are short-circuited. Gives if-elif-else
      semantics.
    """
    ALL = "all"
    FIRST = "first"


class OnLimit(str, Enum):
    """Behavior when max_depth, max_nodes, or time_limit is hit."""
    STOP = "stop"
    RAISE = "raise"


_Case = namedtuple("_Case",
                   ["condition", "fn", "label", "id", "bound", "exclusive"])
_Default = namedtuple("_Default", ["fn", "label", "id"])
_UNSET = object()


class Builder:
    """Immutable, chainable builder accumulating cases and options."""

    __slots__ = ("_iterable", "_cases", "_default", "_options")

    def __init__(self, iterable, cases=(), default=_UNSET, options=None):
        self._iterable = iterable
        self._cases = tuple(cases)
        self._default = default
        self._options = dict(options) if options else {}

    def _with(self, **kw):
        return Builder(
            kw.get("iterable", self._iterable),
            cases=kw.get("cases", self._cases),
            default=kw.get("default", self._default),
            options=kw.get("options", self._options),
        )

    def case(self, condition, fn, *, label=None, id=None, bound=None,
             exclusive=None):
        """Add a guarded case to the chain.

        `condition(x)` decides applicability; `fn(x)` produces the
        successor — either a plain value, or an
        ``OpResult(value, label=…)`` to override this case's static
        ``label`` for that one edge. If the case matches and
        ``exclusive=True``, later cases and the default are skipped for
        that x. `bound(x)` (optional) separates "op applies" from "stop
        here anyway" — a False bound records a pseudo-edge instead of a
        real successor.

        `label` is the case's static edge label. It is the value that
        ends up on every edge produced by this case unless ``fn``
        returns an ``OpResult`` with a non-None label.

        `exclusive=None` (the default) lets the chain-level `match=` mode
        decide: Match.ALL → not exclusive, Match.FIRST → exclusive. An
        explicit True/False overrides the mode for this case only.
        """
        return self._with(cases=self._cases + (
            _Case(condition, fn, label, id, bound, exclusive),))

    def cases(self, iterable):
        """Add multiple cases from an iterable.

        Each item is ``(cond, fn)`` or ``(cond, fn, kwargs_dict)`` where
        the dict may carry label, id, bound, exclusive.
        """
        b = self
        for item in iterable:
            if len(item) == 2:
                cond, fn = item
                b = b.case(cond, fn)
            elif len(item) == 3:
                cond, fn, kw = item
                b = b.case(cond, fn, **kw)
            else:
                raise ValueError(
                    "cases items must be (cond, fn) or (cond, fn, kwargs)")
        return b

    def default(self, fn=None, *, label=None, id=None):
        """Set the fallback op (fires only when no case matched).

        Behaves identically to ``case`` regarding the return value of
        ``fn``: a plain value uses the static ``label``; an
        ``OpResult(value, label=…)`` overrides per call. ``default`` is
        not a "failure" branch — it is just the case without an explicit
        condition.

        Calling .default() more than once raises RuntimeError — the
        fallback is a singleton. `fn=None` (also the omitted-call state)
        means values with no matching case are terminal leaves.
        """
        if self._default is not _UNSET:
            raise RuntimeError("default already set")
        return self._with(default=_Default(fn, label, id))

    def build(self):
        """Materialize the accumulated cases as a Graph."""
        match_mode = self._options.get("match", Match.ALL)
        default_exclusive = (match_mode == Match.FIRST)

        if self._options.get("lang", "python") == "rust":
            return self._build_rust(default_exclusive)

        # Lazy import: keeps Rule/Op out of the public `visiter` surface
        # while still letting the Builder translate cases into them.
        from .iteration import Op, Rule, build as _build

        rules = []
        for c in self._cases:
            op = Op(c.fn, label=c.label, id=c.id)
            eff_exclusive = default_exclusive if c.exclusive is None else c.exclusive
            rules.append(Rule(c.condition, op, c.bound, eff_exclusive))

        default_op = None
        if self._default is not _UNSET and self._default.fn is not None:
            d = self._default
            default_op = Op(d.fn, label=d.label, id=d.id)

        # `lang`/`consts` are Builder-level (Path B) options, not build() kwargs.
        skip = {"match", "lang", "consts"}
        build_kwargs = {k: v for k, v in self._options.items() if k not in skip}
        if isinstance(build_kwargs.get("on_limit"), OnLimit):
            build_kwargs["on_limit"] = build_kwargs["on_limit"].value

        return _build(self._iterable, rules, default_op, **build_kwargs)

    def _build_rust(self, default_exclusive):
        """Path B: compile the Rust-string cases and run the native BFS.

        ``.case()`` / ``.default()`` / ``bound=`` / ``tags=`` carried Rust
        expression strings (value bound to ``s``). Defaults, bounds, and
        ``time_limit`` match the Python path exactly (``max_depth=64``,
        ``max_nodes=1024``), including ghost-stub pseudo-edges. ``OpResult`` is
        not yet supported and raises rather than diverging silently.
        """
        from .builder import OnLimit
        from .rustgen import build_rust

        # Same defaults as iteration.build, so the rust path is a drop-in.
        max_depth = self._options.get("max_depth", 64)
        max_nodes = self._options.get("max_nodes", 1024)
        time_limit = self._options.get("time_limit")
        on_limit = self._options.get("on_limit", "stop")
        if isinstance(on_limit, OnLimit):
            on_limit = on_limit.value

        starts = ([self._iterable] if isinstance(self._iterable, int)
                  else list(self._iterable))
        cases = []
        for c in self._cases:
            eff_exclusive = (default_exclusive if c.exclusive is None
                             else c.exclusive)
            cases.append((c.condition, c.fn, c.label, c.id, c.bound,
                          eff_exclusive))
        default = None
        if self._default is not _UNSET and self._default.fn is not None:
            d = self._default
            default = (d.fn, d.label, d.id)

        return build_rust(starts, cases, default,
                          consts=self._options.get("consts"),
                          key_type=self._options.get("key_type"),
                          tags=self._options.get("tags"),
                          max_depth=max_depth, max_nodes=max_nodes,
                          time_limit=time_limit, on_limit=on_limit)

    def render(self, format="svg", file=None):
        """One-shot shortcut: build, convert to Dot, render.

        Accepts only the final render parameters. Use the explicit path
        ``builder.build().to_dot(...).render(...)`` when to_dot() needs
        configuration (colors, cropping, ghost stubs, node labels).
        """
        return self.build().to_dot().render(format=format, file=file)


def viter(iterable, *, match=Match.ALL, **options):
    """Entry point for the fluent viter pipeline.

    Returns a Builder. Kwargs other than `match` (max_depth, max_nodes,
    on_limit, time_limit, tags, key_type, engine) are forwarded to the
    internal build() call when the chain is materialized.

    `engine` selects the BFS backend: "auto" (default) uses the optional
    native engine when it is installed and the build is unbounded
    (max_depth/max_nodes/time_limit unset, no bound), else pure Python;
    "native" requires it; "python" forces pure Python. The native path
    produces a byte-identical Graph — pure Python is always available.

    `lang="rust"` (Path B) switches the chain to inline Rust-expression
    callbacks: `.case()` / `.default()` / `bound=` / `tags=` then take Rust
    expression *strings* (the current value is bound to `s`) which are compiled
    on the fly with `rustc` and run natively. `consts={"N": ...}` injects i64
    constants the expressions can reference. It is a drop-in — same chain, same
    graph (bounds, ghost stubs, tags and all). Requires `rustc` on PATH;
    supports int/tuple-of-int/str state values; `time_limit` and `OpResult` are
    not supported (they raise rather than diverge).
    """
    opts = dict(options)
    opts["match"] = match
    return Builder(iterable, options=opts)
