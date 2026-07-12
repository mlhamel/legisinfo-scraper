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
	@echo "  reset     Show instructions for wiping and resetting the target repository"
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

reset:
	@if [ ! -d "$(REPO)/.git" ]; then echo "Error: $(REPO) is not a git repository."; exit 1; fi
	@echo "WARNING: This will completely wipe all history and files in the target data repository: $(REPO)"
	@echo "To proceed, run: make reset-confirm REPO=$(REPO)"

reset-confirm:
	@if [ ! -d "$(REPO)/.git" ]; then echo "Error: $(REPO) is not a git repository."; exit 1; fi
	git -C $(REPO) checkout --orphan clean_start
	# Remove only session folders from git tracking and working tree
	git -C $(REPO) rm -rf [0-9]*-[0-9]* 2>/dev/null || true
	rm -rf $(REPO)/[0-9]*-[0-9]*
	# Reset root README.md table of contents
	printf "# Canadian Parliamentary Bills Database\n\nThis repository contains a versioned history of Canadian legislative bills and text revisions.\n\n## Supported Sessions\n\n| Session | Link | Status | Last Updated |\n| --- | --- | --- | --- |\n" > $(REPO)/README.md
	# Stage all remaining root files (README, LICENSE, etc.) and .github
	git -C $(REPO) add .github * 2>/dev/null || true
	git -C $(REPO) commit -m "Initial commit"
	git -C $(REPO) branch -M main
	@echo "Target repository $(REPO) has been successfully reset. README (with cleared TOC), LICENSE, and .github have been preserved."

clean:
	rm -rf dist/
	rm -rf .pytest_cache/
	rm -rf src/*.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} +
