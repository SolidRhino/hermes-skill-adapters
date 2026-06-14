.PHONY: sync check test lint validate validate-sources clean

sync:  ## Sync upstream skills
	uv run python scripts/sync_skills.py sync

check:  ## Check if generated files are up to date
	uv run python scripts/sync_skills.py sync --check

test:  ## Run tests
	uv run pytest

lint:  ## Lint workflows
	actionlint -color

validate:  ## Validate generated skills
	uv run python scripts/sync_skills.py validate

validate-sources:  ## Validate sources.yaml
	uv run python scripts/sync_skills.py validate-sources

clean:  ## Remove generated skills
	rm -rf skills/

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
