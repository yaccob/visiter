# VisIter vs. the rest of the ecosystem

Python already has graph libraries, Graphviz wrappers, and state-machine
visualizers. Mathematica has `NestGraph`. Maude's `search` explores
rewrite systems. LoLA explores Petri-net reachability. This page is an
honest look at what overlaps with VisIter, what doesn't, and — in a
paragraph at the end — when **not** to use VisIter.

## What VisIter actually does

To save you scrolling: VisIter takes a starting value (or several), a
list of guard-and-operation rules, and an optional default. It runs a
BFS from the starts, applies whichever rule(s) match at each node,
records edges and per-node depth, emits pseudo-edges where `Rule.bound`
or `max_depth` suppressed expansion. A second stage (`to_dot`) turns
the resulting graph dict into a Graphviz drawing with cropping,
coloring, wedged-pie fills for branching nodes, and dashed "ghost
stubs" at every cut boundary. The graph dict has a published JSON
Schema. The `viter` CLI executes `.vit` files — self-contained Python
scripts that use the fluent API (`build(...).to_dot().render()`).

In one phrase: **orbit graphs for discrete iterations under guarded
rules**, with free/scriptable/Graphviz-native rendering.

## The direct superset nobody talks about in Python-land

**[Wolfram Mathematica's `NestGraph`](https://reference.wolfram.com/language/ref/NestGraph.html)**
is the closest thing to VisIter's core in any ecosystem. `NestGraph[f,
expr, n]` builds exactly a seed-plus-successor orbit graph; `f` can
return a list for multi-rule branching; rendering is inline. For
multiway rewriting there's
**[`ResourceFunction["MultiwaySystem"]`](https://resources.wolframcloud.com/FunctionRepository/resources/MultiwaySystem/)**
from the Wolfram Physics Project, with causal/branchial graph
extensions.

If you have a Mathematica license and live in notebooks, `NestGraph`
does what VisIter does and then some. The honest positioning is that
VisIter occupies the **free, scriptable, Graphviz-native**
version of this niche — plus an opinionated rendering layer (see
below).

What VisIter has that `NestGraph` doesn't:

- First-class guard-and-operation rule pairs (you can model this in
  `NestGraph` by making `f` a dispatch function, but there's no built-
  in notion of "this op applies here, that op doesn't").
- Pseudo-edges and ghost stubs as a distinct visual primitive for
  structural cutoffs (`Rule.bound`, `max_depth`, render-time crop).
- Op-label-driven stable palette (two invocations of the same rules
  produce the same colors).
- Wedged-pie multi-op node fills for branching nodes.
- A JSON-schema'd pipeline that saves the data layer once and lets you
  render it many different ways from shell scripts.

## Term rewriting

**[Maude](https://maude.cs.illinois.edu/)**'s `search` command does
BFS from a term under guarded rewrite rules with depth cutoffs —
structurally the closest cousin to VisIter in the term-rewriting
world.
- Does MORE: AC-matching, equational theories, strategy language,
  LTL model-checking.
- Does LESS: rendering is an afterthought (export to external `dot`),
  no cutoff-as-visual-primitive, no op-palette conventions.

**[K Framework](https://kframework.org/)** — rewriting for programming-
language semantics; visualization tertiary.

**[Stratego/XT](https://strategoxt.org/)** — strategic rewriting;
graph output not first-class.

## Model checking / state-space tools

**[LoLA](https://theo.informatik.uni-rostock.de/theo-forschung/tools/lola/)**
and **[TAPAAL](https://www.tapaal.net/)** explore Petri-net
reachability from an initial marking — the verification world's
structural twin. Reachability graph *is* the primary artifact.
- Does MORE: coverability, deadlock analysis, CTL/LTL.
- Does LESS: Petri-net-shaped rules only. You can't say "apply `x
  // 3` when x is divisible by three" — you'd have to encode it as a
  Petri net first.

