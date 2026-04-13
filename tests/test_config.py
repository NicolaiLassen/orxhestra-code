"""Tests for configuration loading and effort mapping."""

from __future__ import annotations

from orxhestra_code.config import effort_model_kwargs, load_config


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
    assert low.max_iterations == 200

    high = load_config(["--effort", "high"])
    assert high.max_iterations == 200


def test_config_permission_mode_flag() -> None:
    cfg = load_config(["--permission-mode", "plan"])
    assert cfg.permission_mode == "plan"


def test_config_auto_approve_shortcut() -> None:
    cfg = load_config(["--auto-approve"])
    assert cfg.permission_mode == "auto-approve"


# ── Effort model kwargs per provider ─────────────────────────────


def test_effort_anthropic() -> None:
    assert effort_model_kwargs("anthropic", "low") == {}
    assert effort_model_kwargs("anthropic", "medium") == {
        "thinking": {"type": "enabled", "budget_tokens": 5000},
    }
    assert effort_model_kwargs("anthropic", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 10000},
    }


def test_effort_aws() -> None:
    assert effort_model_kwargs("aws", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 10000},
    }


def test_effort_openai() -> None:
    assert effort_model_kwargs("openai", "high") == {
        "reasoning_effort": "high",
        "use_responses_api": True,
    }


def test_effort_azure() -> None:
    assert effort_model_kwargs("azure-ai", "high") == {
        "reasoning_effort": "high",
        "use_responses_api": True,
    }


def test_effort_google() -> None:
    assert effort_model_kwargs("google", "low") == {"thinking_level": "low"}
    assert effort_model_kwargs("google", "high") == {"thinking_level": "high"}
    assert effort_model_kwargs("google-vertexai", "medium") == {"thinking_level": "medium"}


def test_effort_xai() -> None:
    assert effort_model_kwargs("xai", "high") == {"reasoning_effort": "high"}


def test_effort_deepseek() -> None:
    assert effort_model_kwargs("deepseek", "high") == {"reasoning_effort": "high"}


def test_effort_mistral() -> None:
    assert effort_model_kwargs("mistralai", "high") == {"reasoning_effort": "high"}


def test_effort_groq() -> None:
    assert effort_model_kwargs("groq", "medium") == {"reasoning_effort": "medium"}


def test_effort_cohere() -> None:
    assert effort_model_kwargs("cohere", "low") == {}
    assert effort_model_kwargs("cohere", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 10000},
    }


def test_effort_unknown_provider() -> None:
    assert effort_model_kwargs("ollama", "high") == {}
