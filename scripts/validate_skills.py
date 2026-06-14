#!/usr/bin/env python3
"""Validate Hermes-compatible generated skill directories."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALID_SKILL_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
STANDARD_SUPPORT_DIRS = {"references", "scripts", "templates", "assets"}
ALLOWED_TOP_LEVEL_FILES = {"SKILL.md"}
DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = DEFAULT_MAX_FILE_BYTES


def validate_relative_path(rel: str) -> str:
    rel = rel.strip()
    if not rel or rel.startswith("/"):
        raise ValueError(f"Unsafe relative path: {rel!r}")
    parts = Path(rel).parts
    if any(part in {"..", ""} for part in parts):
        raise ValueError(f"Unsafe relative path: {rel!r}")
    return rel


def load_skill_frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"Missing YAML frontmatter: {skill_md}")
    raw = yaml.safe_load(match.group(1)) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Frontmatter must be a mapping: {skill_md}")
    return raw


def validate_frontmatter(fm: dict[str, Any], skill_dir: Path) -> None:
    name = fm.get("name")
    if not isinstance(name, str) or not VALID_SKILL_NAME.match(name):
        raise ValueError(f"Invalid skill name in {skill_dir}: {name!r}")
    expected_name = skill_dir.name.removeprefix("staged-")
    if name != expected_name:
        raise ValueError(f"Skill name {name!r} does not match directory {skill_dir.name!r}")

    description = fm.get("description")
    if not isinstance(description, str) or len(description.strip()) < 10:
        raise ValueError(f"Missing/short description for {name}")

    metadata = fm.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"metadata must be a mapping for {name}")
    hermes = metadata.get("hermes") or {}
    if not isinstance(hermes, dict):
        raise ValueError(f"metadata.hermes must be a mapping for {name}")

    tags = hermes.get("tags")
    if not isinstance(tags, list) or not tags or not all(isinstance(t, str) for t in tags):
        raise ValueError(f"Missing/invalid metadata.hermes.tags for {name}")

    upstream = hermes.get("upstream")
    if not isinstance(upstream, str) or not upstream.startswith("https://github.com/"):
        raise ValueError(f"Missing/invalid metadata.hermes.upstream for {name}")


def configured_max_file_bytes() -> int:
    if MAX_FILE_BYTES != DEFAULT_MAX_FILE_BYTES:
        return MAX_FILE_BYTES
    sources = ROOT / "sources.yaml"
    if not sources.exists():
        return MAX_FILE_BYTES
    try:
        config = yaml.safe_load(sources.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return MAX_FILE_BYTES
    safety = config.get("safety") if isinstance(config, dict) else None
    if isinstance(safety, dict) and isinstance(safety.get("max_file_bytes"), int):
        return int(safety["max_file_bytes"])
    return MAX_FILE_BYTES


def validate_nested_path(path: Path, skill_dir: Path) -> None:
    rel = path.relative_to(skill_dir)
    if any(part.startswith(".") for part in rel.parts):
        raise ValueError(f"Hidden path not allowed in generated skill: {path}")
    if path.is_symlink():
        raise ValueError(f"Symlink not allowed in generated skill: {path}")
    max_file_bytes = configured_max_file_bytes()
    if path.is_file() and path.stat().st_size > max_file_bytes:
        raise ValueError(f"Refusing oversized file in generated skill: {path}")


def validate_skill_tree(skill_dir: Path) -> None:
    for child in skill_dir.iterdir():
        validate_nested_path(child, skill_dir)
        if child.is_dir() and child.name not in STANDARD_SUPPORT_DIRS:
            raise ValueError(f"Unexpected support directory in generated skill: {child}")
        if child.is_file() and child.name not in ALLOWED_TOP_LEVEL_FILES:
            raise ValueError(f"Unexpected top-level file in generated skill: {child}")

    for support_dir in STANDARD_SUPPORT_DIRS:
        root = skill_dir / support_dir
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            validate_nested_path(path, skill_dir)


def validate_skill_dir(skill_dir: Path, fm: dict[str, Any] | None = None) -> dict[str, Any]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise ValueError(f"Missing SKILL.md in {skill_dir}")

    frontmatter = fm or load_skill_frontmatter(skill_md)
    validate_frontmatter(frontmatter, skill_dir)
    validate_skill_tree(skill_dir)
    return frontmatter


def validate_all(skills_dir: Path) -> int:
    if not skills_dir.exists():
        raise ValueError(f"Skills directory does not exist: {skills_dir}")
    count = 0
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        validate_skill_dir(skill_dir)
        print(f"validated {skill_dir.relative_to(ROOT)}")
        count += 1
    if count == 0:
        raise ValueError(f"No skill directories found in {skills_dir}")
    return count


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default=str(ROOT / "skills"),
        help="skill directory or skills root to validate",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.is_absolute():
        path = ROOT / path

    try:
        if (path / "SKILL.md").exists():
            validate_skill_dir(path)
            print(f"validated {path.relative_to(ROOT)}")
        else:
            validate_all(path)
    except ValueError as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
