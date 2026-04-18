#!/usr/bin/env python3
"""Generate all demo outputs into their respective out/ directories.

Usage: python scripts/generate_demo_outputs.py
"""

import os
import subprocess
import sys
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "demos"

# Demos that need extra CLI args.
EXTRA_ARGS = {
    "tictactoe.vit": ["--depth", "3"],
}

# Demos that produce text output, not SVG.
TEXT_OUTPUT = {
    "inspection.vit",
}

# Demos that write their own files (no stdout capture needed).
SELF_OUTPUT = {
    "ghost_stubs.vit",
    "color_stability.vit",
}

# Demos that write files AND produce stdout (capture both).
MIXED_OUTPUT = {
    "water_jugs.vit",
}


def main():
    viter = os.path.join(os.path.dirname(sys.executable), "viter")
    errors = []

    for vit in sorted(DEMOS.rglob("*.vit")):
        rel = vit.relative_to(DEMOS)
        out_dir = vit.parent / "out"
        out_dir.mkdir(exist_ok=True)
        extra = EXTRA_ARGS.get(vit.name, [])

        print(f"== {rel} ==", end=" ")

        result = subprocess.run(
            [viter, str(vit)] + extra,
            capture_output=True,
        )
        if result.returncode != 0:
            print("FAIL")
            print(result.stderr.decode(), file=sys.stderr)
            errors.append(str(rel))
            continue

        if vit.name in SELF_OUTPUT:
            print("ok (self-output)")
        elif vit.name in MIXED_OUTPUT:
            # Writes own files AND produces stdout.
            (out_dir / f"{vit.stem}.svg").write_bytes(result.stdout)
            print(f"ok → out/{vit.stem}.svg + self-output")
        elif vit.name in TEXT_OUTPUT:
            ext = ".txt"
            (out_dir / f"{vit.stem}{ext}").write_bytes(result.stdout)
            print(f"ok → out/{vit.stem}{ext}")
        else:
            ext = ".svg"
            (out_dir / f"{vit.stem}{ext}").write_bytes(result.stdout)
            print(f"ok → out/{vit.stem}{ext}")

    if errors:
        print(f"\n{len(errors)} demo(s) failed: {', '.join(errors)}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nall demos succeeded")


if __name__ == "__main__":
    main()
