"""Tests for orxhestra-code modules."""

from __future__ import annotations

from pathlib import Path

from orxhestra_code.claude_md import load_project_instructions
from orxhestra_code.config import effort_model_kwargs, load_config
from orxhestra_code.permissions import PermissionState, check_permission
from orxhestra_code.prompt import SYSTEM_PROMPT


def test_system_prompt_not_empty() -> None:
    assert len(SYSTEM_PROMPT) > 100


def test_system_prompt_has_key_sections() -> None:
    assert "# Doing tasks" in SYSTEM_PROMPT
    assert "# Using your tools" in SYSTEM_PROMPT
    assert "# Git workflow" in SYSTEM_PROMPT
    assert "# Executing actions with care" in SYSTEM_PROMPT
    assert "# Committing changes" in SYSTEM_PROMPT
    assert "# Creating pull requests" in SYSTEM_PROMPT
    assert "# Shell tool guidance" in SYSTEM_PROMPT
    assert "# Output efficiency" in SYSTEM_PROMPT
    assert "NEVER skip hooks" in SYSTEM_PROMPT
    assert "HEREDOC" in SYSTEM_PROMPT


def test_default_config() -> None:
    cfg = load_config([])
    assert cfg.model == "anthropic/claude-sonnet-4-6"
    assert cfg.effort == "high"
    assert cfg.max_iterations == 200
    assert cfg.provider == "anthropic"
    assert cfg.model_name == "claude-sonnet-4-6"


def test_config_model_override() -> None:
    cfg = load_config(["--model", "openai/gpt-4o"])
    assert cfg.provider == "openai"
    assert cfg.model_name == "gpt-4o"


def test_config_effort_presets() -> None:
    low = load_config(["--effort", "low"])
    assert low.max_iterations == 50

    high = load_config(["--effort", "high"])
    assert high.max_iterations == 200


def test_effort_model_kwargs_anthropic() -> None:
    assert effort_model_kwargs("anthropic", "low") == {}
    mid = effort_model_kwargs("anthropic", "medium")
    assert mid == {"thinking": {"type": "enabled", "budget_tokens": 5000}}
    high = effort_model_kwargs("anthropic", "high")
    assert high == {"thinking": {"type": "enabled", "budget_tokens": 10000}}


def test_effort_model_kwargs_anthropic_aws() -> None:
    # Bedrock Claude uses same thinking format.
    assert effort_model_kwargs("aws", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 10000},
    }


def test_effort_model_kwargs_openai() -> None:
    assert effort_model_kwargs("openai", "high") == {
        "reasoning_effort": "high",
        "use_responses_api": True,
    }


def test_effort_model_kwargs_google() -> None:
    assert effort_model_kwargs("google", "low") == {"thinking_level": "low"}
    assert effort_model_kwargs("google", "high") == {"thinking_level": "high"}
    assert effort_model_kwargs("google-vertexai", "medium") == {"thinking_level": "medium"}


def test_effort_model_kwargs_xai() -> None:
    assert effort_model_kwargs("xai", "high") == {"reasoning_effort": "high"}


def test_effort_model_kwargs_deepseek() -> None:
    assert effort_model_kwargs("deepseek", "high") == {"reasoning_effort": "high"}


def test_effort_model_kwargs_azure() -> None:
    assert effort_model_kwargs("azure-ai", "high") == {
        "reasoning_effort": "high",
        "use_responses_api": True,
    }


def test_effort_model_kwargs_mistral() -> None:
    assert effort_model_kwargs("mistralai", "high") == {"reasoning_effort": "high"}


def test_effort_model_kwargs_groq() -> None:
    assert effort_model_kwargs("groq", "medium") == {"reasoning_effort": "medium"}


def test_effort_model_kwargs_cohere() -> None:
    assert effort_model_kwargs("cohere", "low") == {}
    assert effort_model_kwargs("cohere", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 10000},
    }


