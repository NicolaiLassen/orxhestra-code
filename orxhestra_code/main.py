"""CLI entry point for orx-coder.

Builds the coding-focused agent configuration, injects runtime tools and
callbacks, and starts the interactive or single-shot CLI flow.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import tempfile

# ── RuntimeContext + rebuild_state (our logic, not SDK's) ────────
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ── SDK imports (direct, no wrapper layer) ───────────────────────
from orxhestra.cli.commands import (
    get_command_names,
    handle_slash_command,
    register_command,
)
from orxhestra.cli.render import print_banner
from orxhestra.cli.stream import stream_response
from orxhestra.cli.theme import make_console

from orxhestra_code.claude_md import load_project_instructions
from orxhestra_code.config import CoderConfig, effort_model_kwargs, load_config
from orxhestra_code.permissions import (
    PERMISSION_MODE_LABELS,
    PERMISSION_MODES,
    PermissionState,
    make_before_tool_callback,
)
from orxhestra_code.prompt import SYSTEM_PROMPT
from orxhestra_code.tools.plan_mode import make_plan_mode_tools
from orxhestra_code.tools.web import make_web_tools


@dataclass
class RuntimeContext:
    """Mutable runtime context shared across the CLI loop and commands."""

    cfg: CoderConfig
    workspace: Path
    orx_path: Path


async def build_state(orx_path: Path, model_name: str, workspace: str) -> Any:
    """Build REPL state from an ``orx.yaml`` file."""
    from orxhestra.cli.builder import build_from_orx

    return await build_from_orx(orx_path, model_name, workspace)


async def rebuild_state(
    state: Any, orx_path: Path, model_name: str, workspace: str,
) -> None:
    """Rebuild runtime state while preserving session history."""
    from orxhestra.cli.config import DEFAULT_USER_ID

    old_session = await state.runner.get_or_create_session(
        user_id=DEFAULT_USER_ID, session_id=state.session_id,
    )
    old_events = list(old_session.events)

    new_state = await build_state(orx_path, model_name, workspace)
    state.runner = new_state.runner
    state.todo_list = new_state.todo_list
    state.model_name = new_state.model_name
    state.turn_count = 0

    new_session = await state.runner.get_or_create_session(
        user_id=DEFAULT_USER_ID, session_id=state.session_id,
    )
    new_session.events.extend(old_events)

_PROVIDER_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "cohere": "COHERE_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

_DIFF_PREVIEW_LINE_LIMIT = 160


def _check_api_key(cfg: CoderConfig) -> None:
    """Exit when the configured provider is missing its API key.

    Parameters
    ----------
    cfg : CoderConfig
        Resolved runtime configuration.

    Returns
    -------
    None
        This function does not return a value.
    """
    env_var = _PROVIDER_ENV_VARS.get(cfg.provider)
    if env_var and not os.environ.get(env_var):
        # Don't fail for local providers.
        if cfg.provider in ("ollama",):
            return
        print(f"\n  Missing {env_var}.")
        print(f"  Set it with: export {env_var}=your-key-here\n")
        sys.exit(1)


def _build_permission_section(mode: str) -> str:
    """Build the permission section for the system prompt.

    Parameters
    ----------
    mode : str
        Active permission mode.

    Returns
    -------
    str
        Prompt section describing tool restrictions for the mode.
    """
    sections: dict[str, str] = {
        "default": """\
# Permission mode: default

Tools are executed in the **default** permission mode. Destructive tools \
(file writes, edits, shell commands, directory creation) and web tools \
(`web_search`, `web_fetch`) require user approval before execution. \
Read-only local tools (file reads, glob, grep, ls) are auto-approved. \
If the user denies a tool call, do not re-attempt the exact same call. \
Instead, think about why it was denied and adjust your approach.""",

        "plan": """\
# Permission mode: plan (read-only)

You are in **plan mode** — a read-only analysis mode. You can ONLY:
- Read files, search with glob/grep, list directories
- Think, analyze, and explain code
- Create task lists and plans

You CANNOT and MUST NOT attempt to:
- Write or edit any files
- Run shell commands
- Use `web_search` or `web_fetch`
- Create directories
- Make any changes to the codebase

