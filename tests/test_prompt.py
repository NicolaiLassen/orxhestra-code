"""Tests for orxhestra-code modules.

Covers prompt content, configuration loading, permission handling, project
instruction loading, and web-tool helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orxhestra_code.claude_md import load_project_instructions
from orxhestra_code.config import effort_model_kwargs, load_config
from orxhestra_code.permissions import PermissionState, check_permission
from orxhestra_code.prompt import SYSTEM_PROMPT
from orxhestra_code.tools import web as web_tools


def test_system_prompt_not_empty() -> None:
    """Verify that the system prompt has substantial content.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert len(SYSTEM_PROMPT) > 100


def test_system_prompt_has_key_sections() -> None:
    """Verify that the system prompt includes required guidance sections.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert "# Doing tasks" in SYSTEM_PROMPT
    assert "# Using your tools" in SYSTEM_PROMPT
    assert "# Git workflow" in SYSTEM_PROMPT
    assert "# Executing actions with care" in SYSTEM_PROMPT
    assert "# Committing changes" in SYSTEM_PROMPT
    assert "# Creating pull requests" in SYSTEM_PROMPT
    assert "# Shell tool guidance" in SYSTEM_PROMPT
    assert "# Output efficiency" in SYSTEM_PROMPT
    assert "# Web access" in SYSTEM_PROMPT
    assert "NEVER skip hooks" in SYSTEM_PROMPT
    assert "HEREDOC" in SYSTEM_PROMPT


def test_default_config() -> None:
    """Verify the default resolved configuration values.

    Returns
    -------
    None
        This test does not return a value.
    """
    cfg = load_config([])
    assert cfg.model == "anthropic/claude-sonnet-4-6"
    assert cfg.effort == "high"
    assert cfg.max_iterations == 200
    assert cfg.provider == "anthropic"
    assert cfg.model_name == "claude-sonnet-4-6"


def test_config_model_override() -> None:
    """Verify that the model CLI flag overrides the default model.

    Returns
    -------
    None
        This test does not return a value.
    """
    cfg = load_config(["--model", "openai/gpt-4o"])
    assert cfg.provider == "openai"
    assert cfg.model_name == "gpt-4o"


def test_config_effort_presets() -> None:
    """Verify the configured max-iteration value for effort presets.

    Returns
    -------
    None
        This test does not return a value.
    """
    low = load_config(["--effort", "low"])
    assert low.max_iterations == 200

    high = load_config(["--effort", "high"])
    assert high.max_iterations == 200


def test_effort_model_kwargs_anthropic() -> None:
    """Verify Anthropic effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("anthropic", "low") == {}
    mid = effort_model_kwargs("anthropic", "medium")
    assert mid == {"thinking": {"type": "enabled", "budget_tokens": 5000}}
    high = effort_model_kwargs("anthropic", "high")
    assert high == {"thinking": {"type": "enabled", "budget_tokens": 10000}}


def test_effort_model_kwargs_anthropic_aws() -> None:
    """Verify AWS Bedrock shares Anthropic effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    # Bedrock Claude uses same thinking format.
    assert effort_model_kwargs("aws", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 10000},
    }


def test_effort_model_kwargs_openai() -> None:
    """Verify OpenAI effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("openai", "high") == {
        "reasoning_effort": "high",
        "use_responses_api": True,
    }


def test_effort_model_kwargs_google() -> None:
    """Verify Google effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("google", "low") == {"thinking_level": "low"}
    assert effort_model_kwargs("google", "high") == {"thinking_level": "high"}
    assert effort_model_kwargs("google-vertexai", "medium") == {"thinking_level": "medium"}


def test_effort_model_kwargs_xai() -> None:
    """Verify xAI effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("xai", "high") == {"reasoning_effort": "high"}


def test_effort_model_kwargs_deepseek() -> None:
    """Verify DeepSeek effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("deepseek", "high") == {"reasoning_effort": "high"}


def test_effort_model_kwargs_azure() -> None:
    """Verify Azure OpenAI effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("azure-ai", "high") == {
        "reasoning_effort": "high",
        "use_responses_api": True,
    }


