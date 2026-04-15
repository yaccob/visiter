#!/usr/bin/env bash
# Iteration on strings, not numbers. Rule: if the word ends in a vowel,
# drop the last character. Default: none — words ending in a consonant
# are leaves. Demonstrates that `iterate`'s value type can be any
# hashable, str()-able Python object.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out

EXPR='start=["banana", "garage", "queue", "iterator"],
rules=[Rule(lambda s: len(s) > 0 and s[-1] in set("aeiou"),
            Op(lambda s: s[:-1], "drop-vowel"))],
default=None'

visiter iterate "$EXPR" \
  | visiter to-dot '' \
  | dot -Tsvg -o out/words.svg
echo "wrote out/words.svg (string-valued iteration)"
