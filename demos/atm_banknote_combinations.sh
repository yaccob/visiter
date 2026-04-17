#!/usr/bin/env bash
# ATM withdrawal: dispense 80 EUR with 50/20/10 EUR notes.
# Every path from 80 to 0 is a valid banknote combination.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

viter "$HERE/atm_banknote_combinations.vit" -o "$OUT/atm_banknote_combinations.svg"
echo "wrote $OUT/atm_banknote_combinations.svg"
echo "  → every path from 80 to 0 is a valid payout combination."
