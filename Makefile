VENV := .venv
VENV_BIN := $(VENV)/bin
VENV_STAMP := $(VENV)/.installed
# Pin the interpreter so the venv is reproducible regardless of what `python3`
# resolves to on the host. Override with `make setup PYTHON=python3.13`.
PYTHON ?= python3.12

.PHONY: setup test demo dot-check docs build publish test-publish check-version clean help native

help:
	@echo "Targets:"
	@echo "  setup         create venv and install package + dev deps"
	@echo "  test          run pytest"
	@echo "  native        build the optional native engine into the venv"
	@echo "  demo          re-render demos whose .vit changed (force all: make -B demo)"
	@echo "  docs          regenerate all embedded SVGs in docs/"
	@echo "  build         build sdist + wheel into dist/"
	@echo "  check-version verify pyproject version isn't already on PyPI"
	@echo "                (REPOSITORY=pypi|testpypi, default pypi)"
	@echo "  publish       upload dist/ to PyPI (requires credentials)"
	@echo "  test-publish  upload dist/ to TestPyPI"
	@echo "  clean         remove build artefacts"

setup: $(VENV_STAMP)

$(VENV_STAMP): pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install -U pip
	$(VENV_BIN)/python -m pip install -e ".[dev,storage]"
	@touch $@

test: setup
	$(VENV_BIN)/pytest

# Optional native acceleration (Path A / ①). Requires a Rust toolchain.
# Builds the visiter_native extension into the venv; once present, build()
# uses it automatically (engine="auto") for every build, bounded or not.
# visiter works without this — pure Python is the always-available fallback.
native: setup
	@command -v cargo >/dev/null || { echo "native engine requires a Rust toolchain (cargo) on PATH"; exit 1; }
	$(VENV_BIN)/pip install -q "maturin>=1.0,<2.0"
	cd "$(CURDIR)/native" && VIRTUAL_ENV="$(CURDIR)/$(VENV)" "$(CURDIR)/$(VENV_BIN)/maturin" develop --release
	@echo "native engine installed — build() now uses it for all graphs"

# Each demo renders into its sibling out/ dir; make re-renders an output only
# when its .vit is newer. Force a full rebuild the make way: `make -B demo`.
# foreach just collects the target list; the work is plain pattern rules (one
# per topic dir for the 1-.vit -> 1-.svg-on-stdout demos, grouped pattern rules
# for the few that write several SVGs themselves). Assumes the venv exists (run
# `make setup` once); it is deliberately not a prerequisite so `make -B demo`
# re-renders outputs without rebuilding the venv.
VITER := $(VENV_BIN)/viter
DEMO_VITS := $(shell find demos -name '*.vit' | sort)
# .vit that don't map to one same-named .svg on stdout (text, or self-written
# multi-file output) — handled by the explicit rules below.
SPECIAL := demos/python/integration/inspection.vit \
           demos/python/rendering/ghost_stubs.vit \
           demos/python/rendering/color_stability.vit
DEMO_SVGS := $(foreach v,$(filter-out $(SPECIAL),$(DEMO_VITS)),$(dir $v)out/$(notdir $(v:.vit=.svg)))

demo: dot-check $(DEMO_SVGS) \
      demos/python/integration/out/inspection.txt \
      demos/python/rendering/out/ghost_stubs_bound.svg \
      demos/python/rendering/out/ghost_stubs_max_depth.svg \
      demos/python/rendering/out/color_stability_baseline.svg \
      demos/python/rendering/out/color_stability_appended.svg \
      demos/python/rendering/out/color_stability_pinned.svg

dot-check:
	@command -v dot >/dev/null || { echo "demos require 'dot' (Graphviz) on PATH"; exit 1; }

# 1 .vit -> 1 same-named .svg on stdout — one pattern rule per topic dir
demos/python/basics/out/%.svg:       demos/python/basics/%.vit       ; $(VITER) $< $(VITER_ARGS) > $@
demos/python/integration/out/%.svg:  demos/python/integration/%.vit  ; $(VITER) $< $(VITER_ARGS) > $@
demos/python/applications/out/%.svg: demos/python/applications/%.vit ; $(VITER) $< $(VITER_ARGS) > $@
demos/python/rendering/out/%.svg:    demos/python/rendering/%.vit    ; $(VITER) $< $(VITER_ARGS) > $@
demos/rust/basics/out/%.svg:         demos/rust/basics/%.vit         ; $(VITER) $< $(VITER_ARGS) > $@
demos/rust/applications/out/%.svg:   demos/rust/applications/%.vit   ; $(VITER) $< $(VITER_ARGS) > $@

# tic-tac-toe is the one demo that takes extra CLI args (after the .vit, so the
# script sees them on sys.argv)
demos/python/applications/out/tictactoe.svg: VITER_ARGS := --depth 3

# inspection prints a text report, not an SVG
demos/python/integration/out/inspection.txt: demos/python/integration/inspection.vit
	$(VITER) $< > $@

# self-writing demos: one viter run makes the whole set. A pattern rule with
# several target patterns is grouped — the recipe runs once for all of them.
demos/python/rendering/out/%_bound.svg demos/python/rendering/out/%_max_depth.svg: demos/python/rendering/%.vit
	$(VITER) $<
demos/python/rendering/out/%_baseline.svg demos/python/rendering/out/%_appended.svg demos/python/rendering/out/%_pinned.svg: demos/python/rendering/%.vit
	$(VITER) $<

docs: setup
	@command -v dot >/dev/null || { echo "docs require 'dot' (Graphviz) on PATH"; exit 1; }
	PATH="$(CURDIR)/$(VENV_BIN):$$PATH" bash docs/generate_images.sh
	@echo "docs SVGs regenerated — see docs/images/"

build: setup clean
	$(VENV_BIN)/python -m build

check-version: setup
	@$(VENV_BIN)/python scripts/check_pypi_version.py --repository $(or $(REPOSITORY),pypi)

test-publish: build
	@$(MAKE) check-version REPOSITORY=testpypi
	$(VENV_BIN)/python -m twine upload --repository testpypi dist/*

publish: build
	@$(MAKE) check-version REPOSITORY=pypi
	$(VENV_BIN)/python -m twine upload dist/*

clean:
	rm -rf dist/ build/ src/visiter.egg-info src/*.egg-info