If the user asks you to make changes, explain what you WOULD do and \
present a plan, but do not execute it. Suggest the user switch to a \
different permission mode when ready to implement.""",

        "accept-edits": """\
# Permission mode: accept-edits

File operations (write, edit, mkdir) are **auto-approved** — you can \
freely create and modify files without prompting. Shell commands and web \
tools still require user approval. Read-only local tools are auto-approved. \
Use this mode for focused coding tasks where file changes are expected.""",

        "auto-approve": """\
# Permission mode: auto-approve

All tool calls are **auto-approved** — no prompts will be shown. You can \
freely read, write, edit files, use web tools, and run shell commands. \
Exercise extra caution with destructive operations since the user will not \
be prompted to confirm. Prefer safe, reversible actions.""",

        "trust": """\
# Permission mode: trust

All tool calls are **auto-approved** with no warnings. Full autonomous \
operation. Exercise maximum caution with destructive operations — there \
is no safety net. Only use destructive git operations, web actions, or \
file deletions when you are absolutely certain they are correct.""",
    }
    return sections.get(mode, sections["default"])


def _build_env_section(cfg: CoderConfig, workspace: Path) -> str:
    """Build the dynamic environment section for the system prompt.

    Parameters
    ----------
    cfg : CoderConfig
        Resolved runtime configuration.
    workspace : Path
        Workspace directory for the current run.

    Returns
    -------
    str
        Prompt section describing the local runtime environment.
    """
    import platform
    import shutil
    import subprocess

    is_git = (workspace / ".git").exists()
    shell = os.environ.get("SHELL", "bash").rsplit("/", 1)[-1]
    os_version = platform.platform()

    git_info = ""
    if is_git:
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=str(workspace), timeout=5,
            ).stdout.strip()
            git_info = f"\n  Git branch: {branch}" if branch else ""
        except Exception:
            pass

    # Detect common tools
    tools_available: list[str] = []
    for tool_name in ("git", "gh", "node", "npm", "python", "uv", "pip", "docker"):
        if shutil.which(tool_name):
            tools_available.append(tool_name)

    from orxhestra.memory.file_memory_service import get_memory_dir

    memory_dir = get_memory_dir(str(workspace))

    return f"""\
# Environment

- Working directory: {workspace}
- Is a git repository: {"yes" if is_git else "no"}{git_info}
- Platform: {platform.system().lower()}
- Shell: {shell}
- OS: {os_version}
- Model: {cfg.model}
- Effort: {cfg.effort}
- Memory directory: {memory_dir}
- Available tools: {', '.join(tools_available) if tools_available else 'unknown'}"""


def _build_orx_yaml(cfg: CoderConfig, workspace: Path) -> Path:
    """Generate the temporary ``orx.yaml`` file for a session.

    Parameters
    ----------
    cfg : CoderConfig
        Resolved runtime configuration.
    workspace : Path
        Workspace directory for the session.

    Returns
    -------
    Path
        Path to the generated YAML file.
    """
    project_instructions: str = load_project_instructions(workspace)

    # Build dynamic sections (like Claude Code's per-turn assembly).
    env_section = _build_env_section(cfg, workspace)
    permission_section = _build_permission_section(cfg.permission_mode)

    instructions: str = SYSTEM_PROMPT
    if project_instructions:
        instructions = f"{instructions}\n\n{project_instructions}"
    instructions = f"{instructions}\n\n{permission_section}\n\n{env_section}"

    # Escape for YAML multiline block scalar.
    escaped: str = instructions.replace("\\", "\\\\")

    # Session database path for persistence.
    session_dir = Path.home() / ".orx-coder"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_db = str(session_dir / "sessions.db")

    # Build extra model kwargs for LLM-level reasoning effort.
    extra_model = effort_model_kwargs(cfg.provider, cfg.effort)
    extra_yaml = ""
    if extra_model:
        import yaml as _yaml

        dumped = _yaml.dump(extra_model, default_flow_style=False).rstrip()
        extra_yaml = "\n" + "\n".join("    " + line for line in dumped.splitlines())

    yaml_content: str = f"""\
