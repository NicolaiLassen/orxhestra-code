"""Tests for orxhestra-code modules."""

from __future__ import annotations

from pathlib import Path

from orxhestra_code.claude_md import load_project_instructions
from orxhestra_code.config import load_config
from orxhestra_code.prompt import SYSTEM_PROMPT


def test_system_prompt_not_empty() -> None:
    assert len(SYSTEM_PROMPT) > 100


def test_system_prompt_has_key_sections() -> None:
    assert "# Doing tasks" in SYSTEM_PROMPT
    assert "# Using your tools" in SYSTEM_PROMPT
    assert "# Git workflow" in SYSTEM_PROMPT
    assert "# Executing actions with care" in SYSTEM_PROMPT


def test_default_config() -> None:
    cfg = load_config([])
    assert cfg.model == "anthropic/claude-sonnet-4-6"
    assert cfg.effort == "high"
    assert cfg.max_iterations == 30
    assert cfg.provider == "anthropic"
    assert cfg.model_name == "claude-sonnet-4-6"


def test_config_model_override() -> None:
    cfg = load_config(["--model", "openai/gpt-4o"])
    assert cfg.provider == "openai"
    assert cfg.model_name == "gpt-4o"


def test_config_effort_presets() -> None:
    low = load_config(["--effort", "low"])
    assert low.max_iterations == 5

    high = load_config(["--effort", "high"])
    assert high.max_iterations == 30


def test_load_project_instructions_empty(tmp_path: Path) -> None:
    result = load_project_instructions(tmp_path)
    assert result == ""


def test_load_project_instructions_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("Use pytest for tests.")
    result = load_project_instructions(tmp_path)
    assert "Use pytest for tests." in result


def test_load_project_instructions_orx_dir(tmp_path: Path) -> None:
    orx_dir = tmp_path / ".orx"
    orx_dir.mkdir()
    (orx_dir / "instructions.md").write_text("Follow PEP 8.")
    result = load_project_instructions(tmp_path)
    assert "Follow PEP 8." in result
