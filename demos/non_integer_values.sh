#!/usr/bin/env bash
# Iteration on strings, not numbers. Rule: if the word ends in a vowel,
# drop the last character. Default: none — words ending in a consonant
# are leaves. Demonstrates that `iterate`'s value type can be any
# hashable, str()-able Python object.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

EXPR='start=["banana", "garage", "queue", "iterator"],
rules=[Rule(lambda s: len(s) > 0 and s[-1] in set("aeiou"),
            Op(lambda s: s[:-1], label="drop-vowel"))],
default=None'

visiter build "$EXPR" \
  | visiter to-dot '' \
  | dot -Tsvg -o "$OUT/words.svg"
echo "wrote $OUT/words.svg (string-valued iteration)"
