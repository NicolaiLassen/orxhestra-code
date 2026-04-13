"""Tests for the system prompt."""

from __future__ import annotations

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
    assert "# Web access" in SYSTEM_PROMPT
    assert "# Memory" in SYSTEM_PROMPT
    assert "NEVER skip hooks" in SYSTEM_PROMPT
    assert "HEREDOC" in SYSTEM_PROMPT
