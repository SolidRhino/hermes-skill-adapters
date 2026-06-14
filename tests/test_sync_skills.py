from __future__ import annotations

from pathlib import Path

import pytest

import sync_skills as sync


def test_copy_include_rejects_symlink(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    (src / "real.txt").write_text("secret", encoding="utf-8")
    (src / "link.txt").symlink_to(src / "real.txt")

    with pytest.raises(ValueError, match="symlink"):
        sync.copy_include(src, dest, "link.txt")


def test_copy_include_rejects_nested_symlink(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "real.ts").write_text("console.log('ok')", encoding="utf-8")
    (src / "scripts" / "link.ts").symlink_to(src / "scripts" / "real.ts")

    with pytest.raises(ValueError, match="symlink"):
        sync.copy_include(src, dest, "scripts/")


def test_copy_include_rejects_oversized_file(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    (src / "SKILL.md").write_bytes(b"x" * 11)
    monkeypatch.setattr(sync, "MAX_FILE_BYTES", 10)

    with pytest.raises(ValueError, match="oversized"):
        sync.copy_include(src, dest, "SKILL.md")


def test_main_supports_legacy_sync_flags(monkeypatch) -> None:
    called = {}

    def fake_run_sync(args):
        called["check"] = args.check
        return 0

    monkeypatch.setattr(sync, "run_sync", fake_run_sync)

    assert sync.main(["--check"]) == 0
    assert called == {"check": True}


def test_main_supports_sync_subcommand(monkeypatch) -> None:
    called = {}

    def fake_run_sync(args):
        called["check"] = args.check
        return 0

    monkeypatch.setattr(sync, "run_sync", fake_run_sync)

    assert sync.main(["sync", "--check"]) == 0
    assert called == {"check": True}
