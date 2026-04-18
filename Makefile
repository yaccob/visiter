VENV := .venv
VENV_BIN := $(VENV)/bin
VENV_STAMP := $(VENV)/.installed

.PHONY: setup test demo docs build publish test-publish check-version clean help

help:
	@echo "Targets:"
	@echo "  setup         create venv and install package + dev deps"
	@echo "  test          run pytest"
	@echo "  demo          run all demos/**/*.vit (writes to each out/)"
	@echo "  docs          regenerate all embedded SVGs in docs/"
	@echo "  build         build sdist + wheel into dist/"
	@echo "  check-version verify pyproject version isn't already on PyPI"
	@echo "                (REPOSITORY=pypi|testpypi, default pypi)"
	@echo "  publish       upload dist/ to PyPI (requires credentials)"
	@echo "  test-publish  upload dist/ to TestPyPI"
	@echo "  clean         remove build artefacts"

setup: $(VENV_STAMP)

$(VENV_STAMP): pyproject.toml
	python3 -m venv $(VENV)
	$(VENV_BIN)/pip install -U pip
	$(VENV_BIN)/pip install -e ".[dev]"
	@touch $@

test: setup
	$(VENV_BIN)/pytest

demo: setup
	@command -v dot >/dev/null || { echo "demos require 'dot' (Graphviz) on PATH"; exit 1; }
	$(VENV_BIN)/python scripts/generate_demo_outputs.py

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
