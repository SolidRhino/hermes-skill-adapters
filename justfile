UV := env_var_or_default("UV", ".venv/bin/uv")
ACTIONLINT := env_var_or_default("ACTIONLINT", "actionlint")

# Sync upstream skills
sync:
    {{UV}} run python scripts/sync_skills.py sync

# Check if generated files are up to date
check:
    {{UV}} run python scripts/sync_skills.py sync --check

# Run tests
test:
    {{UV}} run pytest

# Lint workflows (requires actionlint in PATH or ACTIONLINT=/path/to/actionlint)
lint:
    {{ACTIONLINT}} -color

# Validate generated skills
validate:
    {{UV}} run python scripts/sync_skills.py validate

# Validate sources.yaml
validate-sources:
    {{UV}} run python scripts/sync_skills.py validate-sources

# Validate release-please JSON config
validate-release-config:
    {{UV}} run python -m json.tool release-please-config.json >/dev/null
    {{UV}} run python -m json.tool .release-please-manifest.json >/dev/null

# Remove generated skills
clean:
    rm -rf skills/

# Run full CI pipeline locally
ci: lint validate-release-config validate-sources validate check test
