#!/usr/bin/env bash
# Op identity (auto-derived from func) is the color-assignment key:
# two renders of the same op body get the same color, so a graph stays
# visually coherent as you evolve it across runs.
#
# Three SVGs:
#   (a) baseline — two rules + default (x // 3, x + 2).
#   (b) rule appended at the end — adds a third rule (x // 5). The
#       pre-existing op colors stay where they were, x // 5 takes the
#       next palette slot.
#   (c) rule inserted in the middle, plus op_colors override — when
#       a rule lands BEFORE existing ones, the auto-assigned palette
#       indices shift; pin colors with op_colors (keyed on identity)
#       to keep the legend stable across edits.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

# (a) Baseline: x // 3 + x + 2 default.
visiter build '
range(1, 30),
[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
default=Op(lambda x: x + 2)' \
  | visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/stable_a_baseline.svg"
echo "wrote $OUT/stable_a_baseline.svg     (x // 3 = blue, x + 2 = orange)"

# (b) Append a third rule: x // 5 for multiples of 5.
visiter build '
range(1, 30),
[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3)),
 Rule(lambda x: x % 5 == 0, Op(lambda x: x // 5))],
default=Op(lambda x: x + 2)' \
  | visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/stable_b_appended.svg"
echo "wrote $OUT/stable_b_appended.svg     (x // 3 still blue, x // 5 next slot, x + 2 last)"

# (c) Insert x // 5 BEFORE x // 3, with op_colors pinning by identity
#     to keep the pre-existing colors in place. Without the pin,
#     x // 3 would shift palette slots; with it, the visual identity
#     holds.
visiter build '
range(1, 30),
[Rule(lambda x: x % 5 == 0, Op(lambda x: x // 5)),
 Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3))],
default=Op(lambda x: x + 2)' \
  | visiter to-dot 'op_colors={
      "x // 3": ("#ccddff", "#6688bb"),
      "x + 2": ("#ffddcc", "#ddbb99"),
      "x // 5": ("#cceecc", "#77aa77"),
    }, anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/stable_c_inserted_with_pin.svg"
echo "wrote $OUT/stable_c_inserted_with_pin.svg (colors pinned via op_colors)"
