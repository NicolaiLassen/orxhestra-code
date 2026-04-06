"""Configuration loading with layered precedence.

CLI args > environment variables > config file > defaults.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path.home() / ".orx-coder"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"

EFFORT_PRESETS: dict[str, dict[str, Any]] = {
    "low": {"max_iterations": 5, "temperature": 0.0},
    "medium": {"max_iterations": 15, "temperature": 0.0},
    "high": {"max_iterations": 30, "temperature": 0.0},
}

# Provider-specific model kwargs for LLM-level reasoning effort.
_ANTHROPIC_THINKING_BUDGET: dict[str, int | None] = {
    "low": None,
    "medium": 5000,
    "high": 10000,
}


def effort_model_kwargs(provider: str, effort: str) -> dict[str, Any]:
    """Return provider-specific model kwargs for the given effort level.

    Different LLM providers expose reasoning effort in different ways.
    This maps the unified ``effort`` flag to the right constructor kwargs.
    """
    if provider == "anthropic":
        budget = _ANTHROPIC_THINKING_BUDGET.get(effort)
        if budget is None:
            return {}
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}
    if provider in ("openai", "xai", "deepseek"):
        return {"reasoning_effort": effort}
    return {}


@dataclass
class CoderConfig:
    """Resolved configuration for the coding agent.

    Attributes
    ----------
    model : str
        Provider/model string (e.g. ``"anthropic/claude-sonnet-4-6"``).
    effort : str
        One of ``"low"``, ``"medium"``, ``"high"``.
    max_tokens : int
        Maximum tokens per LLM response.
    max_iterations : int
        Maximum tool-call loop iterations (derived from effort).
    temperature : float
        LLM temperature (derived from effort).
    workspace : Path
        Project root directory.
    auto_approve_reads : bool
        Skip approval prompts for read-only tools.
    """

    model: str = "anthropic/claude-sonnet-4-6"
    effort: str = "high"
    max_tokens: int = 16384
    max_iterations: int = 30
    temperature: float = 0.0
    workspace: Path = field(default_factory=Path.cwd)
    auto_approve_reads: bool = True

    @property
    def provider(self) -> str:
        """Extract the provider name from the model string."""
        return self.model.split("/")[0] if "/" in self.model else "anthropic"

    @property
    def model_name(self) -> str:
        """Extract the model name from the model string."""
        return self.model.split("/", 1)[1] if "/" in self.model else self.model


def _load_yaml_config() -> dict[str, Any]:
    """Load config from ``~/.orx-coder/config.yaml`` if it exists."""
    if not _CONFIG_FILE.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(_CONFIG_FILE.read_text()) or {}
    except Exception:
        return {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
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
        "--workspace", "-w",
        type=Path,
        help="Project root directory (default: cwd)",
    )
    return parser.parse_args(argv)


def load_config(argv: list[str] | None = None) -> CoderConfig:
    """Build a ``CoderConfig`` from CLI args, env vars, config file, and defaults.

    Parameters
    ----------
    argv : list[str], optional
        CLI arguments.  Defaults to ``sys.argv[1:]``.

    Returns
    -------
    CoderConfig
        The resolved configuration.
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
    if "workspace" in yaml_cfg:
        cfg.workspace = Path(yaml_cfg["workspace"])
    if "auto_approve_reads" in yaml_cfg:
        cfg.auto_approve_reads = yaml_cfg["auto_approve_reads"]

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

    # Apply effort presets
    preset = EFFORT_PRESETS.get(cfg.effort, EFFORT_PRESETS["high"])
    cfg.max_iterations = preset["max_iterations"]
    cfg.temperature = preset["temperature"]

    return cfg
