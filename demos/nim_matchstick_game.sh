#!/usr/bin/env bash
# Matchstick game (Nim): 10 matchsticks, take 1–3, last one wins.
# The .vit file IS the iteration definition — this wrapper just
# renders it and shows the SVG path.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

viter "$HERE/nim_matchstick_game.vit" -o "$OUT/nim_matchstick_game.svg"
echo "wrote $OUT/nim_matchstick_game.svg"
echo "  → highlighted nodes (0, 4, 8) are winning positions:"
echo "    leave your opponent there and you always win."
