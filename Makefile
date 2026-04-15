VENV := .venv
VENV_BIN := $(VENV)/bin
VENV_STAMP := $(VENV)/.installed

.PHONY: setup test demo build publish test-publish clean help

help:
	@echo "Targets:"
	@echo "  setup         create venv and install package + dev deps"
	@echo "  test          run pytest"
	@echo "  demo          run all demos/*.sh (writes to demos/out/)"
	@echo "  build         build sdist + wheel into dist/"
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
	@for s in demos/*.sh; do \
	    echo "== $$s =="; \
	    PATH="$(CURDIR)/$(VENV_BIN):$$PATH" bash "$$s" || exit 1; \
	done
	@echo "all demos succeeded — see demos/out/"

build: setup clean
	$(VENV_BIN)/python -m build

test-publish: build
	$(VENV_BIN)/python -m twine upload --repository testpypi dist/*

publish: build
	$(VENV_BIN)/python -m twine upload dist/*

clean:
	rm -rf dist/ build/ src/visiter.egg-info src/*.egg-info
