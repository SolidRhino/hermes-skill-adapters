# Hermes Skill Adapters

This repository packages third-party agent skills into Hermes-compatible skill directories.

It is a packaging/adaptation layer, not an ownership claim over upstream skills. Upstream content is copied as intactly as practical; Hermes-specific metadata and notes are generated from `sources.yaml` and `overlays/`.

## Layout

```text
sources.yaml                  # upstream skill manifest
overlays/<skill>/             # manual Hermes metadata and notes
skills/<skill>/               # generated Hermes-compatible skill output
scripts/sync_skills.py        # clone/copy/write generated skill output
scripts/generate_frontmatter.py # deterministic + GitHub Models metadata generation
scripts/validate_sources.py   # sources.yaml schema validation
scripts/validate_skills.py    # Hermes skill output validation
.github/workflows/sync.yml    # scheduled/manual upstream sync PR workflow
```

## Usage

Sync all configured skills:

```bash
uv run python scripts/sync_skills.py sync
```

The legacy form still works: `python3 scripts/sync_skills.py`.

Validate `sources.yaml`:

```bash
uv run python scripts/sync_skills.py validate-sources
```

Improve generated metadata with GitHub Models and cache the result under `overlays/<skill>/generated-metadata.yaml`:

```bash
GITHUB_TOKEN=*** uv run python scripts/sync_skills.py sync --use-github-models
```

Refresh existing AI metadata caches deliberately:

```bash
GITHUB_TOKEN=*** uv run python scripts/sync_skills.py sync --use-github-models --refresh-ai-cache
```

Check that generated files are current without writing changes:

```bash
uv run python scripts/sync_skills.py sync --check
```

Validate generated Hermes skill directories:

```bash
uv run python scripts/sync_skills.py validate
```

Run the full local CI recipe:

```bash
just ci
```

Run unit tests:

```bash
uv run pytest
```

## Hermes installation

After this repository is pushed to GitHub, add it as a Hermes skill tap:

```bash
hermes skills tap add <owner>/hermes-skill-adapters
hermes skills search literate --source github
hermes skills install <owner>/hermes-skill-adapters/skills/literate-programming
```

## Current packaged skills

- `literate-programming` from <https://github.com/tlehman/litprog-skill>

## Safety model

- Upstream repository content is treated as untrusted input.
- The sync script copies files; it does not execute upstream scripts, follow symlinks, or copy files larger than `safety.max_file_bytes`.
- `heuristics.context_files` are path-validated before reading; traversal, absolute paths, and symlinks are refused.
- Generated skill trees are validated recursively; nested hidden files, symlinks, and oversized files are refused.
- `sources.yaml` rejects unknown keys and skill entries must remain sorted by name for deterministic diffs.
- GitHub Models output must be strict JSON with only approved keys, then it is sanitized and cached with model/prompt/upstream provenance before being applied.
- Automated sync opens pull requests for review instead of directly merging upstream changes.

## Maintenance automation

Dependabot is configured for:

- GitHub Actions updates in `.github/workflows/`
- Python dependency updates from `pyproject.toml`

It groups related dependency updates into weekly pull requests.

Release Please is configured to maintain releases from Conventional Commits:

- `.github/workflows/release-please.yml` opens or updates the release PR after changes land on `main`.
- `release-please-config.json` defines the Python release strategy.
- `.release-please-manifest.json` tracks the current version.
- `CHANGELOG.md` is maintained automatically by Release Please; do not edit release entries manually.
- Merging the Release Please PR creates the GitHub Release and tag.

Use Conventional Commit prefixes so releases are categorized correctly:

- `feat:` for minor releases.
- `fix:` for patch releases.
- `feat!:` or `fix!:` for breaking/major releases.
- `chore:`, `docs:`, `test:`, and `ci:` for maintenance entries.
