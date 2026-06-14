#!/usr/bin/env python3
"""Sync upstream agent skills into Hermes-compatible skill directories.

Safety model:
- Upstream repository content is untrusted input.
- This script copies files only; it never executes upstream scripts.
- Generated output is deterministic.
"""

from __future__ import annotations

import argparse
import copy
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

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources.yaml"
VALID_SKILL_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
STANDARD_SUPPORT_DIRS = {"references", "scripts", "templates", "assets"}
KEYWORD_TAGS = {
    "literate": "literate-programming",
    "pandoc": "pandoc",
    "mermaid": "mermaid",
    "markdown": "markdown",
    "tangle": "tangle",
    "weave": "weave",
    "pdf": "pdf",
    "typescript": "typescript",
    "python": "python",
    "documentation": "documentation",
    "reverse-sync": "reverse-sync",
    "hook": "hooks",
}
COMMANDS = ["bun", "pandoc", "xelatex", "mermaid-filter", "node", "npm", "python", "uv"]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dump_frontmatter(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip() + "\n"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def slug_from_repo(repo: str) -> str:
    return repo.split("/", 1)[-1].removesuffix("-skill").replace("_", "-")


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1).lstrip()


def first_meaningful_sentence(text: str) -> str:
    clean = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    clean = re.sub(r"[#>*_`\[\]()]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    for sentence in re.split(r"(?<=[.!?])\s+", clean):
        sentence = sentence.strip(" -")
        if 40 <= len(sentence) <= 220:
            return sentence
    return "Hermes-compatible packaging for an upstream agent skill."


def collect_context(src_root: Path) -> str:
    chunks: list[str] = []
    for rel in ["README.md", "SKILL.md"]:
        path = src_root / rel
        if path.exists() and path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace")[:6000])
    return "\n\n".join(chunks)


def infer_tags(context: str, include: list[str]) -> list[str]:
    haystack = (context + "\n" + "\n".join(include)).lower()
    tags: list[str] = []
    for needle, tag in KEYWORD_TAGS.items():
        if needle in haystack and tag not in tags:
            tags.append(tag)
    if "documentation" not in tags:
        tags.append("documentation")
    return tags[:12]


def infer_required_commands(context: str) -> list[str]:
    found: list[str] = []
    lowered = context.lower()
    for command in COMMANDS:
        if re.search(rf"\b{re.escape(command.lower())}\b", lowered):
            found.append(command)
    return found


def generate_frontmatter(entry: dict[str, Any], src_root: Path) -> dict[str, Any]:
    name = entry.get("name") or slug_from_repo(entry["upstream"]["repo"])
    repo = entry["upstream"]["repo"]
    homepage = f"https://github.com/{repo}"
    context = collect_context(src_root)
    include = entry.get("include") or []

    fm: dict[str, Any] = {
        "name": name,
        "description": first_meaningful_sentence(context),
        "version": "0.1.0",
        "author": repo.split("/", 1)[0],
        "license": "unknown",
        "platforms": ["linux", "macos", "windows"],
        "metadata": {
            "hermes": {
                "tags": infer_tags(context, include),
                "category": "software-development",
                "homepage": homepage,
                "upstream": homepage,
                "source_repo": repo,
            }
        },
    }

    required = infer_required_commands(context)
    if required:
        fm["metadata"]["hermes"]["required_commands"] = required

    overrides = ((entry.get("frontmatter") or {}).get("overrides") or {})
    return deep_merge(fm, overrides)


def validate_relative_path(rel: str) -> str:
    rel = rel.strip()
    if not rel or rel.startswith("/"):
        raise ValueError(f"Unsafe include path: {rel!r}")
    parts = Path(rel).parts
    if any(part in {"..", ""} for part in parts):
        raise ValueError(f"Unsafe include path: {rel!r}")
    return rel


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


def validate_skill_dir(skill_dir: Path, fm: dict[str, Any]) -> None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise ValueError(f"Missing SKILL.md in {skill_dir}")
    name = fm.get("name")
    if not isinstance(name, str) or not VALID_SKILL_NAME.match(name):
        raise ValueError(f"Invalid skill name: {name!r}")
    description = fm.get("description")
    if not isinstance(description, str) or len(description.strip()) < 10:
        raise ValueError(f"Missing/short description for {name}")
    hermes = ((fm.get("metadata") or {}).get("hermes") or {})
    tags = hermes.get("tags")
    if not isinstance(tags, list) or not tags:
        raise ValueError(f"Missing metadata.hermes.tags for {name}")
    for child in skill_dir.iterdir():
        if child.is_dir() and child.name.startswith("."):
            raise ValueError(f"Hidden directory not allowed in generated skill: {child}")


def write_skill(entry: dict[str, Any], tmpdir: Path) -> None:
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

    fm = generate_frontmatter(entry, src_root)
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
    args = parser.parse_args()

    config = load_yaml(SOURCES)
    entries = config.get("skills") or []
    if not entries:
        raise SystemExit("No skills configured in sources.yaml")

    before = snapshot_generated() if args.check else {}
    with tempfile.TemporaryDirectory(prefix="hermes-skill-adapters-") as td:
        tmpdir = Path(td)
        for entry in entries:
            write_skill(entry, tmpdir)

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
