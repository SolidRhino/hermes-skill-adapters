# Sync upstream skills
sync:
    uv run python scripts/sync_skills.py sync

# Check if generated files are up to date
check:
    uv run python scripts/sync_skills.py sync --check

# Run tests
test:
    uv run pytest

# Lint workflows (requires actionlint in PATH)
lint:
    actionlint -color

# Validate generated skills
validate:
    uv run python scripts/sync_skills.py validate

# Validate sources.yaml
validate-sources:
    uv run python scripts/sync_skills.py validate-sources

# Remove generated skills
clean:
    rm -rf skills/

# Run full CI pipeline locally
ci: lint validate-sources validate check test
