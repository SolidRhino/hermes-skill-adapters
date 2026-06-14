from __future__ import annotations

from pathlib import Path

import generate_frontmatter as gf


def test_sanitize_ai_metadata_rejects_unknown_and_normalizes_values() -> None:
    raw = {
        "name": "evil-name",
        "homepage": "https://evil.example",
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
        "description: Create literate documentation from source code.\n"
        "tags:\n"
        "  - docs\n"
        "required_commands: []\n",
        encoding="utf-8",
    )
    entry = {
        "name": "demo-skill",
        "upstream": {"repo": "owner/demo-skill", "ref": "main", "path": "."},
        "target": "skills/demo-skill",
        "include": ["SKILL.md", "scripts/"],
    }

    fm = gf.generate_frontmatter(entry, src_root)

    assert fm["description"] == "Create literate documentation from source code."
    assert fm["metadata"]["hermes"]["tags"] == ["docs"]
    assert fm["metadata"]["hermes"]["required_commands"] == [
        "bun",
        "pandoc",
        "xelatex",
        "mermaid-filter",
    ]


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