**[SPIN](https://spinroot.com/)** exports its explored state space to
Graphviz (`spin -M`), but verification, not orbit rendering, is the
intent.

**[NuSMV / nuXmv](https://nusmv.fbk.eu/)** — symbolic, so produces
counterexample traces rather than orbit graphs.

**[UPPAAL](https://uppaal.org/)** — timed automata; the visual is the
model, not the seed's orbit.

## Python ecosystem

**[NetworkX](https://networkx.org/)** — generic graph library with
`bfs_tree`, `bfs_edges`, Graphviz export via `nx_agraph` / `nx_pydot`,
and hundreds of algorithms. You'd hand-roll the BFS-with-rules loop,
the op-label coloring, the ghost-stub rendering. If you already hold
your graph in a NetworkX `DiGraph`, you don't need VisIter to build
it — but you could feed it to `to_dot` if the rendering model
appeals.

**[graphviz (Python)](https://pypi.org/project/graphviz/)** and
**[pygraphviz](https://pygraphviz.github.io/)** are DOT builders with
no graph semantics. VisIter uses `graphviz` as its backend.

Several single-purpose PyPI packages and one-off notebooks exist for
specific number-theoretic iterations (one map, hard-coded). No
general, reusable iteration-graph plotter on PyPI.

**[d3-graphviz](https://github.com/magjac/d3-graphviz)** /
**Cytoscape.js** — rendering only, no rule engine.

## A note on state machines

People occasionally assume this kind of tool is about finite state
machines (FSMs). It isn't. VisIter doesn't have states, an alphabet,
or an accept set — it has values and a successor relation derived
from rules. That makes it sibling to orbit-graph / reachability-graph
tooling (NestGraph, Maude's `search`, LoLA), not to FSM designers
like **[transitions](https://github.com/pytransitions/transitions)**,
**[python-statemachine](https://github.com/fgmacedo/python-statemachine)**,
**[xstate](https://stately.ai/viz)**, or
**[automata-lib](https://github.com/caleb531/automata)**. If you want
to render the static design of a known state machine, use one of
those — they render what you declared. VisIter renders what a seed
actually reaches when rules are applied.

## Continuous dynamics (different problem)

**[PyDSTool](https://pydstool.sourceforge.io/)**,
**[nolds](https://github.com/CSchoel/nolds)**,
**[pynamical](https://github.com/gboeing/pynamical)** visualize
continuous dynamical systems via phase portraits, bifurcation
diagrams, Lyapunov exponents — different output modality from
discrete reachability graphs.

## Feature matrix

| capability                                          | VisIter | NetworkX | NestGraph | Maude | LoLA |
| --------------------------------------------------- | :-----: | :------: | :-------: | :---: | :--: |
| Seed + rules → orbit graph                          |    ✓    |    —¹    |     ✓     |   ✓   |  ✓²  |
| Free (not paywalled)                                |    ✓    |    ✓     |     —     |   ✓   |  ✓   |
| Scriptable / non-interactive                        |    ✓    |    ✓³    |     —     |  ✓³   |  ✓³  |
| Guard + op as a first-class pair                    |    ✓    |    —     |     —     |   ✓   |  ✓²  |
| Arbitrary hashable values as nodes                  |    ✓    |    ✓     |     ✓     |  ✓⁴   |  —   |
| Pseudo-edges for structural cutoffs                 |    ✓    |    —     |     —     |   —   |  —   |
| Dashed ghost stubs at boundaries                    |    ✓    |    —     |     —     |   —   |  —   |
| Op-label-driven stable coloring                     |    ✓    |    —     |     —     |   —   |  —   |
| Wedged-pie fills for branching nodes                |    ✓    |    —     |     —     |   —   |  —   |
| Anchor/radius cropping at render time               |    ✓    |    —     |    ✓⁵     |   —   |  —   |
| JSON Schema for graph dict                          |    ✓    |    —     |     —     |   —   |  —   |
| Hundreds of graph algorithms                        |   ✓⁶    |    ✓     |     ✓     |   —   |  —   |
| Formal verification (CTL/LTL)                       |    —    |    —     |     —     |   ✓   |  ✓   |

¹ NetworkX can do this, but the wiring is yours to write.
² For Petri-net-shaped rules only.
³ Strictly: invocable from a script, but not designed around
  scriptable composition like VisIter's `.vit` files.
⁴ Any term in the user's signature, not any hashable Python object.
⁵ Via `NeighborhoodGraph` / `Subgraph`; separate primitive.
⁶ Via the `[analytics]` extra, which bridges to NetworkX: install with
  `pip install visiter[analytics]`, then use `NxFilter` in the fluent
  chain or `visiter.analytics.to_networkx` directly. See
  [manual §7](manual.md#7-integrating-with-networkx).

Every ✓ in the VisIter column is demonstrated by a runnable `.vit`
file in [`demos/`](../demos/); see [`demos/README.md`](../demos/README.md)
for the full list.

## When **not** to reach for VisIter

- **You have a Mathematica license and live in notebooks.** Use
  `NestGraph` and the Wolfram Function Repository's orbit-graph
  utilities. Mature, interactive, better integrated with symbolic
  math.
- **You're doing term rewriting with equational theories or LTL
  verification.** Maude and K Framework dwarf VisIter's rule model.
- **Your rules fit a Petri net** and you want deadlock/coverability
  analysis on top. Use LoLA.
- **You need graph analytics** (centrality, shortest paths, community
  detection). NetworkX.
- **Your "iteration" is continuous** (ODEs, chaotic maps on ℝ). Phase
  portraits beat reachability graphs; use PyDSTool, pynamical, or
  matplotlib directly.
- **You already have a `DiGraph` in hand.** Render it directly —
  VisIter's `to_dot` can consume any dict that matches the
  [schema](../schemas/v1/graph.schema.json), but that's only worth it
  if you want the coloring/cropping/ghost-stub conventions.
- **You want to draw the design of a known state machine.** That's a
  different tool category entirely; see the note above.

## When VisIter *is* the right tool

- You have a discrete rule-based iteration (number-theoretic
  orbits, divisor-descent chains, toy rewriting systems, automaton
  explorations) and you want to *see* what a seed actually reaches,
  in Python, without a Mathematica license.
- You want the rendering to carry semantic meaning — "this is a
  leaf", "this got stopped by a bound", "this got cropped at the
  render boundary" — as a distinct visual primitive, without
  inventing your own vocabulary.
- You want the data stage and the render stage decoupled — save JSON
  via `.tap(write(...))`, render it many ways, or validate it against
  a schema; or keep the graph for later re-analysis.
- You want scriptable `.vit` files rather than a REPL session.

## Honest positioning

VisIter is not a reimplementation of anything. But it is **not a
unique idea** either: `NestGraph` in Mathematica, Maude's `search`,
and LoLA's reachability graph all cover the BFS-from-seed-under-rules
core in their own ecosystems. VisIter's specific contribution is the
combination of (a) free + scriptable + Graphviz-native + Unix-pipe
ergonomics, and (b) a rendering layer where cutoff boundaries
(structural bounds, render-time crops) are a first-class visual
primitive rather than silent truncation. That combination isn't
packaged anywhere else I found. Small niche, real.
