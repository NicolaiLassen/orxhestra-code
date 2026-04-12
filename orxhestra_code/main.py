"""CLI entry point for orx-coder.

Builds a coding-focused LlmAgent with filesystem, shell, memory,
and todo tools, then launches the orxhestra interactive REPL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

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


def _check_api_key(cfg: CoderConfig) -> None:
    """Check if the required API key is set for the configured provider."""
    env_var = _PROVIDER_ENV_VARS.get(cfg.provider)
    if env_var and not os.environ.get(env_var):
        # Don't fail for local providers.
        if cfg.provider in ("ollama",):
            return
        print(f"\n  Missing {env_var}.")
        print(f"  Set it with: export {env_var}=your-key-here\n")
        sys.exit(1)


def _build_permission_section(mode: str) -> str:
    """Build the permission mode section for the system prompt.

    This tells the LLM what it can and cannot do under the current
    permission mode, so it doesn't attempt denied operations.
    """
    sections: dict[str, str] = {
        "default": """\
# Permission mode: default

Tools are executed in the **default** permission mode. Destructive tools \
(file writes, edits, shell commands, directory creation) require user \
approval before execution. Read-only tools (file reads, search, glob) are \
auto-approved. If the user denies a tool call, do not re-attempt the exact \
same call. Instead, think about why it was denied and adjust your approach.""",

        "plan": """\
# Permission mode: plan (read-only)

You are in **plan mode** — a read-only analysis mode. You can ONLY:
- Read files, search with glob/grep, list directories
- Think, analyze, and explain code
- Create task lists and plans

You CANNOT and MUST NOT attempt to:
- Write or edit any files
- Run shell commands
- Create directories
- Make any changes to the codebase

If the user asks you to make changes, explain what you WOULD do and \
present a plan, but do not execute it. Suggest the user switch to a \
different permission mode when ready to implement.""",

        "accept-edits": """\
# Permission mode: accept-edits

File operations (write, edit, mkdir) are **auto-approved** — you can \
freely create and modify files without prompting. Shell commands still \
require user approval. Read-only tools are auto-approved. Use this mode \
for focused coding tasks where file changes are expected.""",

        "auto-approve": """\
# Permission mode: auto-approve

All tool calls are **auto-approved** — no prompts will be shown. You can \
freely read, write, edit files and run shell commands. Exercise extra \
caution with destructive operations since the user will not be prompted \
to confirm. Prefer safe, reversible actions.""",

        "trust": """\
# Permission mode: trust

