from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

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


def test_run_generate_frontmatter_passes_argv_without_program_name(monkeypatch) -> None:
    captured = {}

    def fake_generate_main(argv):
        captured["argv"] = argv
        return 0

    import scripts.generate_frontmatter as gf

    monkeypatch.setattr(gf, "main", fake_generate_main)
    parser = sync.build_parser()
    args = parser.parse_args(["generate-frontmatter", "/tmp/src", "--entry", "/tmp/entry.yaml"])

    assert args.func(args) == 0
    assert captured["argv"] == ["/tmp/src", "--entry", "/tmp/entry.yaml", "--github-model", sync.DEFAULT_GITHUB_MODEL]


def test_snapshot_generated_uses_hashes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    skills = tmp_path / "skills" / "demo-skill"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# Demo\n", encoding="utf-8")

    snap = sync.snapshot_generated()

    assert len(snap) == 1
    key = list(snap.keys())[0]
    assert key.endswith("SKILL.md")
    assert len(snap[key]) == 64


def test_diff_snapshots_only_diffs_changed_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    skills = tmp_path / "skills" / "demo-skill"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("old", encoding="utf-8")

    before = sync.snapshot_generated(include_content=True)

    (skills / "SKILL.md").write_text("new", encoding="utf-8")
    after = sync.snapshot_generated(include_content=True)

    diff = sync.diff_snapshots(before, after)
    assert "-old" in diff
    assert "+new" in diff


def test_diff_snapshots_skips_identical_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    skills = tmp_path / "skills" / "demo-skill"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("same", encoding="utf-8")

    before = sync.snapshot_generated()
    after = sync.snapshot_generated()

    diff = sync.diff_snapshots(before, after)
    assert diff == ""


def test_configured_safety_limit_controls_copy_size(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    sources = tmp_path / "sources.yaml"
    sources.write_text("skills: [{name: demo}]\nsafety:\n  max_file_bytes: 12\n", encoding="utf-8")
    monkeypatch.setattr(sync, "SOURCES", sources)
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    (src / "SKILL.md").write_bytes(b"x" * 13)

    with pytest.raises(ValueError, match="oversized"):
        sync.copy_include(src, dest, "SKILL.md")


def test_stage_files_copies_included_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "staging"
    src.mkdir()
    (src / "SKILL.md").write_text("# Test\n", encoding="utf-8")
    (src / "scripts").mkdir()
    (src / "scripts" / "run.sh").write_text("echo ok\n", encoding="utf-8")

    entry = {"include": ["SKILL.md", "scripts/"]}
    sync.stage_files(entry, src, dest)

    assert (dest / "SKILL.md").read_text() == "# Test\n"
    assert (dest / "scripts" / "run.sh").read_text() == "echo ok\n"


def test_assemble_skill_writes_frontmatter_and_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "SKILL.md").write_text("---\nname: old\n---\n\n# Body\n", encoding="utf-8")

    fm = {"name": "demo-skill", "description": "A demo."}
    entry = {"name": "demo-skill"}

    sync.assemble_skill(entry, staging, fm)

    result = (staging / "SKILL.md").read_text()
    assert "name: demo-skill" in result
    assert "# Body" in result


def test_run_retries_transient_failures(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise subprocess.CalledProcessError(1, args[0], stderr="temporary")
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    monkeypatch.setattr(sync.time, "sleep", lambda _delay: None)

    sync.run(["git", "clone", "repo"], retries=3, skill_name="demo")

    assert calls["count"] == 3


def test_check_mode_does_not_modify_existing_generated_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    sources = tmp_path / "sources.yaml"
    sources.write_text(
        yaml.safe_dump({
            "skills": [{
                "name": "demo-skill",
                "upstream": {"repo": "owner/demo-skill", "ref": "main", "path": "."},
                "target": "skills/demo-skill",
                "include": ["SKILL.md"],
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sync, "SOURCES", sources)

    existing = tmp_path / "skills" / "demo-skill"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("existing content", encoding="utf-8")

    def fake_write_skill(entry, tmpdir, *, output_root, **kwargs):
        target = output_root / entry["target"]
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("new generated content", encoding="utf-8")

    monkeypatch.setattr(sync, "write_skill", fake_write_skill)

    args = sync.build_parser().parse_args(["sync", "--check"])
    assert sync.run_sync(args) == 1
    assert (existing / "SKILL.md").read_text(encoding="utf-8") == "existing content"


# ── integration test: full pipeline with a local git repo ─────────────────


def test_full_pipeline_with_local_upstream(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sync, "ROOT", tmp_path)

    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "SKILL.md").write_text(
        "# Fake Skill\n\nA test skill for integration testing.\n\nUse pandoc and bun.\n",
        encoding="utf-8",
    )
    (upstream / "README.md").write_text(
        "# Fake Skill\n\nThis skill does literate programming with pandoc.\n",
        encoding="utf-8",
    )
    (upstream / "scripts").mkdir()
    (upstream / "scripts" / "weave.sh").write_text("#!/bin/bash\necho weave\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=upstream, check=True, capture_output=True)

    sources = tmp_path / "sources.yaml"
    sources.write_text(
        yaml.safe_dump({
            "skills": [{
                "name": "fake-skill",
                "upstream": {"repo": "test/fake-skill", "ref": "main", "path": "."},
                "target": "skills/fake-skill",
                "include": ["SKILL.md", "scripts/"],
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sync, "SOURCES", sources)

    def fake_clone(entry, tmpdir):
        name = entry["name"]
        clone_dir = tmpdir / name
        subprocess.run(["git", "clone", str(upstream), str(clone_dir)], check=True, capture_output=True)
        src_root = clone_dir
        upstream_commit = subprocess.check_output(
            ["git", "-C", str(clone_dir), "rev-parse", "HEAD"], text=True
        ).strip()
        return clone_dir, src_root, upstream_commit

    monkeypatch.setattr(sync, "clone_upstream", fake_clone)

    exit_code = sync.main(["sync"])
    assert exit_code == 0

    skill_dir = tmp_path / "skills" / "fake-skill"
    assert skill_dir.is_dir()
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "scripts" / "weave.sh").exists()

    from validate_skills import validate_skill_dir
    fm = validate_skill_dir(skill_dir)
    assert fm["name"] == "fake-skill"
    assert "pandoc" in fm["metadata"]["hermes"]["tags"]
