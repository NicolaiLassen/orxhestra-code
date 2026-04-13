"""Permission modes for tool execution control.

Mirrors Claude Code's multi-mode permission system.  Each mode
defines which tools are auto-approved, which require prompting, and
which are denied outright.

Modes
-----
default
    Prompt for destructive tools (write, edit, shell, mkdir).
    Read-only tools are auto-approved.
plan
    Read-only analysis mode.  All write/edit/shell tools are denied.
    The agent can only read files, search, and think.
accept-edits
    Auto-approve file operations (write, edit, mkdir).
    Shell commands still require approval.
auto-approve
    Auto-approve everything.  No prompts.
trust
    Like auto-approve, but also suppresses dangerous-command warnings.
"""

from __future__ import annotations

from typing import Any

# Tools that modify the filesystem or run commands.
_WRITE_TOOLS: frozenset[str] = frozenset({
    "write_file",
    "edit_file",
    "mkdir",
})

_SHELL_TOOLS: frozenset[str] = frozenset({
    "shell_exec",
    "shell_exec_background",
})

_DESTRUCTIVE_TOOLS: frozenset[str] = _WRITE_TOOLS | _SHELL_TOOLS

# Read-only tools that are always safe.
_READ_TOOLS: frozenset[str] = frozenset({
    "ls",
    "read_file",
    "glob",
    "grep",
    "list_artifacts",
    "load_artifact",
})

# All valid permission mode names.
PERMISSION_MODES: tuple[str, ...] = (
    "default",
    "plan",
    "accept-edits",
    "auto-approve",
    "trust",
)

# Short descriptions for display.
PERMISSION_MODE_LABELS: dict[str, str] = {
    "default": "default (prompt for writes/shell)",
    "plan": "plan (read-only)",
    "accept-edits": "accept-edits (auto-approve edits, prompt shell)",
    "auto-approve": "auto-approve (no prompts)",
    "trust": "trust (no prompts, no warnings)",
}


class PermissionDeniedError(Exception):
    """Raised when a tool call is denied by the permission mode."""


class PermissionState:
    """Mutable permission state that can be changed mid-session.

    The ``before_tool`` callback references this object, so changing
    ``self.mode`` takes effect on the next tool call without needing
    to re-inject the callback.
    """

    def __init__(self, mode: str = "default") -> None:
        self.mode = mode

    def cycle(self) -> str:
        """Cycle to the next permission mode and return it."""
        modes = list(PERMISSION_MODES)
        idx = modes.index(self.mode) if self.mode in modes else 0
        self.mode = modes[(idx + 1) % len(modes)]
        return self.mode


def check_permission(
    mode: str,
    tool_name: str,
    tool_args: dict[str, Any],
) -> str:
    """Check whether a tool call is allowed under the given permission mode.

    Parameters
    ----------
    mode : str
        One of the ``PERMISSION_MODES``.
    tool_name : str
        Name of the tool being called.
    tool_args : dict
        Arguments passed to the tool.

    Returns
    -------
    str
        ``"allow"`` if the call should proceed without prompting,
        ``"ask"`` if the user should be prompted, or
        ``"deny"`` if the call should be blocked.
    """
    if mode == "trust" or mode == "auto-approve":
        return "allow"

    if mode == "plan":
        if tool_name in _DESTRUCTIVE_TOOLS:
            return "deny"
        return "allow"

    if mode == "accept-edits":
        if tool_name in _WRITE_TOOLS:
            return "allow"
        if tool_name in _SHELL_TOOLS:
            return "ask"
        return "allow"

    # default mode
    if tool_name in _DESTRUCTIVE_TOOLS:
        return "ask"
    return "allow"


def _format_tool_summary(tool_name: str, tool_args: dict[str, Any]) -> str:
    """Format a summary of a tool call for the approval prompt."""
    if tool_name == "shell_exec":
        cmd = tool_args.get("command", "")
        return f"shell_exec: {cmd[:120]}" + ("..." if len(cmd) > 120 else "")
    if tool_name == "write_file":
        path = tool_args.get("path", "?")
        content = tool_args.get("content", "")
        lines = content.count("\n") + 1 if content else 0
        return f"write_file: {path} ({lines} lines)"
    if tool_name == "edit_file":
        path = tool_args.get("path", "?")
        old = tool_args.get("old", "")[:80]
        new = tool_args.get("new", "")[:80]
        return (
            f"edit_file: {path}\n"
            f"    - {old}{'...' if len(tool_args.get('old', '')) > 80 else ''}\n"
            f"    + {new}{'...' if len(tool_args.get('new', '')) > 80 else ''}"
        )
    if tool_name == "mkdir":
        return f"mkdir: {tool_args.get('path', '?')}"
    return f"{tool_name}({', '.join(f'{k}={v!r}' for k, v in list(tool_args.items())[:3])})"


def make_before_tool_callback(perm_state: PermissionState):
    """Create a ``before_tool`` callback that enforces the current permission mode.

    The callback reads from ``perm_state.mode`` on every call, so
    changing the mode mid-session takes effect immediately.

    For ``"ask"`` decisions, the user is prompted in the terminal.
    Typing ``n`` denies the call, ``y`` allows it, ``a`` switches
    to auto-approve for the rest of the session.
    """

    async def _before_tool(ctx: Any, tool_name: str, tool_args: dict) -> None:
        decision = check_permission(perm_state.mode, tool_name, tool_args)

        if decision == "deny":
            raise PermissionDeniedError(
                f"Tool '{tool_name}' is not allowed in '{perm_state.mode}' "
                f"permission mode. Switch to a different mode to use this tool."
            )

        if decision == "ask":
            import asyncio

            summary = _format_tool_summary(tool_name, tool_args)
            try:
                answer = (
                    await asyncio.to_thread(
                        input,
                        f"\n  ? Allow: {summary}\n  [y]es / [n]o / approve [a]ll > ",
                    )
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"

            if answer == "a":
                perm_state.mode = "auto-approve"
                return
            if answer not in ("y", "yes"):
                raise PermissionDeniedError(
                    f"User denied '{tool_name}'. The user chose not to allow "
                    f"this operation. Try a different approach or ask the user "
                    f"what they'd like you to do instead."
                )

    return _before_tool
