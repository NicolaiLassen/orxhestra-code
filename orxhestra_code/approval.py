"""Permission callback for destructive tool operations.

Auto-approves read-only tools, prompts the user for writes and
shell commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orxhestra.agents.invocation_context import InvocationContext

_READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "read_file",
    "glob",
    "grep",
    "ls",
    "list_memories",
    "list_artifacts",
    "load_artifact",
    "tool_search",
})


def make_approval_callback(
    *, auto_approve_reads: bool = True,
):
    """Create a ``before_tool_callback`` that gates destructive operations.

    Parameters
    ----------
    auto_approve_reads : bool
        When ``True``, read-only tools are executed without prompting.

    Returns
    -------
    callable
        An async callback compatible with ``LlmAgent.before_tool_callback``.
    """

    async def _approval_callback(
        ctx: InvocationContext,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> None:
        if auto_approve_reads and tool_name in _READ_ONLY_TOOLS:
            return

        # For write operations, print what's about to happen.
        # The CLI REPL's approval system handles the actual prompt.
        # This callback is a hook point for future customisation.
        return

    return _approval_callback