def test_effort_model_kwargs_mistral() -> None:
    """Verify Mistral effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("mistralai", "high") == {"reasoning_effort": "high"}


def test_effort_model_kwargs_groq() -> None:
    """Verify Groq effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("groq", "medium") == {"reasoning_effort": "medium"}


def test_effort_model_kwargs_cohere() -> None:
    """Verify Cohere effort mapping.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("cohere", "low") == {}
    assert effort_model_kwargs("cohere", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 10000},
    }


def test_effort_model_kwargs_unknown_provider() -> None:
    """Verify unknown providers produce no extra model kwargs.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert effort_model_kwargs("ollama", "high") == {}


def test_load_project_instructions_empty(tmp_path: Path) -> None:
    """Verify loading instructions from an empty workspace.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    result = load_project_instructions(tmp_path)
    assert result == ""


def test_load_project_instructions_claude_md(tmp_path: Path) -> None:
    """Verify loading instructions from ``CLAUDE.md``.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    (tmp_path / "CLAUDE.md").write_text("Use pytest for tests.")
    result = load_project_instructions(tmp_path)
    assert "Use pytest for tests." in result


def test_load_project_instructions_orx_dir(tmp_path: Path) -> None:
    """Verify loading instructions from ``.orx/instructions.md``.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    orx_dir = tmp_path / ".orx"
    orx_dir.mkdir()
    (orx_dir / "instructions.md").write_text("Follow PEP 8.")
    result = load_project_instructions(tmp_path)
    assert "Follow PEP 8." in result


def test_load_project_instructions_local_md(tmp_path: Path) -> None:
    """Verify loading instructions from ``CLAUDE.local.md``.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    (tmp_path / "CLAUDE.local.md").write_text("Local only rule.")
    result = load_project_instructions(tmp_path)
    assert "Local only rule." in result


def test_load_project_instructions_claude_dir(tmp_path: Path) -> None:
    """Verify loading instructions from ``.claude/CLAUDE.md``.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("Claude dir rule.")
    result = load_project_instructions(tmp_path)
    assert "Claude dir rule." in result


def test_load_project_instructions_import(tmp_path: Path) -> None:
    """Verify loading instructions with an ``@`` import.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    (tmp_path / "rules.md").write_text("Imported rule content.")
    (tmp_path / "CLAUDE.md").write_text("Main rule.\n@rules.md")
    result = load_project_instructions(tmp_path)
    assert "Main rule." in result
    assert "Imported rule content." in result


def test_load_project_instructions_circular_import(tmp_path: Path) -> None:
    """Verify circular ``@`` imports are handled safely.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    (tmp_path / "a.md").write_text("A content.\n@b.md")
    (tmp_path / "b.md").write_text("B content.\n@a.md")
    (tmp_path / "CLAUDE.md").write_text("@a.md")
    result = load_project_instructions(tmp_path)
    assert "A content." in result
    assert "B content." in result


def test_load_project_instructions_html_comments_stripped(tmp_path: Path) -> None:
    """Verify HTML comments are removed from loaded instructions.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    (tmp_path / "CLAUDE.md").write_text("Visible.\n<!-- hidden comment -->\nAlso visible.")
    result = load_project_instructions(tmp_path)
    assert "Visible." in result
    assert "Also visible." in result
    assert "hidden comment" not in result


def test_load_project_instructions_truncation(tmp_path: Path) -> None:
    """Verify oversized instruction files are truncated.

    Parameters
    ----------
    tmp_path : Path
        Temporary workspace path.

    Returns
    -------
    None
        This test does not return a value.
    """
    huge = "x" * 60_000
    (tmp_path / "CLAUDE.md").write_text(huge)
    result = load_project_instructions(tmp_path)
    assert "TRUNCATED" in result


# ── Permission mode tests ────────────────────────────────────────────


