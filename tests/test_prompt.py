"""Tests for orxhestra-code modules."""

from __future__ import annotations

from pathlib import Path

from orxhestra_code.claude_md import load_project_instructions
from orxhestra_code.config import effort_model_kwargs, load_config
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
