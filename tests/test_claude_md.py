"""Tests for CLAUDE.md instruction loading."""

from __future__ import annotations

from pathlib import Path

from orxhestra_code.claude_md import load_project_instructions


def test_empty_workspace(tmp_path: Path) -> None:
    assert load_project_instructions(tmp_path) == ""


def test_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("Use pytest for tests.")
    result = load_project_instructions(tmp_path)
    assert "Use pytest for tests." in result


def test_orx_dir(tmp_path: Path) -> None:
    orx_dir = tmp_path / ".orx"
    orx_dir.mkdir()
    (orx_dir / "instructions.md").write_text("Follow PEP 8.")
    result = load_project_instructions(tmp_path)
    assert "Follow PEP 8." in result


def test_local_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.local.md").write_text("Local only rule.")
    result = load_project_instructions(tmp_path)
    assert "Local only rule." in result


def test_claude_dir(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("Claude dir rule.")
    result = load_project_instructions(tmp_path)
    assert "Claude dir rule." in result


def test_import_directive(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("Imported rule content.")
    (tmp_path / "CLAUDE.md").write_text("Main rule.\n@rules.md")
    result = load_project_instructions(tmp_path)
    assert "Main rule." in result
    assert "Imported rule content." in result


def test_circular_import(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("A content.\n@b.md")
    (tmp_path / "b.md").write_text("B content.\n@a.md")
    (tmp_path / "CLAUDE.md").write_text("@a.md")
    result = load_project_instructions(tmp_path)
    assert "A content." in result
    assert "B content." in result


def test_html_comments_stripped(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("Visible.\n<!-- hidden -->\nAlso visible.")
    result = load_project_instructions(tmp_path)
    assert "Visible." in result
    assert "Also visible." in result
    assert "hidden" not in result


def test_truncation(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("x" * 60_000)
    result = load_project_instructions(tmp_path)
    assert "TRUNCATED" in result