def test_permission_default_mode() -> None:
    """Verify default permission handling.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("default", "read_file", {}) == "allow"
    assert check_permission("default", "ls", {}) == "allow"
    assert check_permission("default", "glob", {}) == "allow"
    assert check_permission("default", "write_file", {}) == "ask"
    assert check_permission("default", "edit_file", {}) == "ask"
    assert check_permission("default", "shell_exec", {}) == "ask"


def test_permission_plan_mode() -> None:
    """Verify plan-mode permission handling.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("plan", "read_file", {}) == "allow"
    assert check_permission("plan", "glob", {}) == "allow"
    assert check_permission("plan", "grep", {}) == "allow"
    assert check_permission("plan", "write_file", {}) == "deny"
    assert check_permission("plan", "edit_file", {}) == "deny"
    assert check_permission("plan", "shell_exec", {}) == "deny"
    assert check_permission("plan", "mkdir", {}) == "deny"


def test_permission_accept_edits_mode() -> None:
    """Verify accept-edits permission handling.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("accept-edits", "write_file", {}) == "allow"
    assert check_permission("accept-edits", "edit_file", {}) == "allow"
    assert check_permission("accept-edits", "mkdir", {}) == "allow"
    assert check_permission("accept-edits", "shell_exec", {}) == "ask"
    assert check_permission("accept-edits", "read_file", {}) == "allow"


def test_permission_auto_approve_mode() -> None:
    """Verify auto-approve permission handling.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("auto-approve", "shell_exec", {}) == "allow"
    assert check_permission("auto-approve", "write_file", {}) == "allow"
    assert check_permission("auto-approve", "read_file", {}) == "allow"


def test_permission_trust_mode() -> None:
    """Verify trust-mode permission handling.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("trust", "shell_exec", {}) == "allow"
    assert check_permission("trust", "write_file", {}) == "allow"


def test_config_permission_mode_flag() -> None:
    """Verify the permission-mode CLI flag.

    Returns
    -------
    None
        This test does not return a value.
    """
    cfg = load_config(["--permission-mode", "plan"])
    assert cfg.permission_mode == "plan"


def test_config_auto_approve_shortcut() -> None:
    """Verify the auto-approve CLI shortcut.

    Returns
    -------
    None
        This test does not return a value.
    """
    cfg = load_config(["--auto-approve"])
    assert cfg.permission_mode == "auto-approve"


def test_permission_state_cycle() -> None:
    """Verify permission-state cycling wraps through every mode.

    Returns
    -------
    None
        This test does not return a value.
    """
    ps = PermissionState("default")
    assert ps.cycle() == "plan"
    assert ps.cycle() == "accept-edits"
    assert ps.cycle() == "auto-approve"
    assert ps.cycle() == "trust"
    assert ps.cycle() == "default"  # wraps around


def test_permission_default_mode_web_tools() -> None:
    """Verify default-mode handling for web tools.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("default", "web_search", {}) == "ask"
    assert check_permission("default", "web_fetch", {}) == "ask"


def test_permission_plan_mode_web_tools() -> None:
    """Verify plan-mode handling for web tools.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("plan", "web_search", {}) == "deny"
    assert check_permission("plan", "web_fetch", {}) == "deny"


def test_permission_accept_edits_mode_web_tools() -> None:
    """Verify accept-edits handling for web tools.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert check_permission("accept-edits", "web_search", {}) == "ask"
    assert check_permission("accept-edits", "web_fetch", {}) == "ask"


def test_web_candidate_urls() -> None:
    """Verify URL candidate normalization.

    Returns
    -------
    None
        This test does not return a value.
    """
    assert web_tools._candidate_urls("example.com") == ["https://example.com"]
    assert web_tools._candidate_urls("https://example.com") == ["https://example.com"]
    assert web_tools._candidate_urls("http://example.com") == [
        "https://example.com",
        "http://example.com",
    ]
    with pytest.raises(ValueError):
        web_tools._candidate_urls("file:///tmp/test.txt")


def test_web_search_result_formatting() -> None:
    """Verify formatting of search results.

    Returns
    -------
    None
        This test does not return a value.
    """
    result = web_tools._format_search_results(
        "python",
        [{
            "title": "Python",
            "href": "https://www.python.org",
            "body": "The official home of Python.",
        }],
    )
    assert 'Open web results for "python":' in result
    assert "https://www.python.org" in result
    assert "The official home of Python." in result


