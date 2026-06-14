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
IGNORED_DIRS = {".git", "node_modules", "dist"}
MAX_FILE_BYTES = 2 * 1024 * 1024
SUBCOMMANDS = {"sync", "validate", "validate-sources", "generate-frontmatter"}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1).lstrip()


def git_commit(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def ensure_under_root(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Unsafe path escaped root: {path}")


def assert_safe_source_path(path: Path, src_root: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing to copy symlink from upstream: {path.relative_to(src_root)}")
    ensure_under_root(path, src_root)
    if path.is_file() and path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(
            f"Refusing to copy oversized upstream file: {path.relative_to(src_root)} "
            f"({path.stat().st_size} bytes)"
        )


def safe_copy_file(src: Path, dest: Path, src_root: Path) -> None:
    assert_safe_source_path(src, src_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest, follow_symlinks=False)


def safe_copy_dir(src: Path, dest: Path, src_root: Path) -> None:
    assert_safe_source_path(src, src_root)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for child in sorted(src.iterdir()):
        if child.name in IGNORED_DIRS:
            continue
        assert_safe_source_path(child, src_root)
        child_dest = dest / child.name
        if child.is_dir():
            safe_copy_dir(child, child_dest, src_root)
        elif child.is_file():
            safe_copy_file(child, child_dest, src_root)
        else:
            raise ValueError(f"Refusing to copy unsupported upstream path type: {child}")


def copy_include(src_root: Path, dest_root: Path, rel: str) -> None:
    rel = validate_relative_path(rel)
    src = src_root / rel
    dest = dest_root / rel.rstrip("/")
    if not src.exists():
        print(f"warning: include not found: {rel}", file=sys.stderr)
        return
    assert_safe_source_path(src, src_root)
    if src.is_dir():
        safe_copy_dir(src, dest, src_root)
    elif src.is_file():
        safe_copy_file(src, dest, src_root)
    else:
        raise ValueError(f"Refusing to copy unsupported upstream path type: {rel}")


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
    upstream_commit = git_commit(clone_dir)

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
        upstream_commit=upstream_commit,
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


def add_sync_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--check", action="store_true", help="fail if generated files change")
    parser.add_argument(
        "--use-github-models",
        action="store_true",
        help="use GitHub Models for missing/stale AI metadata caches",
    )
    parser.add_argument(
        "--refresh-ai-cache",
        action="store_true",
        help="call GitHub Models even when a generated metadata cache is fresh",
    )
    parser.add_argument(
        "--github-model",
        default=os.environ.get("GITHUB_MODEL", DEFAULT_GITHUB_MODEL),
        help=f"GitHub Models model name (default: {DEFAULT_GITHUB_MODEL})",
    )


def run_sync(args: argparse.Namespace) -> int:
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


def run_validate(_: argparse.Namespace) -> int:
    from validate_skills import main as validate_main

    sys.argv = ["validate_skills.py"]
    return validate_main()


def run_validate_sources(_: argparse.Namespace) -> int:
    from validate_sources import main as validate_sources_main

    sys.argv = ["validate_sources.py"]
    return validate_sources_main()


def run_generate_frontmatter(args: argparse.Namespace) -> int:
    from generate_frontmatter import main as generate_main

    sys.argv = ["generate_frontmatter.py", args.source_root, "--entry", args.entry]
    if args.use_github_models:
        sys.argv.append("--use-github-models")
    if args.refresh_ai_cache:
        sys.argv.append("--refresh-ai-cache")
    sys.argv.extend(["--github-model", args.github_model])
    return generate_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync and validate Hermes-compatible skill adapters")
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("sync", help="sync upstream skills")
    add_sync_args(sync_parser)
    sync_parser.set_defaults(func=run_sync)

    validate_parser = subparsers.add_parser("validate", help="validate generated skills")
    validate_parser.set_defaults(func=run_validate)

    validate_sources_parser = subparsers.add_parser("validate-sources", help="validate sources.yaml")
    validate_sources_parser.set_defaults(func=run_validate_sources)

    generate_parser = subparsers.add_parser("generate-frontmatter", help="generate frontmatter for one source root")
    generate_parser.add_argument("source_root")
    generate_parser.add_argument("--entry", required=True)
    generate_parser.add_argument("--use-github-models", action="store_true")
    generate_parser.add_argument("--refresh-ai-cache", action="store_true")
    generate_parser.add_argument("--github-model", default=os.environ.get("GITHUB_MODEL", DEFAULT_GITHUB_MODEL))
    generate_parser.set_defaults(func=run_generate_frontmatter)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in SUBCOMMANDS:
        legacy_parser = argparse.ArgumentParser()
        add_sync_args(legacy_parser)
        return run_sync(legacy_parser.parse_args(argv))

    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