All tool calls are **auto-approved** with no warnings. Full autonomous \
operation. Exercise maximum caution with destructive operations — there \
is no safety net. Only use destructive git operations or file deletions \
when you are absolutely certain they are correct.""",
    }
    return sections.get(mode, sections["default"])


def _build_env_section(cfg: CoderConfig, workspace: Path) -> str:
    """Build a dynamic environment info section (mirrors Claude Code's computeSimpleEnvInfo)."""
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

    return f"""\
# Environment

- Working directory: {workspace}
- Is a git repository: {"yes" if is_git else "no"}{git_info}
- Platform: {platform.system().lower()}
- Shell: {shell}
- OS: {os_version}
- Model: {cfg.model}
- Effort: {cfg.effort}
- Available tools: {', '.join(tools_available) if tools_available else 'unknown'}"""


def _build_orx_yaml(cfg: CoderConfig, workspace: Path) -> Path:
    """Generate a temporary orx.yaml for the coding agent.

    Parameters
    ----------
    cfg : CoderConfig
        Resolved configuration.
    workspace : Path
        The project workspace directory.

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
  coder:
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

main_agent: coder

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
    """Register /permissions, /perm, /mode slash commands via orxhestra's API."""
    from orxhestra.cli.commands import register_command

    async def _cmd_permissions(state: Any, cmd_arg: str | None, **kw: Any) -> None:
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


def _register_extra_commands() -> None:
    """Register /cost and /diff commands."""
    from orxhestra.cli.commands import register_command

    # Cumulative session token tracking.
    _session_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "turns": 0,
    }

    def track_usage(prompt_tokens: int, completion_tokens: int) -> None:
        """Called after each turn to accumulate usage."""
        _session_usage["prompt_tokens"] += prompt_tokens
        _session_usage["completion_tokens"] += completion_tokens
        _session_usage["turns"] += 1

    # Expose tracker so the REPL can call it.
    _register_extra_commands.track_usage = track_usage  # type: ignore[attr-defined]

    async def _cmd_cost(state: Any, cmd_arg: str | None, **kw: Any) -> None:
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
        console = kw.get("console")
        if not console:
            return
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, timeout=10,
            )
            stat = result.stdout.strip()
            if not stat:
                console.print("  [orx.status]No uncommitted changes.[/orx.status]")
                return
            console.print("  [orx.status]Uncommitted changes:[/orx.status]")
            console.print(f"  {stat}")

            # Show full diff if --full or -f is passed.
            if cmd_arg in ("--full", "-f", "full"):
                full = subprocess.run(
                    ["git", "diff"],
                    capture_output=True, text=True, timeout=10,
                )
                if full.stdout.strip():
                    from rich.syntax import Syntax

                    syntax = Syntax(
                        full.stdout, "diff", theme="monokai", line_numbers=False,
                    )
                    console.print(syntax)
        except FileNotFoundError:
            console.print("  [orx.status]git not found.[/orx.status]")
        except subprocess.TimeoutExpired:
            console.print("  [orx.status]git diff timed out.[/orx.status]")

    register_command("/diff", _cmd_diff)

    async def _cmd_help(state: Any, cmd_arg: str | None, **kw: Any) -> None:
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
  /diff               Show uncommitted git changes (/diff full for syntax-highlighted diff)
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
  Start with \\"\\"\\" or \\'\\'\\' and end with same.
""")

    register_command("/help", _cmd_help)

    async def _cmd_effort(state: Any, cmd_arg: str | None, **kw: Any) -> None:
        console = kw.get("console")
        if not console:
            return
        from orxhestra_code.config import EFFORT_PRESETS

        if cmd_arg and cmd_arg in EFFORT_PRESETS:
            preset = EFFORT_PRESETS[cmd_arg]
            state.runner.agent.max_iterations = preset["max_iterations"]
            console.print(
                f"  [orx.status]Effort: {cmd_arg} "
                f"(max {preset['max_iterations']} iterations)[/orx.status]"
            )
        else:
            current_iter = getattr(state.runner.agent, "max_iterations", "?")
            console.print(
                f"  [orx.status]Current max iterations: {current_iter}[/orx.status]"
            )
            console.print(
                "  [orx.status]Usage: /effort low|medium|high[/orx.status]"
            )

    register_command("/effort", _cmd_effort)


def _inject_permission_callback(
    agent: Any, perm_state: PermissionState, usage_tracker: Any = None,
) -> None:
    """Walk the agent tree and inject callbacks for permissions and usage tracking."""
    from orxhestra_code.permissions import _DESTRUCTIVE_TOOLS

    callback = make_before_tool_callback(perm_state)
    if hasattr(agent, "_callbacks"):
        agent._callbacks.before_tool = callback
        # Wire up usage tracking via after_model callback.
        if usage_tracker is not None:
            async def _after_model(ctx: Any, response: Any) -> None:
                input_t = getattr(response, "input_tokens", 0) or 0
                output_t = getattr(response, "output_tokens", 0) or 0
                if input_t or output_t:
                    usage_tracker(input_t, output_t)
            agent._callbacks.after_model = _after_model
    # Mark destructive tools with require_confirmation so the spinner
    # is suppressed while the approval prompt is active.
    if hasattr(agent, "_tools"):
        for name, tool in agent._tools.items():
            if name in _DESTRUCTIVE_TOOLS:
                object.__setattr__(tool, "require_confirmation", True)
    for child in getattr(agent, "sub_agents", []):
        _inject_permission_callback(child, perm_state)


async def _resolve_session_id(state: Any, resume_arg: str) -> str | None:
    """Resolve a session ID from a resume argument.

    If ``resume_arg`` is ``"latest"``, finds the most recent session
    from the session service.  Otherwise treats it as a literal session ID.
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
    """Add enter/exit plan mode tools to the root agent."""
    if hasattr(agent, "_tools"):
        for tool in make_plan_mode_tools(perm_state):
            agent._tools[tool.name] = tool