def test_web_fetch_chunk_selection_prefers_matching_content() -> None:
    """Verify relevant chunk selection favors matching text.

    Returns
    -------
    None
        This test does not return a value.
    """
    markdown = (
        "Install steps for the CLI.\n\n"
        "Caching behavior and cache invalidation details.\n\n"
        "Release notes for unrelated features."
    )
    result = web_tools._select_relevant_chunks(markdown, "cache invalidation")
    assert "cache invalidation" in result.lower()
    assert "Install steps" not in result


def test_web_fetch_rejects_binary_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify binary fetched content is rejected.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.

    Returns
    -------
    None
        This test does not return a value.
    """

    class FakeResponse:
        """Fake binary HTTP response.

        Attributes
        ----------
        headers : dict[str, str]
            Response headers for the fake response.
        content : bytes
            Raw response body.
        text : str
            Decoded text body.
        url : str
            Response URL.
        """

        headers = {"content-type": "application/pdf", "content-length": "4"}
        content = b"%PDF"
        text = ""
        url = "https://example.com/file.pdf"

        def raise_for_status(self) -> None:
            """Simulate a successful HTTP status check.

            Returns
            -------
            None
                This method does not return a value.
            """
            return None

    class FakeClient:
        """Fake HTTP client used by the binary-content test."""

        def __enter__(self) -> FakeClient:
            """Enter the fake client context.

            Returns
            -------
            FakeClient
                The active fake client.
            """
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            """Exit the fake client context.

            Parameters
            ----------
            exc_type : type or ``None``, optional
                Exception type raised inside the context.
            exc : BaseException or ``None``, optional
                Exception instance raised inside the context.
            tb : object or ``None``, optional
                Traceback object for the exception.

            Returns
            -------
            None
                This method does not return a value.
            """
            return None

        def get(self, url: str) -> FakeResponse:
            """Return the fake binary response.

            Parameters
            ----------
            url : str
                Requested URL.

            Returns
            -------
            FakeResponse
                Fake HTTP response object.
            """
            return FakeResponse()

    monkeypatch.setattr(web_tools.httpx, "Client", lambda **kwargs: FakeClient())
    result = web_tools.web_fetch("https://example.com/file.pdf")
    assert "binary or unsupported" in result


def test_web_fetch_extracts_relevant_html(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify HTML fetching extracts and filters readable content.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.

    Returns
    -------
    None
        This test does not return a value.
    """

    class FakeResponse:
        """Fake HTML HTTP response.

        Attributes
        ----------
        headers : dict[str, str]
            Response headers for the fake response.
        content : bytes
            Raw response body.
        text : str
            Decoded text body.
        url : str
            Response URL.
        """

        headers = {"content-type": "text/html; charset=utf-8", "content-length": "64"}
        content = b"<html><title>Docs</title></html>"
        text = "<html><title>Docs</title><body>ignored</body></html>"
        url = "https://example.com/docs"

        def raise_for_status(self) -> None:
            """Simulate a successful HTTP status check.

            Returns
            -------
            None
                This method does not return a value.
            """
            return None

    class FakeClient:
        """Fake HTTP client used by the HTML extraction test."""

        def __enter__(self) -> FakeClient:
            """Enter the fake client context.

            Returns
            -------
            FakeClient
                The active fake client.
            """
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            """Exit the fake client context.

            Parameters
            ----------
            exc_type : type or ``None``, optional
                Exception type raised inside the context.
            exc : BaseException or ``None``, optional
                Exception instance raised inside the context.
            tb : object or ``None``, optional
                Traceback object for the exception.

            Returns
            -------
            None
                This method does not return a value.
            """
            return None

        def get(self, url: str) -> FakeResponse:
            """Return the fake HTML response.

            Parameters
            ----------
            url : str
                Requested URL.

            Returns
            -------
            FakeResponse
                Fake HTTP response object.
            """
            return FakeResponse()

    monkeypatch.setattr(web_tools.httpx, "Client", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        web_tools.trafilatura,
        "extract",
        lambda text, output_format=None: (
            "Install steps.\n\nCaching behavior and cache invalidation."
        ),
    )

    result = web_tools.web_fetch("https://example.com/docs", prompt="cache invalidation")
    assert "Fetched: https://example.com/docs" in result
    assert "Title: Docs" in result
    assert "Caching behavior and cache invalidation." in result
    assert "Install steps." not in result
