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
from orxhestra_code.prompt import SYSTEM_PROMPT


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

    instructions: str = SYSTEM_PROMPT
    if project_instructions:
        instructions = f"{SYSTEM_PROMPT}\n\n{project_instructions}"

    # Escape for YAML multiline block scalar.
    escaped: str = instructions.replace("\\", "\\\\")

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
      - todos
      - task
      - human_input

main_agent: coder

runner:
  app_name: orx-coder
  session_service: memory
  artifact_service: memory
"""
    tmp = Path(tempfile.mkdtemp()) / "orx-coder.yaml"
    tmp.write_text(yaml_content)
    return tmp


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

    orx_path: Path = _build_orx_yaml(cfg, workspace)

    # Reuse the orxhestra CLI builder and REPL.
    from orxhestra.cli.builder import build_from_orx
    from orxhestra.cli.state import ReplState

    state: ReplState = await build_from_orx(
        orx_path, cfg.model_name, str(workspace),
    )

    # Check for single-shot command via pipe or -c flag.
    if not sys.stdin.isatty():
        command: str = sys.stdin.read().strip()
        if command:
            await _run_single(state, command, workspace)
            return

    await _repl(orx_path, state, workspace)


async def _run_single(state: Any, command: str, workspace: Path) -> None:
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
        auto_approve=False,
    )


async def _repl(orx_path: Path, state: Any, workspace: Path) -> None:
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

    console = make_console()

    print_banner(orx_path, state.model_name, str(workspace), console)
    console.print(
        "  [orx.status]type /help for commands, Ctrl+D to exit[/orx.status]\n"
    )

    prompt_session: Any = None
    prompt_style: Any = None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import ANSI
        from prompt_toolkit.history import FileHistory

        history_dir: Path = Path.home() / ".orx-coder"
        history_dir.mkdir(parents=True, exist_ok=True)
        prompt_session = PromptSession(
            history=FileHistory(str(history_dir / "history")),
        )
        prompt_style = ANSI("\033[38;5;208morx-coder\033[0m\033[90m>\033[0m ")
    except ImportError:
        pass

    auto_approve: bool = False

    while True:
        try:
            if prompt_session:
                user_input: str = await prompt_session.prompt_async(
                    prompt_style or "orx-coder> ",
                )
            else:
                user_input = input("orx-coder> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[orx.status]Goodbye![/orx.status]")
            break

        user_input = user_input.strip()
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
