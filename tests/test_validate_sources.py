from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import validate_sources as vs


def valid_config() -> dict:
    return {
        "skills": [
            {
                "name": "demo-skill",
                "upstream": {"repo": "owner/demo-skill", "ref": "main", "path": "."},
                "target": "skills/demo-skill",
                "include": ["SKILL.md", "scripts/", "references/"],
                "frontmatter": {"mode": "auto", "overrides": {"author": "Demo"}},
                "append_notes": "overlays/demo-skill/hermes-notes.md",
            }
        ]
    }


def test_validate_sources_accepts_valid_config() -> None:
    entries = vs.validate_sources(valid_config())
    assert entries[0]["name"] == "demo-skill"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda c: c["skills"][0].update({"name": "Demo Skill"}), "name must be"),
        (lambda c: c["skills"][0]["upstream"].update({"repo": "not-a-repo"}), "owner/repo"),
        (lambda c: c["skills"][0].update({"target": "../skills/demo-skill"}), "Unsafe"),
        (lambda c: c["skills"][0].update({"target": "skills/wrong"}), "target must be"),
        (lambda c: c["skills"][0].update({"include": ["../SKILL.md"]}), "Unsafe"),
        (lambda c: c["skills"][0].update({"include": ["secrets/"]}), "not allowed"),
        (
            lambda c: c["skills"][0].update({"append_notes": "notes.md"}),
            "append_notes must be",
        ),
        (
            lambda c: c["skills"][0].update({"frontmatter": {"mode": "surprise"}}),
            "frontmatter.mode",
        ),
    ],
)
def test_validate_sources_rejects_invalid_config(mutation, message: str) -> None:
    config = valid_config()
    mutation(config)
    with pytest.raises(ValueError, match=message):
        vs.validate_sources(config)


def test_validate_sources_rejects_duplicate_names() -> None:
    config = valid_config()
    config["skills"].append(dict(config["skills"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        vs.validate_sources(config)


def test_validate_sources_file(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")
    assert vs.validate_sources_file(path)[0]["name"] == "demo-skill"
