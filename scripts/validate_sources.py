#!/usr/bin/env python3
"""Validate the sources.yaml manifest for Hermes skill adapters."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Allow direct script invocation: ensure project root is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validate_skills import validate_relative_path

ROOT = Path(__file__).resolve().parents[1]
VALID_SKILL_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
VALID_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VALID_FRONTMATTER_MODES = {"auto", "github-models", "ai"}
ALLOWED_INCLUDE_FILES = {"SKILL.md", "README.md", "LICENSE", "LICENSE.md"}
ALLOWED_INCLUDE_DIRS = {"scripts/", "references/", "assets/", "templates/", "examples/", "docs/", "configs/"}


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def validate_include(rel: str) -> str:
    rel = validate_relative_path(_require_string(rel, "include item"))
    if rel.endswith("/"):
        if rel not in ALLOWED_INCLUDE_DIRS:
            raise ValueError(f"include directory is not allowed: {rel}")
    elif rel not in ALLOWED_INCLUDE_FILES:
        raise ValueError(f"include file is not allowed: {rel}")
    return rel


def validate_frontmatter_config(config: Any, skill_name: str) -> None:
    if config is None:
        return
    fm = _require_mapping(config, f"skills[{skill_name}].frontmatter")
    mode = fm.get("mode", "auto")
    if mode not in VALID_FRONTMATTER_MODES:
        raise ValueError(
            f"skills[{skill_name}].frontmatter.mode must be one of "
            f"{sorted(VALID_FRONTMATTER_MODES)}"
        )
    ai_cache = fm.get("ai_cache")
    if ai_cache is not None:
        rel = validate_relative_path(_require_string(ai_cache, f"skills[{skill_name}].frontmatter.ai_cache"))
        if not rel.startswith("overlays/") or not rel.endswith(".yaml"):
            raise ValueError(f"skills[{skill_name}].frontmatter.ai_cache must be overlays/*.yaml")
    overrides = fm.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError(f"skills[{skill_name}].frontmatter.overrides must be a mapping")


def validate_source_entry(entry: Any, index: int) -> dict[str, Any]:
    item = _require_mapping(entry, f"skills[{index}]")

    name = _require_string(item.get("name"), f"skills[{index}].name")
    if not VALID_SKILL_NAME.match(name):
        raise ValueError(f"skills[{index}].name must be lowercase kebab/underscore case: {name!r}")

    upstream = _require_mapping(item.get("upstream"), f"skills[{name}].upstream")
    repo = _require_string(upstream.get("repo"), f"skills[{name}].upstream.repo")
    if not VALID_REPO.match(repo):
        raise ValueError(f"skills[{name}].upstream.repo must be owner/repo: {repo!r}")
    _require_string(upstream.get("ref", "main"), f"skills[{name}].upstream.ref")
    validate_relative_path(_require_string(upstream.get("path", "."), f"skills[{name}].upstream.path"))

    target = validate_relative_path(_require_string(item.get("target"), f"skills[{name}].target"))
    expected_target = f"skills/{name}"
    if target != expected_target:
        raise ValueError(f"skills[{name}].target must be {expected_target!r}, got {target!r}")

    includes = item.get("include")
    if not isinstance(includes, list) or not includes:
        raise ValueError(f"skills[{name}].include must be a non-empty list")
    for rel in includes:
        validate_include(rel)

    append_notes = item.get("append_notes")
    if append_notes is not None:
        rel = validate_relative_path(_require_string(append_notes, f"skills[{name}].append_notes"))
        if not rel.startswith(f"overlays/{name}/") or not rel.endswith(".md"):
            raise ValueError(f"skills[{name}].append_notes must be overlays/{name}/*.md")

    validate_frontmatter_config(item.get("frontmatter"), name)
    return item


def validate_sources(config: Any) -> list[dict[str, Any]]:
    root = _require_mapping(config, "sources.yaml")
    skills = root.get("skills")
    if not isinstance(skills, list) or not skills:
        raise ValueError("sources.yaml must contain a non-empty skills list")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, entry in enumerate(skills):
        item = validate_source_entry(entry, index)
        name = item["name"]
        if name in seen:
            raise ValueError(f"duplicate skill name in sources.yaml: {name}")
        seen.add(name)
        validated.append(item)
    return validated


def validate_sources_file(path: Path) -> list[dict[str, Any]]:
    return validate_sources(load_yaml(path))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=str(ROOT / "sources.yaml"))
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.is_absolute():
        path = ROOT / path

    try:
        entries = validate_sources_file(path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"sources validation error: {exc}", file=sys.stderr)
        return 1

    print(f"validated {path.relative_to(ROOT)} ({len(entries)} skill source(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
