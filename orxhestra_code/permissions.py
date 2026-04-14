"""Permission modes for tool execution control.

Defines the tool-approval rules used by the coding agent and provides the
callback that enforces those rules at runtime.
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

_NETWORK_TOOLS: frozenset[str] = frozenset({
    "web_search",
    "web_fetch",
})

# Read-only tools that are always safe.
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
    "default": "default (prompt for writes/shell/web)",
    "plan": "plan (read-only)",
    "accept-edits": "accept-edits (auto-approve edits, prompt shell/web)",
    "auto-approve": "auto-approve (no prompts)",
    "trust": "trust (no prompts, no warnings)",
}


class PermissionDeniedError(Exception):
    """Raised when a tool call is denied by the active permission mode."""


class PermissionState:
    """Mutable permission mode state shared across callbacks.

    Parameters
    ----------
    mode : str, optional
        Initial permission mode name.

    Attributes
    ----------
    mode : str
        Current permission mode name.
    """

    def __init__(self, mode: str = "default") -> None:
        """Initialize the permission state.

        Parameters
        ----------
        mode : str, optional
            Initial permission mode name.

        Returns
        -------
        None
            This method does not return a value.
        """
        self.mode = mode

    def cycle(self) -> str:
        """Advance to the next permission mode.

        Returns
        -------
        str
            The newly selected permission mode.
        """
        modes = list(PERMISSION_MODES)
        idx = modes.index(self.mode) if self.mode in modes else 0
        self.mode = modes[(idx + 1) % len(modes)]
        return self.mode


def check_permission(
    mode: str,
    tool_name: str,
    tool_args: dict[str, Any],
) -> str:
    """Determine how a tool call should be handled.

    Parameters
    ----------
    mode : str
        Active permission mode.
    tool_name : str
        Tool name to evaluate.
    tool_args : dict[str, Any]
        Tool arguments provided for the call.

    Returns
    -------
    str
        ``"allow"``, ``"ask"``, or ``"deny"``.
    """
    if mode == "trust" or mode == "auto-approve":
        return "allow"

    if mode == "plan":
        if tool_name in _DESTRUCTIVE_TOOLS or tool_name in _NETWORK_TOOLS:
            return "deny"
        return "allow"

    if mode == "accept-edits":
        if tool_name in _WRITE_TOOLS:
            return "allow"
        if tool_name in _SHELL_TOOLS or tool_name in _NETWORK_TOOLS:
            return "ask"
        return "allow"

    # default mode
    if tool_name in _DESTRUCTIVE_TOOLS or tool_name in _NETWORK_TOOLS:
        return "ask"
    return "allow"


def _format_tool_summary(tool_name: str, tool_args: dict[str, Any]) -> str:
    """Format a short approval prompt summary for a tool call.

    Parameters
    ----------
    tool_name : str
        Tool name being invoked.
    tool_args : dict[str, Any]
        Tool arguments for the invocation.

    Returns
    -------
    str
        Human-readable summary of the tool call.
    """
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
    if tool_name == "web_search":
        query = str(tool_args.get("query", ""))
        return f"web_search: {query[:120]}" + ("..." if len(query) > 120 else "")
    if tool_name == "web_fetch":
        return f"web_fetch: {tool_args.get('url', '?')}"
    return f"{tool_name}({', '.join(f'{k}={v!r}' for k, v in list(tool_args.items())[:3])})"


def make_before_tool_callback(
    perm_state: PermissionState,
    approval_fn: Any = None,
):
    """Create a callback that enforces permission checks before tool calls.

    Parameters
    ----------
    perm_state : PermissionState
        Mutable permission state used at call time.
    approval_fn : callable, optional
        Blocking function ``(label: str) -> str`` that shows an approval
        selector and returns ``"y"``, ``"a"`` (allow all), or ``"n"``.
        When provided, ``"ask"`` decisions are routed through this function
        instead of relying on the SDK's built-in approval flow.

    Returns
    -------
    collections.abc.Callable
        Async callback invoked before each tool execution.
    """

    async def _before_tool(ctx: Any, tool_name: str, tool_args: dict) -> None:
        """Validate and optionally prompt for a tool call.

        Parameters
        ----------
        ctx : Any
            Callback context from the runtime.
        tool_name : str
            Tool name being invoked.
        tool_args : dict
            Tool arguments for the call.
        """
        decision = check_permission(perm_state.mode, tool_name, tool_args)

        if decision == "deny":
            raise PermissionDeniedError(
                f"Tool '{tool_name}' is not allowed in '{perm_state.mode}' "
                f"permission mode. Switch to a different mode to use this tool."
            )

        if decision == "ask" and approval_fn is not None:
            summary = _format_tool_summary(tool_name, tool_args)
            response = approval_fn(summary)
            if response in ("a", "all"):
                # Upgrade to auto-approve for the rest of the session.
                perm_state.mode = "auto-approve"
            elif response not in ("y", "yes"):
                raise PermissionDeniedError(
                    f"Tool '{tool_name}' was denied by the user."
                )

    return _before_tool
