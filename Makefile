# Tallyproof developer commands. CI runs these same targets, so a green
# `make check` locally means the same checks pass in CI.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := backend
VENV := $(BACKEND)/.venv
PY := $(VENV)/bin/python
PIP_TOOLS_VERSION := 7.6.2

# Prefer Homebrew's Python 3.12 on macOS: some pyenv builds ship without the
# BLAKE2 hash module, which breaks libraries later in confusing ways.
UNAME := $(shell uname)
ifeq ($(UNAME),Darwin)
  BREW_PY := $(shell brew --prefix python@3.12 2>/dev/null)/bin/python3.12
  PYTHON ?= $(if $(wildcard $(BREW_PY)),$(BREW_PY),python3.12)
  # Spark needs Java 17. It is installed keg-only, so expose it to project
  # commands only instead of changing the system Java.
  JAVA_HOME ?= $(shell brew --prefix openjdk@17 2>/dev/null)/libexec/openjdk.jdk/Contents/Home
  export JAVA_HOME
else
  PYTHON ?= python3.12
endif

# PyDeequ loads the Deequ build that matches this Spark line.
SPARK_VERSION ?= 4.1
export SPARK_VERSION

.PHONY: help doctor venv deps deps-sync require-venv lint format typecheck test check audit vectors web-install web-lint web-typecheck web-test web-build web-check data-fetch clean

help: ## List available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-12s %s\n", $$1, $$2}'

doctor: ## Show the toolchain this project will use
	@echo "make:       $$($(MAKE) --version | head -1)"
	@echo "python:     $(PYTHON) ($$($(PYTHON) --version 2>&1))"
	@echo "venv:       $$(test -x $(PY) && $(PY) --version || echo 'not created, run make venv')"
	@echo "JAVA_HOME:  $(JAVA_HOME)"
	@test -x "$(JAVA_HOME)/bin/java" && "$(JAVA_HOME)/bin/java" -version 2>&1 | head -1 || echo "java:       not found (only needed for the Spark pipeline)"
	@echo "docker:     $$(docker context show 2>/dev/null || echo 'not available')"

venv: ## Create backend/.venv and install the pinned dependencies
	@$(PYTHON) -c "import sys, hashlib; assert sys.version_info[:2] == (3, 12), sys.version; hashlib.blake2b(b'')" \
		|| { echo "Need a Python 3.12 build with BLAKE2 support. Try: make venv PYTHON=/path/to/python3.12"; exit 1; }
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet "pip-tools==$(PIP_TOOLS_VERSION)"
	$(MAKE) deps-sync

require-venv:
	@test -x $(PY) || { echo "No virtual environment found. Run: make venv"; exit 1; }

deps: require-venv ## Recompile pinned requirement files after editing a .in file
	cd $(BACKEND) && .venv/bin/pip-compile --quiet --generate-hashes --allow-unsafe --strip-extras --output-file requirements.txt requirements.in
	cd $(BACKEND) && .venv/bin/pip-compile --quiet --generate-hashes --allow-unsafe --strip-extras --output-file requirements-dev.txt requirements-dev.in

deps-sync: require-venv ## Make the virtual environment match the pinned files exactly
	cd $(BACKEND) && .venv/bin/pip-sync --quiet requirements.txt requirements-dev.txt

lint: require-venv ## Check style and formatting
	$(VENV)/bin/ruff check . && $(VENV)/bin/ruff format --check .

format: require-venv ## Apply formatting and safe lint fixes
	$(VENV)/bin/ruff format . && $(VENV)/bin/ruff check --fix .

typecheck: require-venv ## Run mypy in strict mode
	cd $(BACKEND) && .venv/bin/mypy
	$(VENV)/bin/mypy --strict scripts

test: require-venv ## Run the unit tests with coverage
	cd $(BACKEND) && .venv/bin/pytest --cov --cov-report=term --cov-report=xml:coverage.xml

audit: require-venv ## Scan pinned dependencies for known vulnerabilities
	cd $(BACKEND) && .venv/bin/pip-audit --strict --disable-pip -r requirements.txt -r requirements-dev.txt

vectors: require-venv ## Regenerate the shared cross-language test vectors
	cd $(BACKEND) && .venv/bin/python -m tests.vectors_builder

data-fetch: require-venv ## Download the configured fiscal years into data/bronze
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.acquire

check: lint typecheck test ## Everything CI checks on every pull request

WEB := frontend

web-install: ## Install the web app's locked dependencies
	cd $(WEB) && pnpm install --frozen-lockfile

web-lint: ## Lint and format-check the web app
	cd $(WEB) && pnpm run lint

web-typecheck: ## Type-check the web app
	cd $(WEB) && pnpm run typecheck

web-test: ## Run the web app's unit tests
	cd $(WEB) && pnpm run test

web-build: ## Build the static web app (needs the replay bundle and pinned key)
	cd $(WEB) && pnpm run build

web-check: web-lint web-typecheck web-test ## Everything CI checks on the web app

clean: ## Remove caches and build output (keeps the virtual environment)
	find $(BACKEND) -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	rm -f $(BACKEND)/coverage.xml $(BACKEND)/.coverage
