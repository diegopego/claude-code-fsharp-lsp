# Developer entry points for claude-code-fsharp-lsp, grouped by workflow phase.
# Run `make` (or `make help`) to see them.
#
# Conveniences, not build steps. `pytest` is `python3 -m pytest` (not on PATH as
# a bare command, per CLAUDE.md). Doc regeneration is Claude-driven (the
# maintain-docs skill), so it is NOT a make target — `make docs` prints how.
#
# install-local is a prerequisite of test/verify/docs so the on-disk installed
# plugin always mirrors this working tree. It is a safe no-op when the plugin is
# not installed, so these targets work on a fresh clone too.

PYTHON       ?= python3
LEVEL        ?= patch
SKILL        := .claude/skills/maintain-docs
DEMO         := demo/LibraryLending.slnx
VERSION_FILE := .claude-plugin/plugin.json

.DEFAULT_GOAL := help
.PHONY: help install-local test build-demo check verify docs \
        version release publish clean

help:  ## List targets, grouped by workflow phase
	@awk 'BEGIN{FS=":.*?## "} \
		/^##@/{printf "\n\033[1m%s\033[0m\n", substr($$0,5); next} \
		/^[a-zA-Z_-]+:.*?## /{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)

##@ Develop
install-local:  ## Sync this working tree into the installed plugin (safe no-op if none)
	$(PYTHON) $(SKILL)/refresh_plugin.py

##@ Test
test: install-local  ## Sync the plugin, then run the Python suite (also gates docs consistency)
	$(PYTHON) -m pytest

build-demo:  ## Build the F# demo project (the documentation instrument)
	dotnet build $(DEMO)

check:  ## Is the environment usable? (fsautocomplete on PATH, SDKs)
	$(PYTHON) tools/check_fsharp_lsp.py

verify: install-local check build-demo test  ## Sync + check + build-demo + test

##@ Document
docs: install-local  ## Sync the plugin, then how to regenerate README + landing page
	@echo "Plugin synced into the install. Restart the session so it loads, then"
	@echo "in Claude Code run:  /maintain-docs"
	@echo ""
	@echo "The skill captures real tool output against demo/ and rewrites README +"
	@echo "docs/index.html. 'make test' then verifies they stay consistent."

##@ Publish — bump the version so the marketplace re-pulls
version:  ## Show the current plugin version
	@$(PYTHON) -c "import json; print(json.load(open('$(VERSION_FILE)'))['version'])"

release: verify  ## Prepare a release: verify, bump version (LEVEL=patch|minor|major), commit
	@NEW=$$($(PYTHON) $(SKILL)/bump_version.py --level $(LEVEL) --file $(VERSION_FILE)); \
		git commit -m "chore: release $$NEW" -- $(VERSION_FILE); \
		echo ""; \
		echo "Prepared release $$NEW (committed $(VERSION_FILE) only; other changes untouched)."; \
		echo "Publish it with:  make publish"

publish:  ## Push master so Claude Code re-pulls the marketplace (publishes to everyone)
	@echo "About to push these commits to origin/master:"
	@git log --oneline origin/master..master || true
	@echo ""
	git push origin master

##@ Housekeeping
clean:  ## Remove caches and demo build output
	rm -rf .pytest_cache demo/*/bin demo/*/obj
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