def test_effort_model_kwargs_unknown_provider() -> None:
    assert effort_model_kwargs("ollama", "high") == {}


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


def test_load_project_instructions_local_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.local.md").write_text("Local only rule.")
    result = load_project_instructions(tmp_path)
    assert "Local only rule." in result


def test_load_project_instructions_claude_dir(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("Claude dir rule.")
    result = load_project_instructions(tmp_path)
    assert "Claude dir rule." in result


def test_load_project_instructions_import(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("Imported rule content.")
    (tmp_path / "CLAUDE.md").write_text("Main rule.\n@rules.md")
    result = load_project_instructions(tmp_path)
    assert "Main rule." in result
    assert "Imported rule content." in result


def test_load_project_instructions_circular_import(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("A content.\n@b.md")
    (tmp_path / "b.md").write_text("B content.\n@a.md")
    (tmp_path / "CLAUDE.md").write_text("@a.md")
    result = load_project_instructions(tmp_path)
    assert "A content." in result
    assert "B content." in result


def test_load_project_instructions_html_comments_stripped(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("Visible.\n<!-- hidden comment -->\nAlso visible.")
    result = load_project_instructions(tmp_path)
    assert "Visible." in result
    assert "Also visible." in result
    assert "hidden comment" not in result


def test_load_project_instructions_truncation(tmp_path: Path) -> None:
    huge = "x" * 60_000
    (tmp_path / "CLAUDE.md").write_text(huge)
    result = load_project_instructions(tmp_path)
    assert "TRUNCATED" in result


# ── Permission mode tests ────────────────────────────────────────────


def test_permission_default_mode() -> None:
    assert check_permission("default", "read_file", {}) == "allow"
    assert check_permission("default", "ls", {}) == "allow"
    assert check_permission("default", "glob", {}) == "allow"
    assert check_permission("default", "write_file", {}) == "ask"
    assert check_permission("default", "edit_file", {}) == "ask"
    assert check_permission("default", "shell_exec", {}) == "ask"


def test_permission_plan_mode() -> None:
    assert check_permission("plan", "read_file", {}) == "allow"
    assert check_permission("plan", "glob", {}) == "allow"
    assert check_permission("plan", "grep", {}) == "allow"
    assert check_permission("plan", "write_file", {}) == "deny"
    assert check_permission("plan", "edit_file", {}) == "deny"
    assert check_permission("plan", "shell_exec", {}) == "deny"
    assert check_permission("plan", "mkdir", {}) == "deny"


def test_permission_accept_edits_mode() -> None:
    assert check_permission("accept-edits", "write_file", {}) == "allow"
    assert check_permission("accept-edits", "edit_file", {}) == "allow"
    assert check_permission("accept-edits", "mkdir", {}) == "allow"
    assert check_permission("accept-edits", "shell_exec", {}) == "ask"
    assert check_permission("accept-edits", "read_file", {}) == "allow"


def test_permission_auto_approve_mode() -> None:
    assert check_permission("auto-approve", "shell_exec", {}) == "allow"
    assert check_permission("auto-approve", "write_file", {}) == "allow"
    assert check_permission("auto-approve", "read_file", {}) == "allow"


def test_permission_trust_mode() -> None:
    assert check_permission("trust", "shell_exec", {}) == "allow"
    assert check_permission("trust", "write_file", {}) == "allow"


def test_config_permission_mode_flag() -> None:
    cfg = load_config(["--permission-mode", "plan"])
    assert cfg.permission_mode == "plan"


def test_config_auto_approve_shortcut() -> None:
    cfg = load_config(["--auto-approve"])
    assert cfg.permission_mode == "auto-approve"


def test_permission_state_cycle() -> None:
    ps = PermissionState("default")
    assert ps.cycle() == "plan"
    assert ps.cycle() == "accept-edits"
    assert ps.cycle() == "auto-approve"
    assert ps.cycle() == "trust"
    assert ps.cycle() == "default"  # wraps around
