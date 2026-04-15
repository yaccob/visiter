#!/usr/bin/env bash
# Full pipe composition: build a graph, render to DOT, hand to `dot` for
# layout + format conversion. Two output formats demonstrate that the
# downstream stage is just a Graphviz invocation.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out

# Reverse binary tree: from 1, doubling and double-plus-one until 64.
EXPR='start=[1], rules=[
    Rule(lambda x: True, Op(lambda x: 2*x, "×2"),
         bound=lambda x: 2*x <= 64),
    Rule(lambda x: True, Op(lambda x: 2*x+1, "×2+1"),
         bound=lambda x: 2*x+1 <= 64),
], default=None'

visiter iterate "$EXPR" \
  | visiter to-dot 'show_binary=True' \
  | tee out/binary_tree.dot \
  | dot -Tsvg -o out/binary_tree.svg
echo "wrote out/binary_tree.svg"

# Same data, PDF instead of SVG.
dot -Tpdf out/binary_tree.dot -o out/binary_tree.pdf
echo "wrote out/binary_tree.pdf"
