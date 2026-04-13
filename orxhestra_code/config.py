"""Configuration loading with layered precedence.

Resolves coding-agent settings from CLI arguments, environment variables,
a config file, and built-in defaults.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path.home() / ".orx-coder"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"

# Default max tool-call iterations per turn.  Claude Code has no limit
# in interactive mode.  200 is effectively unlimited — context window
# auto-compacts long before this.  Configurable via --max-iterations,
# config file, or ORX_MAX_ITERATIONS env var.
DEFAULT_MAX_ITERATIONS: int = 200

# Provider-specific model kwargs for LLM-level reasoning effort.
#
# Anthropic:       thinking.budget_tokens  (Claude Sonnet 4+, Opus 4+)
# AWS Bedrock:     thinking.budget_tokens  (Bedrock Claude)
# OpenAI:          reasoning.effort        (gpt-5+, o-series)
# Azure OpenAI:    reasoning.effort        (same as OpenAI)
# Google:          thinking_level           (Gemini 3+, Gemini 2.5)
# Google Vertex:   thinking_level           (Vertex AI Gemini)
# xAI:             reasoning_effort         (Grok 3 Mini, Grok 4.20)
# DeepSeek:        reasoning_effort         (deepseek-reasoner)
# Mistral:         reasoning_effort         (Magistral, Mistral Small 4+)
# Groq:            reasoning_effort         (QwQ, GPT-OSS models)
# Cohere:          thinking.budget_tokens   (Command A Reasoning)
_ANTHROPIC_THINKING_BUDGET: dict[str, int | None] = {
    "low": None,
    "medium": 5000,
    "high": 10000,
}


def effort_model_kwargs(provider: str, effort: str) -> dict[str, Any]:
    """Return provider-specific model kwargs for a reasoning effort level.

    Parameters
    ----------
    provider : str
        LLM provider name.
    effort : str
        Unified effort level such as ``"low"``, ``"medium"``, or ``"high"``.

    Returns
    -------
    dict[str, Any]
        Provider-specific model keyword arguments.
    """
    # Anthropic / AWS Bedrock — extended thinking with budget_tokens.
    if provider in ("anthropic", "aws"):
        budget = _ANTHROPIC_THINKING_BUDGET.get(effort)
        if budget is None:
            return {}
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    # OpenAI / Azure OpenAI — reasoning_effort requires the Responses API
    # when used with function tools (/v1/chat/completions rejects it).
    if provider in ("openai", "azure-ai"):
        return {"reasoning_effort": effort, "use_responses_api": True}

    # Google Gemini — thinking_level parameter.
    if provider in ("google", "google-vertexai"):
        return {"thinking_level": effort}

    # xAI Grok — reasoning_effort string.
    if provider == "xai":
        return {"reasoning_effort": effort}

    # DeepSeek — reasoning_effort string.
    if provider == "deepseek":
        return {"reasoning_effort": effort}

    # Mistral — reasoning_effort string (Magistral, Mistral Small 4+).
    if provider == "mistralai":
        return {"reasoning_effort": effort}

    # Groq — reasoning_effort string (QwQ, GPT-OSS models).
    if provider == "groq":
        return {"reasoning_effort": effort}

    # Cohere — thinking with token budget.
    if provider == "cohere":
        budget = _ANTHROPIC_THINKING_BUDGET.get(effort)
        if budget is None:
            return {}
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    return {}


@dataclass
class CoderConfig:
    """Resolved configuration for the coding agent.

    Attributes
    ----------
    model : str, optional
        Provider and model identifier.
    effort : str, optional
        Effort level for the selected model.
    max_tokens : int, optional
        Maximum tokens per model response.
    max_iterations : int, optional
        Maximum tool-call loop iterations per turn.
    permission_mode : str, optional
        Active permission mode for tool execution.
    resume_session : str or ``None``, optional
        Session ID to resume, or ``"latest"`` for the most recent session.
    workspace : Path, optional
        Workspace directory used by the agent.
    auto_approve_reads : bool, optional
        Whether read-only tools skip approval prompts.
    """

    model: str = "anthropic/claude-sonnet-4-6"
    effort: str = "high"
    max_tokens: int = 16384
    max_iterations: int = 200
    permission_mode: str = "default"
    resume_session: str | None = None
    workspace: Path = field(default_factory=Path.cwd)
    auto_approve_reads: bool = True

    @property
    def provider(self) -> str:
        """Provider name extracted from ``model``."""
        return self.model.split("/")[0] if "/" in self.model else "anthropic"

    @property
    def model_name(self) -> str:
        """Model name extracted from ``model``."""
        return self.model.split("/", 1)[1] if "/" in self.model else self.model


def _load_yaml_config() -> dict[str, Any]:
    """Load the user config file when it exists.

    Returns
    -------
    dict[str, Any]
        Parsed config values, or an empty mapping on failure.
    """
    if not _CONFIG_FILE.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(_CONFIG_FILE.read_text()) or {}
    except Exception:
        return {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv : list[str] or ``None``, optional
        CLI arguments to parse.

    Returns
    -------
    argparse.Namespace
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        prog="orx-coder",
        description="AI coding agent powered by orxhestra",
    )
    parser.add_argument(
        "--model", "-m",
        help="LLM provider/model (e.g. anthropic/claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--effort", "-e",
        choices=["low", "medium", "high"],
        help="Effort level: low (fast), medium, high (thorough)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="Maximum tokens per LLM response",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Maximum tool-call iterations per turn (default: 200)",
    )
    parser.add_argument(
        "--workspace", "-w",
        type=Path,
        help="Project root directory (default: cwd)",
    )
    parser.add_argument(
        "-c", "--continue", dest="continue_session",
        action="store_true",
        help="Continue the most recent session",
    )
    parser.add_argument(
        "-r", "--resume",
        type=str,
        metavar="SESSION_ID",
        help="Resume a specific session by ID",
    )
    parser.add_argument(
        "--permission-mode",
        choices=["default", "plan", "accept-edits", "auto-approve", "trust"],
        help="Permission mode: default (prompt), plan (read-only), "
        "accept-edits (auto-approve edits), auto-approve (all), trust (all+quiet)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Shortcut for --permission-mode auto-approve",
    )
    return parser.parse_args(argv)


def load_config(argv: list[str] | None = None) -> CoderConfig:
    """Build the resolved coding-agent configuration.

    Parameters
    ----------
    argv : list[str] or ``None``, optional
        CLI arguments to parse.

    Returns
    -------
    CoderConfig
        Resolved configuration values.
    """
    args = parse_args(argv)
    yaml_cfg = _load_yaml_config()
    cfg = CoderConfig()

    # Layer 1: config file
    if "model" in yaml_cfg:
        cfg.model = yaml_cfg["model"]
    if "effort" in yaml_cfg:
        cfg.effort = yaml_cfg["effort"]
    if "max_tokens" in yaml_cfg:
        cfg.max_tokens = yaml_cfg["max_tokens"]
    if "max_iterations" in yaml_cfg:
        cfg.max_iterations = yaml_cfg["max_iterations"]
    if "workspace" in yaml_cfg:
        cfg.workspace = Path(yaml_cfg["workspace"])
    if "auto_approve_reads" in yaml_cfg:
        cfg.auto_approve_reads = yaml_cfg["auto_approve_reads"]
    if "permission_mode" in yaml_cfg:
        cfg.permission_mode = yaml_cfg["permission_mode"]

    # Layer 2: environment variables
    if env_model := os.environ.get("ORX_MODEL"):
        cfg.model = env_model
    if env_effort := os.environ.get("ORX_EFFORT"):
        cfg.effort = env_effort

    # Layer 3: CLI args (highest priority)
    if args.model:
        cfg.model = args.model
    if args.effort:
        cfg.effort = args.effort
    if args.max_tokens:
        cfg.max_tokens = args.max_tokens
    if args.workspace:
        cfg.workspace = args.workspace
    if getattr(args, "resume", None):
        cfg.resume_session = args.resume
    elif getattr(args, "continue_session", False):
        cfg.resume_session = "latest"
    if env_perm := os.environ.get("ORX_PERMISSION_MODE"):
        cfg.permission_mode = env_perm
    if getattr(args, "permission_mode", None):
        cfg.permission_mode = args.permission_mode
    if getattr(args, "auto_approve", False):
        cfg.permission_mode = "auto-approve"

    # Max iterations — configurable, not tied to effort.
    if env_iter := os.environ.get("ORX_MAX_ITERATIONS"):
        try:
            cfg.max_iterations = int(env_iter)
        except ValueError:
            pass
    if getattr(args, "max_iterations", None):
        cfg.max_iterations = args.max_iterations

    return cfg