defaults:
  model:
    provider: {cfg.provider}
    name: {cfg.model_name}{extra_yaml}

tools:
  filesystem:
    builtin: "filesystem"
  shell:
    builtin: "shell"
  artifacts:
    builtin: "artifacts"
  memory:
    builtin: "memory"
  todos:
    builtin: "write_todos"
  task:
    builtin: "task"
  human_input:
    builtin: "human_input"

agents:
  orx-coder:
    type: llm
    max_iterations: {cfg.max_iterations}
    instructions: |
{_indent(escaped, 6)}
    tools:
      - filesystem
      - shell
      - artifacts
      - memory
      - todos
      - task
      - human_input

main_agent: orx-coder

runner:
  app_name: orx-coder
  session_service: sqlite+aiosqlite:///{session_db}
  artifact_service: memory
  compaction:
    char_threshold: 80000
    retention_chars: 15000
"""
    tmp = Path(tempfile.mkdtemp()) / "orx-coder.yaml"
    tmp.write_text(yaml_content)
    return tmp


def _register_permission_commands(perm_state: PermissionState) -> None:
    """Register the permission-related slash commands.

    Parameters
    ----------
    perm_state : PermissionState
        Mutable permission state shared with the REPL.

    Returns
    -------
    None
        This function does not return a value.
    """
    async def _cmd_permissions(state: Any, cmd_arg: str | None, **kw: Any) -> None:
        """Handle permission-mode slash commands.

        Parameters
        ----------
        state : Any
            REPL command state.
        cmd_arg : str or ``None``, optional
            Optional command argument.
        **kw : Any
            Additional command context.

        Returns
        -------
        None
            This command does not return a value.
        """
        console = kw.get("console")
        if not console:
            return
        if cmd_arg and cmd_arg in PERMISSION_MODES:
            perm_state.mode = cmd_arg
            console.print(
                f"  [orx.status]Permission mode: "
                f"{PERMISSION_MODE_LABELS[perm_state.mode]}[/orx.status]"
            )
        elif cmd_arg == "cycle":
            new_mode = perm_state.cycle()
            console.print(
                f"  [orx.status]Permission mode: "
                f"{PERMISSION_MODE_LABELS[new_mode]}[/orx.status]"
            )
        else:
            console.print(
                f"  [orx.status]Current mode: "
                f"{PERMISSION_MODE_LABELS[perm_state.mode]}[/orx.status]"
            )
            console.print(
                "  [orx.status]Available: "
                + ", ".join(PERMISSION_MODES)
                + "[/orx.status]"
            )
            console.print(
                "  [orx.status]Usage: /permissions <mode> "
                "or /permissions cycle[/orx.status]"
            )

    register_command("/permissions", _cmd_permissions)
    register_command("/perm", _cmd_permissions)
    register_command("/mode", _cmd_permissions)


def _current_model_id(state: Any, cfg: CoderConfig) -> str:
    """Return the active provider/model identifier for the current session.

    Parameters
    ----------
    state : Any
        REPL state containing the current model name.
    cfg : CoderConfig
        Mutable runtime configuration.

    Returns
    -------
    str
        Full provider/model identifier.
    """
    model_name = getattr(state, "model_name", cfg.model_name)
    if isinstance(model_name, str) and "/" in model_name:
        return model_name
    return f"{cfg.provider}/{model_name}"


async def _handle_effort_command(
    state: Any,
    cmd_arg: str | None,
    *,
    console: Any,
    runtime_ctx: RuntimeContext | None,
    perm_state: PermissionState | None,
    usage_tracker: Any = None,
) -> None:
    """Show or update the active reasoning effort.

    Parameters
    ----------
    state : Any
        REPL command state.
    cmd_arg : str or ``None``
        Optional effort level.
    console : Any
        Rich console for status rendering.
    runtime_ctx : RuntimeContext or ``None``
        Mutable runtime context for the current REPL session.
    perm_state : PermissionState or ``None``
        Mutable permission state shared with callbacks.
    usage_tracker : Any, optional
        Token usage callback to preserve after rebuild.

    Returns
    -------
    None
        This coroutine does not return a value.
    """
    if not console:
        return
    if runtime_ctx is None or perm_state is None:
        console.print("  [orx.error]Effort switching is unavailable.[/orx.error]")
        return
    if not cmd_arg:
        console.print(
            f"  [orx.status]Current effort: {runtime_ctx.cfg.effort}[/orx.status]"
        )
        console.print(
            "  [orx.status]Usage: /effort <low|medium|high>[/orx.status]"
        )
        return

    effort = cmd_arg.strip().lower()
    if effort not in {"low", "medium", "high"}:
        console.print(
            "  [orx.status]Usage: /effort <low|medium|high>[/orx.status]"
        )
        return

    runtime_ctx.cfg.model = _current_model_id(state, runtime_ctx.cfg)
    runtime_ctx.cfg.effort = effort
    runtime_ctx.orx_path = _build_orx_yaml(runtime_ctx.cfg, runtime_ctx.workspace)

    try:
        await rebuild_state(
            state,
            runtime_ctx.orx_path,
            runtime_ctx.cfg.model_name,
            str(runtime_ctx.workspace),
        )
    except Exception as exc:
        console.print(f"  [orx.error]Error: {exc}[/orx.error]")
        return

    _inject_plan_tools(state.runner.agent, perm_state)
    _inject_web_tools(state.runner.agent)
    _inject_permission_callback(state.runner.agent, perm_state, usage_tracker)
    console.print(f"  [orx.status]Effort: {effort}[/orx.status]")


def _parse_diff_args(cmd_arg: str | None) -> tuple[str, bool] | None:
    """Parse scope and output mode for ``/diff``.

    Parameters
    ----------
    cmd_arg : str or ``None``
        Optional command argument.

    Returns
    -------
    tuple[str, bool] or ``None``
        Parsed ``(scope, show_full)`` values, or ``None`` when the input is
        invalid.
    """
    scope: str | None = None
    show_full = False
    if not cmd_arg:
        return "all", show_full

    for token in cmd_arg.split():
        value = token.lower()
        if value in {"full", "--full", "-f"}:
            show_full = True
        elif value in {"staged", "--staged", "cached", "--cached"}:
            if scope and scope != "staged":
                return None
            scope = "staged"
        elif value in {"unstaged", "--unstaged", "working"}:
            if scope and scope != "unstaged":
                return None
            scope = "unstaged"
        else:
            return None

    return scope or "all", show_full



def _run_git_capture(args: list[str], workspace: str | None) -> str:
    """Run a git command and return captured standard output.

    Parameters
    ----------
    args : list[str]
        Git arguments excluding the ``git`` executable itself.
    workspace : str or ``None``
        Working directory for the command.

    Returns
    -------
    str
        Captured standard output with trailing whitespace removed.
    """
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=workspace,
        timeout=10,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        if not message:
            message = "git command failed."
        raise RuntimeError(message)
    return result.stdout.strip()



def _preview_patch(
    diff_text: str,
    max_lines: int = _DIFF_PREVIEW_LINE_LIMIT,
) -> tuple[str, bool]:
    """Return a truncated patch preview when needed.

    Parameters
    ----------
    diff_text : str
        Full unified diff text.
    max_lines : int, optional
        Maximum number of lines to include in the preview.

    Returns
    -------
    tuple[str, bool]
        Preview text and whether the patch was truncated.
    """
    lines = diff_text.splitlines()
    if len(lines) <= max_lines:
        return diff_text, False
    return "\n".join(lines[:max_lines]), True



async def _handle_diff_command(
    cmd_arg: str | None,
    *,
    console: Any,
    workspace: str | None,
) -> None:
    """Show git changes with a patch preview.

    Parameters
    ----------
    cmd_arg : str or ``None``
        Optional command argument.
    console : Any
        Rich console for status rendering.
    workspace : str or ``None``
        Workspace directory used for git commands.

    Returns
    -------
    None
        This coroutine does not return a value.
    """
    if not console:
        return

    parsed = _parse_diff_args(cmd_arg)
    if parsed is None:
        console.print(
            "  [orx.status]Usage: /diff [staged|unstaged] [full][/orx.status]"
        )
        return

    scope, show_full = parsed
    sections: list[tuple[str, list[str]]] = []
    if scope in {"all", "unstaged"}:
        sections.append(("Unstaged changes", ["diff"]))
    if scope in {"all", "staged"}:
        sections.append(("Staged changes", ["diff", "--cached"]))

    try:
        rendered_sections: list[tuple[str, str, str]] = []
        for label, base_args in sections:
            stat = _run_git_capture([*base_args, "--stat"], workspace)
            patch = _run_git_capture(base_args, workspace)
            if not patch:
                continue
            rendered_sections.append((label, stat, patch))

        if not rendered_sections:
            console.print("  [orx.status]No uncommitted changes.[/orx.status]")
            return

        from rich.syntax import Syntax

        for index, (label, stat, patch) in enumerate(rendered_sections):
            if index:
                console.print()
            console.print(f"  [orx.status]{label}:[/orx.status]")
            if stat:
                console.print(_indent(stat, 2))
            if show_full:
                patch_text, truncated = patch, False
            else:
                patch_text, truncated = _preview_patch(patch)
            console.print(
                "  [orx.status]Patch:[/orx.status]"
                if show_full
                else "  [orx.status]Patch preview:[/orx.status]"
            )
            console.print(
                Syntax(
                    patch_text,
                    "diff",
                    theme="monokai",
                    line_numbers=False,
                )
            )
            if truncated:
                console.print(
                    "  [orx.status]Preview truncated. "
                    "Use /diff full for the full patch.[/orx.status]"
                )
    except FileNotFoundError:
        console.print("  [orx.status]git not found.[/orx.status]")
    except subprocess.TimeoutExpired:
        console.print("  [orx.status]git diff timed out.[/orx.status]")
    except RuntimeError as exc:
        console.print(f"  [orx.error]Error: {exc}[/orx.error]")



def _register_extra_commands() -> None:
    """Register auxiliary slash commands.

    Returns
    -------
    None
        This function does not return a value.
    """
    # Cumulative session token tracking.
    _session_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "turns": 0,
    }

    def track_usage(prompt_tokens: int, completion_tokens: int) -> None:
        """Accumulate token usage for the current session.

        Parameters
        ----------
        prompt_tokens : int
            Tokens consumed by the prompt.
        completion_tokens : int
            Tokens generated by the model.

        Returns
        -------
        None
            This function does not return a value.
        """
        _session_usage["prompt_tokens"] += prompt_tokens
        _session_usage["completion_tokens"] += completion_tokens
        _session_usage["turns"] += 1

    # Expose tracker so the REPL can call it.
    _register_extra_commands.track_usage = track_usage  # type: ignore[attr-defined]

    async def _cmd_cost(state: Any, cmd_arg: str | None, **kw: Any) -> None:
        """Show cumulative token usage for the session.

        Parameters
        ----------
        state : Any
            REPL command state.
        cmd_arg : str or ``None``, optional
            Optional command argument.
        **kw : Any
            Additional command context.

        Returns
        -------
        None
            This command does not return a value.
        """
        console = kw.get("console")
        if not console:
            return
        p = _session_usage["prompt_tokens"]
        c = _session_usage["completion_tokens"]
        total = p + c
        turns = _session_usage["turns"]
        console.print(f"  [orx.status]Session token usage ({turns} turns):[/orx.status]")
        console.print(f"  [orx.status]  Input:  {p:,} tokens[/orx.status]")
        console.print(f"  [orx.status]  Output: {c:,} tokens[/orx.status]")
        console.print(f"  [orx.status]  Total:  {total:,} tokens[/orx.status]")

    register_command("/cost", _cmd_cost)
    register_command("/usage", _cmd_cost)

    async def _cmd_diff(state: Any, cmd_arg: str | None, **kw: Any) -> None:
        """Show git changes with a patch preview.

        Parameters
        ----------
        state : Any
            REPL command state.
        cmd_arg : str or ``None``, optional
            Optional command argument.
        **kw : Any
            Additional command context.

        Returns
        -------
        None
            This command does not return a value.
        """
        await _handle_diff_command(
            cmd_arg,
            console=kw.get("console"),
            workspace=kw.get("workspace"),
        )

    register_command("/diff", _cmd_diff)

    async def _cmd_help(state: Any, cmd_arg: str | None, **kw: Any) -> None:
        """Display available slash commands and input tips.

        Parameters
        ----------
        state : Any
            REPL command state.
        cmd_arg : str or ``None``, optional
            Optional command argument.
        **kw : Any
            Additional command context.

        Returns
        -------
        None
            This command does not return a value.
        """
        console = kw.get("console")
        if not console:
            return
        console.print("""\
