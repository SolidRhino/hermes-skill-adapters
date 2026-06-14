from __future__ import annotations

from pathlib import Path

import pytest

import generate_frontmatter as gf


def test_sanitize_ai_metadata_rejects_unknown_keys() -> None:
    with pytest.raises(ValueError, match="unknown keys"):
        gf.sanitize_ai_metadata({"name": "evil-name", "description": "Useful skill metadata."})


def test_sanitize_ai_metadata_normalizes_values() -> None:
    raw = {
        "description": "  Generate useful docs from source code.  ",
        "tags": ["Code Analysis", "code-analysis", "PDF!", 123],
        "category": "Software Development",
        "required_commands": ["pandoc", "bad command", "pandoc", "xelatex"],
    }

    assert gf.sanitize_ai_metadata(raw) == {
        "description": "Generate useful docs from source code.",
        "tags": ["code-analysis", "pdf"],
        "category": "software-development",
        "required_commands": ["pandoc", "xelatex"],
    }


def test_strict_json_object_rejects_trailing_text_and_unknown_keys() -> None:
    with pytest.raises(ValueError):
        gf.strict_json_object('{"description":"Useful metadata."}\nextra')
    with pytest.raises(ValueError, match="unknown keys"):
        gf.strict_json_object('{"description":"Useful metadata.","name":"evil"}')


def test_generate_frontmatter_prefers_cache_but_preserves_heuristic_commands(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(gf, "ROOT", tmp_path)
    src_root = tmp_path / "upstream"
    src_root.mkdir()
    (src_root / "README.md").write_text(
        "# Skill\n\nUse bun, pandoc, xelatex, and mermaid-filter to weave PDFs.",
        encoding="utf-8",
    )
    cache = tmp_path / "overlays" / "demo-skill" / "generated-metadata.yaml"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        "metadata:\n"
        "  description: Create literate documentation from source code.\n"
        "  tags:\n"
        "    - docs\n"
        "  required_commands: []\n"
        "provenance:\n"
        "  model: openai/gpt-4o-mini\n"
        "  prompt_version: 2\n"
        "  upstream_repo: owner/demo-skill\n"
        "  upstream_ref: main\n"
        "  upstream_commit: abc123\n",
        encoding="utf-8",
    )
    entry = {
        "name": "demo-skill",
        "upstream": {"repo": "owner/demo-skill", "ref": "main", "path": "."},
        "target": "skills/demo-skill",
        "include": ["SKILL.md", "scripts/"],
    }

    fm = gf.generate_frontmatter(entry, src_root, upstream_commit="abc123")

    assert fm["description"] == "Create literate documentation from source code."
    assert fm["metadata"]["hermes"]["tags"] == [
        "pandoc",
        "mermaid",
        "weave",
        "pdf",
        "documentation",
        "docs",
    ]
    assert fm["metadata"]["hermes"]["required_commands"] == [
        "bun",
        "pandoc",
        "xelatex",
        "mermaid-filter",
    ]


def test_generate_frontmatter_refreshes_stale_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gf, "ROOT", tmp_path)
    src_root = tmp_path / "upstream"
    src_root.mkdir()
    (src_root / "SKILL.md").write_text("# Demo\n\nA useful skill for testing adapters.", encoding="utf-8")
    cache = tmp_path / "overlays" / "demo-skill" / "generated-metadata.yaml"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        "metadata:\n  description: Old cache description.\n  tags: [old]\n"
        "provenance:\n  model: old-model\n  prompt_version: 1\n",
        encoding="utf-8",
    )
    entry = {
        "name": "demo-skill",
        "upstream": {"repo": "owner/demo-skill", "ref": "main", "path": "."},
        "target": "skills/demo-skill",
        "include": ["SKILL.md"],
    }
    monkeypatch.setattr(
        gf,
        "generate_ai_metadata",
        lambda context, repo, model: {
            "description": "New generated description for adapters.",
            "tags": ["new-tag"],
            "category": "testing",
            "required_commands": [],
        },
    )

    fm = gf.generate_frontmatter(entry, src_root, use_github_models=True, upstream_commit="newsha")

    assert fm["description"] == "New generated description for adapters."
    assert gf.load_yaml(cache)["provenance"]["upstream_commit"] == "newsha"


def test_collect_context_rejects_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gf, "ROOT", tmp_path)
    (tmp_path / "sources.yaml").write_text(
        "skills:\n  - name: demo\nheuristics:\n  context_files:\n    - ../secret.txt\n",
        encoding="utf-8",
    )
    src_root = tmp_path / "upstream"
    src_root.mkdir()
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsafe"):
        gf.collect_context(src_root)


def test_collect_context_rejects_symlink(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gf, "ROOT", tmp_path)
    src_root = tmp_path / "upstream"
    src_root.mkdir()
    (src_root / "README-real.md").write_text("ok", encoding="utf-8")
    (src_root / "README.md").symlink_to(src_root / "README-real.md")

    with pytest.raises(ValueError, match="symlink"):
        gf.collect_context(src_root)


def test_generate_frontmatter_applies_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gf, "ROOT", tmp_path)
    src_root = tmp_path / "upstream"
    src_root.mkdir()
    (src_root / "SKILL.md").write_text("# Demo\n\nA useful skill for testing adapters.", encoding="utf-8")
    entry = {
        "name": "demo-skill",
        "upstream": {"repo": "owner/demo-skill", "ref": "main", "path": "."},
        "target": "skills/demo-skill",
        "include": ["SKILL.md"],
        "frontmatter": {
            "overrides": {
                "author": "Human",
                "metadata": {"hermes": {"category": "testing"}},
            }
        },
    }

    fm = gf.generate_frontmatter(entry, src_root)

    assert fm["author"] == "Human"
    assert fm["metadata"]["hermes"]["category"] == "testing"
    assert fm["metadata"]["hermes"]["upstream"] == "https://github.com/owner/demo-skill"
