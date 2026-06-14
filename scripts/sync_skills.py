#!/usr/bin/env python3
"""Sync upstream agent skills into Hermes-compatible skill directories.

Safety model:
- Upstream repository content is untrusted input.
- This script copies files only; it never executes upstream scripts.
- Generated output is deterministic.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from generate_frontmatter import DEFAULT_GITHUB_MODEL, dump_frontmatter, generate_frontmatter, load_yaml
from validate_sources import validate_sources
from validate_skills import validate_relative_path, validate_skill_dir

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources.yaml"
FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1).lstrip()


def copy_include(src_root: Path, dest_root: Path, rel: str) -> None:
    rel = validate_relative_path(rel)
    src = src_root / rel
    dest = dest_root / rel.rstrip("/")
    if not src.exists():
        print(f"warning: include not found: {rel}", file=sys.stderr)
        return
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git", "node_modules", "dist"))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def write_skill(
    entry: dict[str, Any],
    tmpdir: Path,
    *,
    use_github_models: bool = False,
    refresh_ai_cache: bool = False,
    model: str = DEFAULT_GITHUB_MODEL,
) -> None:
    name = entry["name"]
    repo = entry["upstream"]["repo"]
    ref = entry["upstream"].get("ref", "main")
    upstream_path = validate_relative_path(entry["upstream"].get("path", "."))
    target = ROOT / validate_relative_path(entry["target"])
    clone_dir = tmpdir / name

    run(["git", "clone", "--depth", "1", "--branch", ref, f"https://github.com/{repo}.git", str(clone_dir)])
    src_root = (clone_dir / upstream_path).resolve()
    if not src_root.is_relative_to(clone_dir.resolve()):
        raise ValueError(f"Unsafe upstream path for {name}: {upstream_path}")

    staging = tmpdir / f"staged-{name}"
    staging.mkdir(parents=True, exist_ok=True)
    for rel in entry.get("include") or ["SKILL.md"]:
        copy_include(src_root, staging, rel)

    fm = generate_frontmatter(
        entry,
        src_root,
        use_github_models=use_github_models,
        refresh_ai_cache=refresh_ai_cache,
        model=model,
    )
    validate_skill_dir(staging, fm)

    skill_md = staging / "SKILL.md"
    body = strip_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    append_notes = entry.get("append_notes")
    if append_notes:
        notes_path = ROOT / validate_relative_path(append_notes)
        if notes_path.exists():
            notes = notes_path.read_text(encoding="utf-8")
            if notes.strip() and notes.strip() not in body:
                body = body.rstrip() + "\n\n" + notes.strip() + "\n"

    skill_md.write_text("---\n" + dump_frontmatter(fm) + "---\n\n" + body, encoding="utf-8")
    validate_skill_dir(staging, fm)

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging), str(target))
    print(f"synced {name} -> {target.relative_to(ROOT)}")


def snapshot_generated() -> dict[str, str]:
    skills_dir = ROOT / "skills"
    if not skills_dir.exists():
        return {}
    out: dict[str, str] = {}
    for path in sorted(skills_dir.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8", errors="replace")
    return out


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> str:
    lines: list[str] = []
    keys = sorted(set(before) | set(after))
    for key in keys:
        if before.get(key) == after.get(key):
            continue
        old = before.get(key, "").splitlines(keepends=True)
        new = after.get(key, "").splitlines(keepends=True)
        lines.extend(difflib.unified_diff(old, new, fromfile=f"before/{key}", tofile=f"after/{key}"))
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated files change")
    parser.add_argument(
        "--use-github-models",
        action="store_true",
        help="use GitHub Models for missing AI metadata caches",
    )
    parser.add_argument(
        "--refresh-ai-cache",
        action="store_true",
        help="call GitHub Models even when a generated metadata cache already exists",
    )
    parser.add_argument(
        "--github-model",
        default=os.environ.get("GITHUB_MODEL", DEFAULT_GITHUB_MODEL),
        help=f"GitHub Models model name (default: {DEFAULT_GITHUB_MODEL})",
    )
    args = parser.parse_args()

    entries = validate_sources(load_yaml(SOURCES))

    before = snapshot_generated() if args.check else {}
    with tempfile.TemporaryDirectory(prefix="hermes-skill-adapters-") as td:
        tmpdir = Path(td)
        for entry in entries:
            write_skill(
                entry,
                tmpdir,
                use_github_models=args.use_github_models,
                refresh_ai_cache=args.refresh_ai_cache,
                model=args.github_model,
            )

    if args.check:
        after = snapshot_generated()
        diff = diff_snapshots(before, after)
        if diff:
            print(diff)
            print("generated skills are out of date", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