[orx.status]Commands:[/orx.status]
  /model <name>      Switch model
  /effort <level>    Switch effort (low, medium, high)
  /permissions <mode> Switch permission mode (default, plan, accept-edits, auto-approve, trust)
  /perm cycle         Cycle to next permission mode
  /cost               Show session token usage
  /diff [scope] [full] Show git changes with previews (/diff staged, /diff full)
  /clear              Clear session
  /compact            Compact context (auto-triggers at 80K chars)
  /todos              Show tasks
  /session            Session info
  /undo               Remove last turn
  /retry              Re-run last message
  /copy               Copy last response
  /memory             List saved memories
  /theme              Switch theme (dark/light)
  /exit               Exit

[orx.status]Multi-line input:[/orx.status]
  Start with \"\"\" or \'\'\' and end with same.
""")

    register_command("/help", _cmd_help)


def _inject_permission_callback(
    agent: Any, perm_state: PermissionState, usage_tracker: Any = None,
) -> None:
    """Inject permission and usage callbacks into an agent tree.

    Parameters
    ----------
    agent : Any
        Root agent to update.
    perm_state : PermissionState
        Mutable permission state shared with callbacks.
    usage_tracker : Any, optional
        Callable used to record token usage.

    Returns
    -------
    None
        This function does not return a value.
    """
    from orxhestra_code.permissions import _DESTRUCTIVE_TOOLS, _NETWORK_TOOLS

    callback = make_before_tool_callback(perm_state)
    if hasattr(agent, "_callbacks"):
        agent._callbacks.before_tool = callback
        # Wire up usage tracking via after_model callback.
        if usage_tracker is not None:
            async def _after_model(ctx: Any, response: Any) -> None:
                """Record model token usage after a response.

                Parameters
                ----------
                ctx : Any
                    Callback context from the runtime.
                response : Any
                    Model response object.

                Returns
                -------
                None
                    This callback does not return a value.
                """
                input_t = getattr(response, "input_tokens", 0) or 0
                output_t = getattr(response, "output_tokens", 0) or 0
                if input_t or output_t:
                    usage_tracker(input_t, output_t)
            agent._callbacks.after_model = _after_model
    # Mark prompting tools with require_confirmation so the spinner is
    # suppressed while the approval prompt is active.
    if hasattr(agent, "_tools"):
        for name, tool in agent._tools.items():
            if name in _DESTRUCTIVE_TOOLS or name in _NETWORK_TOOLS:
                object.__setattr__(tool, "require_confirmation", True)
    for child in getattr(agent, "sub_agents", []):
        _inject_permission_callback(child, perm_state)


async def _resolve_session_id(state: Any, resume_arg: str) -> str | None:
    """Resolve a concrete session ID from a resume argument.

    Parameters
    ----------
    state : Any
        REPL state containing the session service.
    resume_arg : str
        Requested resume target, including ``"latest"``.

    Returns
    -------
    str or ``None``
        Resolved session ID when one is available.
    """
    if resume_arg != "latest":
        return resume_arg

    # Try to list sessions from the runner's session service.
    svc = state.runner._session_service
    if hasattr(svc, "list_sessions"):
        sessions = await svc.list_sessions(app_name="orx-coder")
        if sessions:
            # Sort by most recent event timestamp.
            sessions.sort(key=lambda s: s.last_update_time or 0, reverse=True)
            return sessions[0].id
    return None


def _inject_plan_tools(agent: Any, perm_state: PermissionState) -> None:
    """Add the plan-mode tools to the root agent.

    Parameters
    ----------
    agent : Any
        Agent to update.
    perm_state : PermissionState
        Mutable permission state shared with the plan tools.

    Returns
    -------
    None
        This function does not return a value.
    """
    if hasattr(agent, "_tools"):
        for tool in make_plan_mode_tools(perm_state):
            agent._tools[tool.name] = tool


def _inject_web_tools(agent: Any) -> None:
    """Add the web tools to the root agent.

    Parameters
    ----------
    agent : Any
        Agent to update.

    Returns
    -------
    None
        This function does not return a value.
    """
    if hasattr(agent, "_tools"):
        for tool in make_web_tools():
            agent._tools[tool.name] = tool


def _indent(text: str, spaces: int) -> str:
    """Indent each line of text by a fixed number of spaces.

    Parameters
    ----------
    text : str
        Text to indent.
    spaces : int
        Number of leading spaces to add to each line.

    Returns
    -------
    str
        Indented text.
    """
    prefix: str = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


async def _async_main() -> None:
    """Run the asynchronous CLI entry flow.

    Returns
    -------
    None
        This coroutine does not return a value.
    """
    cfg: CoderConfig = load_config()

    logging.basicConfig(level=logging.WARNING)

    workspace: Path = cfg.workspace.resolve()
    os.chdir(workspace)

    # Set workspace env var for orxhestra shell/filesystem tools.
    os.environ.setdefault("AGENT_WORKSPACE", str(workspace))

    # First-run API key check.
    _check_api_key(cfg)

    runtime_ctx = RuntimeContext(
        cfg=cfg,
        workspace=workspace,
        orx_path=_build_orx_yaml(cfg, workspace),
    )

    state = await build_state(
        runtime_ctx.orx_path,
        cfg.model_name,
        str(workspace),
    )

    # Handle session resume.
    if cfg.resume_session:
        resumed_id = await _resolve_session_id(state, cfg.resume_session)
        if resumed_id:
            state.session_id = resumed_id
        else:
            target = cfg.resume_session
            if target == "latest":
                print("  No previous session found. Starting fresh.")
            else:
                print(f"  Session '{target}' not found. Starting fresh.")

    # Create mutable permission state, inject callback, register commands.
    perm_state = PermissionState(cfg.permission_mode)
    _register_extra_commands()
    usage_tracker = getattr(_register_extra_commands, "track_usage", None)
    _inject_plan_tools(state.runner.agent, perm_state)
    _inject_web_tools(state.runner.agent)
    _inject_permission_callback(state.runner.agent, perm_state, usage_tracker)
    _register_permission_commands(perm_state)

    # Register /effort with closures over runtime_ctx, perm_state, usage_tracker.
    async def _cmd_effort_live(st: Any, cmd_arg: str | None, **kw: Any) -> None:
        await _handle_effort_command(
            st, cmd_arg,
            console=kw.get("console"),
            runtime_ctx=runtime_ctx,
            perm_state=perm_state,
            usage_tracker=usage_tracker,
        )

    register_command("/effort", _cmd_effort_live)

    # Let the SDK handle approval prompts via writer.prompt_input()
    # which routes to pyink's approval selector UI.
    state.auto_approve = perm_state.mode in ("auto-approve", "trust")

    # Check for single-shot command via pipe or -c flag.
    if not sys.stdin.isatty():
        command: str = sys.stdin.read().strip()
        if command:
            await _run_single(state, command)
            return None

    # Return state so main() can launch the pyink app outside asyncio.
    return runtime_ctx, state


async def _run_single(state: Any, command: str) -> None:
    """Run a single command and exit."""
    try:
        from rich.markdown import Markdown
    except ImportError:
        print("Error: rich is required. Install with: pip install orxhestra[cli]")
        sys.exit(1)

    from orxhestra.cli.writer import ConsoleWriter

    console = make_console()
    writer = ConsoleWriter(console)
    await stream_response(
        state.runner,
        state.session_id,
        command,
        writer,
        Markdown,
        todo_list=state.todo_list,
        auto_approve=getattr(state, "auto_approve", False),
    )


async def _repl(
    runtime_ctx: RuntimeContext,
    state: Any,
    auto_approve: bool = True,
    perm_state: PermissionState | None = None,
    usage_tracker: Any = None,
) -> None:
    """Run the interactive REPL loop.

    Parameters
    ----------
    runtime_ctx : RuntimeContext
        Mutable runtime context for the current REPL session.
    state : Any
        REPL state containing the runner and session state.
    auto_approve : bool, optional
        Whether tool execution should auto-approve prompts.
    perm_state : PermissionState or ``None``, optional
        Mutable permission state displayed in the prompt.
    usage_tracker : Any, optional
        Token usage callback preserved across runtime rebuilds.

    Returns
    -------
    None
        This coroutine does not return a value.
    """
    try:
        from rich.markdown import Markdown
    except ImportError:
        print("Error: rich is required. Install with: pip install orxhestra[cli]")
        sys.exit(1)

    from orxhestra_code import __version__ as code_version

    console = make_console()

    print_banner(
        runtime_ctx.orx_path,
        state.model_name,
        str(runtime_ctx.workspace),
        console,
    )
    console.print(
        f"  [orx.status]orx-coder v{code_version} · "
        f"type /help for commands, Ctrl+D to exit[/orx.status]\n"
    )

    prompt_session: Any = None
    ANSI_cls: Any = None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import ANSI

        ANSI_cls = ANSI
        from prompt_toolkit.history import FileHistory

        completer = WordCompleter(get_command_names(), sentence=True)

        history_dir: Path = Path.home() / ".orx-coder"
        history_dir.mkdir(parents=True, exist_ok=True)
        prompt_session = PromptSession(
            history=FileHistory(str(history_dir / "history")),
            completer=completer,
        )
    except ImportError:
        pass

    def _make_prompt() -> Any:
        """Build the interactive prompt string.

        Returns
        -------
        Any
            Prompt text or formatted prompt object.
        """
        mode = perm_state.mode if perm_state else "default"
        mode_tag = "" if mode == "default" else f" ({mode})"
        if ANSI_cls:
            return ANSI_cls(
                f"\033[38;5;208morx-coder{mode_tag}\033[0m\033[90m>\033[0m "
            )
        return f"orx-coder{mode_tag}> "

    while True:
        try:
            if prompt_session:
                user_input: str = await prompt_session.prompt_async(
                    _make_prompt(),
                )
            else:
                user_input = input(_make_prompt())
        except (EOFError, KeyboardInterrupt):
            console.print("\n[orx.status]Goodbye![/orx.status]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Multiline input: start with """ or ''' and collect until closing.
        if user_input.startswith('"""') or user_input.startswith("'''"):
            delimiter = user_input[:3]
            lines = [user_input[3:]]
            while True:
                try:
                    if prompt_session:
                        line = await prompt_session.prompt_async("... ")
                    else:
                        line = input("... ")
                except (EOFError, KeyboardInterrupt):
                    break
                if line.rstrip().endswith(delimiter):
                    lines.append(line.rstrip()[: -len(delimiter)])
                    break
                lines.append(line)
            user_input = "\n".join(lines).strip()
            if not user_input:
                continue

        if user_input.startswith("/"):
            cmd_parts: list[str] = user_input.split(maxsplit=1)
            cmd_arg: str | None = (
                cmd_parts[1].strip() if len(cmd_parts) > 1 else None
            )
            await handle_slash_command(
                cmd_parts[0].lower(),
                cmd_arg,
                state,
                console=console,
                orx_path=runtime_ctx.orx_path,
                workspace=str(runtime_ctx.workspace),
            )
            # auto_approve stays True — our before_tool callback handles it.
            if not state.should_continue:
                break
            if state.retry_message:
                user_input = state.retry_message
                state.retry_message = None
            else:
                continue

        auto_approve = await stream_response(
            state.runner,
            state.session_id,
            user_input,
            console,
            Markdown,
            todo_list=state.todo_list,
            auto_approve=auto_approve,
        )
        state.turn_count += 1
        console.print()


def main() -> None:
    """Run the top-level CLI entry point."""
    try:
        result = asyncio.run(_async_main())
    except KeyboardInterrupt:
        return

    if result is not None:
        runtime_ctx, state = result
        from orxhestra.cli.ink_app import run_ink_app

        console = make_console()
        try:
            run_ink_app(state, console, runtime_ctx.orx_path, str(runtime_ctx.workspace))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
