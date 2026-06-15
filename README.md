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

## Releases

The first published release is [`v0.1.0`](https://github.com/SolidRhino/hermes-skill-adapters/releases/tag/v0.1.0).

Release Please maintains `CHANGELOG.md`, `.release-please-manifest.json`, `pyproject.toml`, and `uv.lock` from Conventional Commits. Do not hand-edit generated release entries.

## Remediation Status

Implemented mitigations for prism-full findings:

- **Dirty-tree guard** — `sync` aborts if the git working tree has uncommitted changes, preventing partial-sync corruption.
- **Copy depth limit** — `safe_copy_dir` caps recursion at 20 levels, with configurable override.
- **Release Please token** — workflow supports `RELEASE_PLEASE_TOKEN` secret so release-PRs trigger CI checks.
- **sources.yaml sorted** — enforced by `validate_sources.py` since inception.

Deferred (requires organizational or experimental change):

- **Async parallel AI** — blocked by `urllib` synchronous stack; would need `httpx`/`aiohttp` dependency and signal-safe cancellation. Tracked for future refactor.
- **uv.lock release fallback** — `extra-files` JSONPath is the current mitigation; full `uv lock` post-processing requires a release hook script or custom Release Please plugin.

## Hermes installation

Add this repository as a Hermes skill tap:

```bash
hermes skills tap add SolidRhino/hermes-skill-adapters
```

Search and inspect the packaged skill:

```bash
hermes skills search literate-programming --source github
hermes skills inspect SolidRhino/hermes-skill-adapters/skills/literate-programming
```

Install the packaged skill:

```bash
hermes skills install SolidRhino/hermes-skill-adapters/skills/literate-programming
```

Hermes may block community skills with security-scan findings. For `literate-programming`, the current scan flags installation commands and project-local hook setup instructions. Review the findings first; if you intentionally accept them, install with:

```bash
hermes skills install SolidRhino/hermes-skill-adapters/skills/literate-programming --force
```

A successful install includes the support files beside `SKILL.md`:

```text
assets/pandoc-header.yaml
references/analysis-workflow.md
references/chunk-syntax.md
references/pandoc-setup.md
scripts/hook-reverse-sync.ts
scripts/tangle.ts
scripts/untangle.ts
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

The `main` branch is protected:

- pull requests are required;
- the `test` status check must pass and be up to date;
- linear history is required;
- force pushes and branch deletion are disabled;
- conversations must be resolved before merge.

Dependabot is configured for:

- GitHub Actions updates in `.github/workflows/`
- Python dependency updates from `pyproject.toml`

It groups related dependency updates into weekly pull requests.

Release Please is configured to maintain releases from Conventional Commits:

- `.github/workflows/release-please.yml` opens or updates the release PR after changes land on `main`.
- `release-please-config.json` defines the Python release strategy.
- `.release-please-manifest.json` tracks the current version.
- `CHANGELOG.md` is maintained automatically by Release Please; do not edit release entries manually.
- `uv.lock` is included through Release Please `extra-files` so the locked project version stays in sync with `pyproject.toml`.
- Merging the Release Please PR creates the GitHub Release and tag.

Release Please currently uses the repository `GITHUB_TOKEN`. Pull requests created by that token may not automatically trigger PR CI. If a Release Please PR has no checks, either run CI manually via `workflow_dispatch` on the release branch, or configure a dedicated `RELEASE_PLEASE_TOKEN` secret from a bot/PAT so release PRs trigger normal checks.

Use Conventional Commit prefixes so releases are categorized correctly:

- `feat:` for minor releases.
- `fix:` for patch releases.
- `feat!:` or `fix!:` for breaking/major releases.
- `chore:`, `docs:`, `test:`, and `ci:` for maintenance entries.
