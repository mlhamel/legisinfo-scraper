# Parameters
REPO ?= data_repo
SESSION ?= active
LIMIT ?= 0

# Arguments assembly
ifeq ($(SESSION),active)
  SESSION_ARG =
else
  SESSION_ARG = --session $(SESSION)
endif

ifneq ($(LIMIT),0)
  LIMIT_ARG = --limit $(LIMIT)
else
  LIMIT_ARG =
endif

.PHONY: help install test build run status clean

help:
	@echo "Available Makefile targets:"
	@echo "  install   Install dependencies and package in editable mode"
	@echo "  test      Run the integration test suite"
	@echo "  build     Build the source distribution and wheel"
	@echo "  run       Run the scraper locally (usage: make run REPO=/path/to/repo [SESSION=all|45-1] [LIMIT=10])"
	@echo "  status    Show status of all scraped sessions (usage: make status REPO=/path/to/repo)"
	@echo "  clean     Remove temporary files and build artifacts"

install:
	uv sync --extra dev

test:
	uv run pytest

build:
	uv build

run:
	uv run python scraper.py --repo $(REPO) $(SESSION_ARG) $(LIMIT_ARG)

status:
	uv run python report_status.py --repo $(REPO)

clean:
	rm -rf dist/
	rm -rf .pytest_cache/
	rm -rf src/*.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} +
