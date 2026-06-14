# Hermes Skill Adapters

This repository packages third-party agent skills into Hermes-compatible skill directories.

It is a packaging/adaptation layer, not an ownership claim over upstream skills. Upstream content is copied as intactly as practical; Hermes-specific metadata and notes are generated from `sources.yaml` and `overlays/`.

## Layout

```text
sources.yaml                  # upstream skill manifest
overlays/<skill>/             # manual Hermes metadata and notes
skills/<skill>/               # generated Hermes-compatible skill output
scripts/sync_skills.py        # sync + validate script
.github/workflows/sync.yml    # scheduled/manual upstream sync PR workflow
```

## Usage

Sync all configured skills:

```bash
python3 scripts/sync_skills.py
```

Improve generated metadata with GitHub Models and cache the result under `overlays/<skill>/generated-metadata.yaml`:

```bash
GITHUB_TOKEN=*** python3 scripts/sync_skills.py --use-github-models
```

Refresh existing AI metadata caches deliberately:

```bash
GITHUB_TOKEN=*** python3 scripts/sync_skills.py --use-github-models --refresh-ai-cache
```

Check that generated files are current without writing changes:

```bash
python3 scripts/sync_skills.py --check
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
- The sync script copies files; it does not execute upstream scripts.
- GitHub Models output is sanitized and cached before being applied.
- Automated sync opens pull requests for review instead of directly merging upstream changes.
