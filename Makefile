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

# The container stack runs only on its own Colima profile, never Docker Desktop
# or whatever context happens to be active.
COLIMA_PROFILE := tallyproof
COMPOSE := docker --context colima-$(COLIMA_PROFILE) compose --env-file .env -f infra/compose.yaml

# PyDeequ loads the Deequ build that matches this Spark line.
SPARK_VERSION ?= 4.1
export SPARK_VERSION

.PHONY: help doctor venv deps deps-sync require-venv lint format typecheck test check audit vectors web-install web-lint web-typecheck web-test web-build web-check web-audit web-live data-fetch data-build data-quality require-no-containers data-gold keygen replay data-sample test-integration coverage coverage-report require-colima up down reset ps logs db-roles migrate ingest checkpointer verify-witness data-replay data-treasury demo demo-stop tamper schemas register-schemas verify-event console clean

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

lint: require-venv ## Check style, formatting, and that no model change lacks a migration
	$(VENV)/bin/ruff check . && $(VENV)/bin/ruff format --check .
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.test \
		.venv/bin/python -W ignore::RuntimeWarning manage.py makemigrations --check --dry-run

format: require-venv ## Apply formatting and safe lint fixes
	$(VENV)/bin/ruff format . && $(VENV)/bin/ruff check --fix .

typecheck: require-venv ## Run mypy in strict mode
	cd $(BACKEND) && .venv/bin/mypy
	$(VENV)/bin/mypy --strict scripts

# Which tests `make test` selects. CI narrows this per job (unit or Spark).
TEST_MARKERS ?= not integration

# Each suite records its own coverage data; `make coverage` combines them and
# enforces the threshold on what all the tests exercise together.
PYTEST_COV := --cov --cov-report= --cov-fail-under=0
COVERAGE_NAME ?= unit

test: require-venv ## Run the unit and Spark tests (no containers needed)
	cd $(BACKEND) && COVERAGE_FILE=.coverage.$(COVERAGE_NAME) .venv/bin/pytest -m "$(TEST_MARKERS)" $(PYTEST_COV)

# On macOS, Testcontainers talks to the Colima VM's Docker socket; inside the VM
# the socket lives at the standard path, which its cleanup container mounts.
# On Linux (CI) the default Docker socket is used as is.
ifeq ($(UNAME),Darwin)
  INTEGRATION_ENV := DOCKER_HOST=unix://$$HOME/.colima/$(COLIMA_PROFILE)/docker.sock \
	TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
  INTEGRATION_NEEDS := require-colima
endif

test-integration: require-venv $(INTEGRATION_NEEDS) ## Run integration tests against real Postgres and Redpanda containers
	cd $(BACKEND) && $(INTEGRATION_ENV) COVERAGE_FILE=.coverage.integration \
		.venv/bin/pytest -m integration -p no:cacheprovider $(PYTEST_COV)

coverage: test test-integration coverage-report ## Run every suite and enforce the coverage threshold

coverage-report: require-venv ## Combine recorded coverage and fail below the threshold
	cd $(BACKEND) && .venv/bin/coverage combine --keep .coverage.* && \
		.venv/bin/coverage report && .venv/bin/coverage xml -o coverage.xml

audit: require-venv ## Scan dependencies for known vulnerabilities and check production security settings
	cd $(BACKEND) && .venv/bin/pip-audit --strict --disable-pip -r requirements.txt -r requirements-dev.txt
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECURE_SSL_REDIRECT=true \
		DJANGO_HSTS_SECONDS=31536000 DJANGO_SECRET_KEY=$$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))") \
		.venv/bin/python -W ignore manage.py check --deploy --fail-level WARNING

vectors: require-venv ## Regenerate the shared cross-language test vectors
	cd $(BACKEND) && .venv/bin/python -m tests.vectors_builder

data-fetch: require-venv ## Download the configured fiscal years into data/bronze
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.acquire

require-no-containers:
	@if command -v colima >/dev/null 2>&1 && colima list 2>/dev/null | grep -q Running; then \
		echo "A Colima VM is running. Stop it first (colima stop tallyproof): Spark and the"; \
		echo "container stack never run together on an 8 GB machine."; exit 1; fi

data-build: require-venv require-no-containers ## Clean downloaded archives into silver Parquet with Spark
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.silver

data-quality: require-venv require-no-containers ## Run the Deequ data quality checks on silver
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.quality

data-gold: require-venv require-no-containers ## Conform silver into ledger events with the anomaly overlay
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.gold

data-sample: require-venv ## Refresh the committed real-data sample from gold
	$(PY) -c "import gzip, itertools; src = gzip.open('data/gold/events.jsonl.gz', 'rt'); out = gzip.GzipFile('testdata/sample/gold_events_sample.jsonl.gz', 'wb', mtime=0); [out.write(line.encode()) for line in itertools.islice(src, 2000)]; out.close()"

keygen: require-venv ## Create a signing key in secrets/ (KEY=dev or KEY=rel)
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.keygen $(or $(KEY),dev)

replay: require-venv ## Export a signed demo bundle from gold to data/replay
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.replay_bundle

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

