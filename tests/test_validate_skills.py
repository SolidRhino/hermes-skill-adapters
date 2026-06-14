from __future__ import annotations

from pathlib import Path

import pytest

import validate_skills as val


def write_skill(path: Path, frontmatter: str | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    fm = frontmatter or """---
name: demo-skill
description: Demo skill for validation tests.
metadata:
  hermes:
    tags:
      - demo
    upstream: https://github.com/owner/demo-skill
---

# Demo
"""
    (path / "SKILL.md").write_text(fm, encoding="utf-8")


def test_validate_relative_path_rejects_traversal() -> None:
    with pytest.raises(ValueError, match="Unsafe"):
        val.validate_relative_path("../secret")


def test_validate_skill_dir_accepts_standard_layout(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    (skill / "scripts").mkdir()
    (skill / "references").mkdir()

    fm = val.validate_skill_dir(skill)

    assert fm["name"] == "demo-skill"


def test_validate_skill_dir_rejects_unexpected_top_level_file(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    (skill / "random.txt").write_text("nope", encoding="utf-8")

    with pytest.raises(ValueError, match="Unexpected top-level file"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_unexpected_directory(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    (skill / "danger").mkdir()

    with pytest.raises(ValueError, match="Unexpected support directory"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_missing_upstream(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(
        skill,
        """---
name: demo-skill
description: Demo skill for validation tests.
metadata:
  hermes:
    tags:
      - demo
---

# Demo
""",
    )

    with pytest.raises(ValueError, match="upstream"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_hidden_file(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    (skill / ".gitkeep").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Hidden path"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_hidden_directory(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    (skill / ".hidden").mkdir()

    with pytest.raises(ValueError, match="Hidden path"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_symlink(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    (skill / "link.txt").symlink_to(skill / "SKILL.md")

    with pytest.raises(ValueError, match="Symlink"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_nested_hidden_file(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / ".env").write_text("SECRET=***", encoding="utf-8")

    with pytest.raises(ValueError, match="Hidden path"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_nested_symlink(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / "real.py").write_text("print('ok')", encoding="utf-8")
    (scripts / "link.py").symlink_to(scripts / "real.py")

    with pytest.raises(ValueError, match="Symlink"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_nested_oversized_file(tmp_path: Path, monkeypatch) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(skill)
    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / "big.txt").write_bytes(b"x" * 11)
    monkeypatch.setattr(val, "MAX_FILE_BYTES", 10)

    with pytest.raises(ValueError, match="oversized"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_empty_tags(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(
        skill,
        """---
name: demo-skill
description: Demo skill for validation tests.
metadata:
  hermes:
    tags: []
    upstream: https://github.com/owner/demo-skill
---

# Demo
""",
    )

    with pytest.raises(ValueError, match="tags"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_ftp_upstream(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(
        skill,
        """---
name: demo-skill
description: Demo skill for validation tests.
metadata:
  hermes:
    tags:
      - demo
    upstream: ftp://example.com/skill
---

# Demo
""",
    )

    with pytest.raises(ValueError, match="upstream"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_name_mismatch(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    write_skill(
        skill,
        """---
name: other-skill
description: Demo skill for validation tests.
metadata:
  hermes:
    tags:
      - demo
    upstream: https://github.com/owner/demo-skill
---

# Demo
""",
    )

    with pytest.raises(ValueError, match="does not match directory"):
        val.validate_skill_dir(skill)


def test_validate_skill_dir_rejects_missing_skill_md(tmp_path: Path) -> None:
    skill = tmp_path / "demo-skill"
    skill.mkdir()

    with pytest.raises(ValueError, match="Missing SKILL.md"):
        val.validate_skill_dir(skill)