def _indent(text: str, spaces: int) -> str:
    """Indent every line of *text* by *spaces* spaces."""
    prefix: str = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


async def _async_main() -> None:
    """Async entry point."""
    cfg: CoderConfig = load_config()

    logging.basicConfig(level=logging.WARNING)

    workspace: Path = cfg.workspace.resolve()
    os.chdir(workspace)

    # Set workspace env var for orxhestra shell/filesystem tools.
    os.environ.setdefault("AGENT_WORKSPACE", str(workspace))

    # First-run API key check.
    _check_api_key(cfg)

    orx_path: Path = _build_orx_yaml(cfg, workspace)

    # Reuse the orxhestra CLI builder and REPL.
    from orxhestra.cli.builder import build_from_orx
    from orxhestra.cli.state import ReplState

    state: ReplState = await build_from_orx(
        orx_path, cfg.model_name, str(workspace),
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
    _inject_permission_callback(state.runner.agent, perm_state, usage_tracker)
    _inject_plan_tools(state.runner.agent, perm_state)
    _register_permission_commands(perm_state)

    # Always tell orxhestra's CLI to auto_approve — our before_tool callback
    # handles all approval logic. This prevents two competing prompts.
    auto_approve: bool = True

    # Check for single-shot command via pipe or -c flag.
    if not sys.stdin.isatty():
        command: str = sys.stdin.read().strip()
        if command:
            await _run_single(state, command, workspace, auto_approve)
            return

    await _repl(orx_path, state, workspace, auto_approve, perm_state)


async def _run_single(
    state: Any, command: str, workspace: Path, auto_approve: bool = False,
) -> None:
    """Run a single command and exit."""
    try:
        from rich.markdown import Markdown
    except ImportError:
        print("Error: rich is required. Install with: pip install orxhestra[cli]")
        sys.exit(1)

    from orxhestra.cli.stream import stream_response
    from orxhestra.cli.theme import make_console

    console = make_console()
    await stream_response(
        state.runner,
        state.session_id,
        command,
        console,
        Markdown,
        todo_list=state.todo_list,
        auto_approve=auto_approve,
    )


async def _repl(
    orx_path: Path,
    state: Any,
    workspace: Path,
    auto_approve: bool = True,
    perm_state: PermissionState | None = None,
) -> None:
    """Run the interactive REPL."""
    try:
        from rich.markdown import Markdown
    except ImportError:
        print("Error: rich is required. Install with: pip install orxhestra[cli]")
        sys.exit(1)

    from orxhestra.cli.commands import handle_slash_command
    from orxhestra.cli.render import print_banner
    from orxhestra.cli.stream import stream_response
    from orxhestra.cli.theme import make_console

    from orxhestra_code import __version__ as code_version

    console = make_console()

    print_banner(orx_path, state.model_name, str(workspace), console)
    console.print(
        f"  [orx.status]orx-coder v{code_version} · "
        f"type /help for commands, Ctrl+D to exit[/orx.status]\n"
    )

    prompt_session: Any = None
    ANSI_cls: Any = None
    try:
        from orxhestra.cli.commands import get_command_names
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
        """Build the prompt string with the current permission mode."""
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
                orx_path=orx_path,
                workspace=str(workspace),
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
    """Entry point for the ``orx-coder`` command."""
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