web-live: ## Run the web app against the local live API, trusting the dev key from .env
	cd $(WEB) && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 \
		NEXT_PUBLIC_PINNED_VERIFIER_KEY="$$(grep '^CHECKPOINT_PUBLIC_KEY=' ../.env | cut -d= -f2-)" \
		pnpm dev

web-audit: ## Scan the web app's dependencies for known vulnerabilities
	cd $(WEB) && pnpm audit --prod=false

web-check: web-lint web-typecheck web-test web-audit ## Everything CI checks on the web app

# --- Container stack ----------------------------------------------------------

require-colima:
	@colima status $(COLIMA_PROFILE) >/dev/null 2>&1 || { \
		echo "The Colima VM is not running. Start it with:"; \
		echo "  colima start $(COLIMA_PROFILE) --cpu 2 --memory 3 --disk 25"; exit 1; }
	@test -f .env || { echo "No .env yet: cp .env.example .env, then fill in the passwords."; exit 1; }

up: require-colima ## Start Redpanda, Postgres, and Redis, create topics, wait until healthy
	$(COMPOSE) up -d --wait redpanda postgres redis
	$(COMPOSE) run --rm topics

down: require-colima ## Stop the stack and keep its data
	$(COMPOSE) --profile tools down

reset: require-colima ## Stop the stack and delete its volumes (asks first)
	@read -r -p "Delete all local ledger data, topics, and database volumes? [y/N] " answer; \
		[ "$$answer" = y ] || { echo "Cancelled."; exit 1; }
	$(COMPOSE) --profile tools down --volumes

ps: require-colima ## Show the stack's containers and health
	$(COMPOSE) --profile tools ps

logs: require-colima ## Follow the stack's logs (SERVICE=postgres to pick one)
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

migrate: require-venv ## Apply database migrations as the owner role
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.migrate .venv/bin/python manage.py migrate

ingest: require-venv require-colima ## Run the ingestion consumer (Ctrl+C finishes the batch and stops)
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.local .venv/bin/python manage.py ingest

checkpointer: require-venv require-colima ## Sign checkpoints as the log grows (Ctrl+C stops)
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.local .venv/bin/python manage.py checkpointer

verify-witness: require-venv require-colima ## Check exported checkpoints against the key and the current log
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.local .venv/bin/python manage.py verify_witness

data-replay: require-venv require-colima ## Stream gold events into Kafka (LIMIT=n RATE=per-second)
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.stream $(if $(LIMIT),--limit $(LIMIT)) \
		$(if $(RATE),--rate $(RATE)) $(if $(EVENTS_FILE),--events $(EVENTS_FILE))

demo: require-venv ## Start the whole live pipeline and verify an event from it (DEMO_EVENTS=n)
	./scripts/demo.sh

demo-stop: ## Stop the demo's processes and containers, keeping their data
	@for name in api ingest checkpointer project relay fanout stream web; do \
		pid_file=var/demo/$$name.pid; \
		if [ -f $$pid_file ]; then kill $$(cat $$pid_file) 2>/dev/null && echo "stopped $$name"; rm -f $$pid_file; fi; \
	done
	-$(MAKE) --no-print-directory down

tamper: require-venv ## Tamper demo: DEMO_TAMPER_ENABLED=true make tamper LEVEL=1 EVENT=evt_... (RESTORE=1 undoes it)
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.migrate .venv/bin/python manage.py tamper \
		$(if $(RESTORE),--restore,--level $(LEVEL) --event $(EVENT))

schemas: require-venv ## Regenerate backend/schemas/events.v1.json from the event models
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.test .venv/bin/python -c \
		"import django; django.setup(); from apps.ingestion.schemas import SCHEMA_FILE, schema_text; SCHEMA_FILE.write_text(schema_text())"

register-schemas: require-venv require-colima ## Register the event schema with BACKWARD compatibility
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.local .venv/bin/python manage.py register_schemas

verify-event: require-venv ## Verify an event from the running API against the pinned key (EVENT=evt_...)
	cd $(BACKEND) && DJANGO_SETTINGS_MODULE=config.settings.local .venv/bin/python manage.py verify_event $(if $(EVENT),--event $(EVENT))

data-treasury: require-venv require-colima ## Publish Treasury cash statements (SINCE=yyyy-mm-dd, FOLLOW=1 to keep checking)
	cd $(BACKEND) && .venv/bin/python -m tallyproof_pipeline.treasury $(if $(SINCE),--since $(SINCE)) $(if $(FOLLOW),--follow)

db-roles: require-colima ## Re-run the database role script, for example after changing a password
	$(COMPOSE) exec -T postgres bash /docker-entrypoint-initdb.d/10-roles.sh

console: require-colima ## Open the broker console at http://localhost:8080
	$(COMPOSE) --profile tools up -d --wait console

clean: ## Remove caches and build output (keeps the virtual environment)
	find $(BACKEND) -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	rm -f $(BACKEND)/coverage.xml $(BACKEND)/.coverage $(BACKEND)/.coverage.*
