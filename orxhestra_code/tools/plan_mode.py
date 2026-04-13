"""Plan-mode tools for the plan-then-execute workflow.

Provides structured tools that switch the agent into read-only planning
mode and later present the resulting implementation plan for approval.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

if TYPE_CHECKING:
    from orxhestra_code.permissions import PermissionState


def make_plan_mode_tools(
    perm_state: PermissionState,
) -> list[StructuredTool]:
    """Create the plan-mode tool pair.

    Parameters
    ----------
    perm_state : PermissionState
        Mutable permission state shared with the tool callback.

    Returns
    -------
    list[StructuredTool]
        Structured enter-plan and exit-plan tools.
    """
    _previous_mode: dict[str, str] = {}

    def enter_plan_mode() -> str:
        """Switch the agent into read-only plan mode.

        Returns
        -------
        str
            Status message describing the activated mode.
        """
        # Save the mode to restore after plan approval.
        # If already in plan mode, restore to default (not plan again).
        saved = perm_state.mode
        _previous_mode["saved"] = "default" if saved == "plan" else saved
        perm_state.mode = "plan"
        return (
            "Plan mode activated. You are now in READ-ONLY mode.\n"
            "You can: read files, glob, grep, list directories, analyze code.\n"
            "You CANNOT: write files, edit files, run shell commands.\n\n"
            "Explore the codebase, then call exit_plan_mode with your plan."
        )

    def exit_plan_mode(plan: str) -> str:
        """Present a plan and restore the previous mode when approved.

        Parameters
        ----------
        plan : str
            Proposed implementation plan in markdown.

        Returns
        -------
        str
            Approval result and next-step guidance.
        """
        from rich.console import Console
        from rich.markdown import Markdown as RichMarkdown
        from rich.panel import Panel

        console = Console()
        console.print()
        console.print(Panel(
            RichMarkdown(plan),
            title="[bold]Implementation Plan[/bold]",
            border_style="cyan",
            padding=(1, 2),
        ))

        try:
            answer = input(
                "\n  ? Approve this plan? [y]es / [n]o / [e]dit > "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer in ("e", "edit"):
            try:
                feedback = input("  ? What should be changed? > ").strip()
            except (EOFError, KeyboardInterrupt):
                feedback = ""
            # Stay in plan mode so the agent can revise.
            return (
                f"User wants changes to the plan:\n{feedback}\n\n"
                "Revise your plan and call exit_plan_mode again."
            )

        if answer not in ("y", "yes"):
            # Stay in plan mode.
            return (
                "Plan REJECTED by user. Ask the user what approach they'd "
                "prefer, or revise and call exit_plan_mode again."
            )

        # Approved — restore previous permission mode.
        previous = _previous_mode.get("saved", "default")
        perm_state.mode = previous
        return (
            f"Plan APPROVED. Permission mode restored to '{previous}'.\n"
            "Proceed with implementation following the approved plan."
        )

    enter_tool = StructuredTool.from_function(
        func=enter_plan_mode,
        name="enter_plan_mode",
        description=(
            "Enter plan mode for read-only codebase exploration. "
            "Call this BEFORE starting any non-trivial task (3+ files, "
            "architectural decisions, unclear requirements). In plan mode "
            "you can only read — use it to explore and design your approach, "
            "then call exit_plan_mode with your plan for user approval."
        ),
    )
    exit_tool = StructuredTool.from_function(
        func=exit_plan_mode,
        name="exit_plan_mode",
        description=(
            "Exit plan mode and present your implementation plan to the user "
            "for approval. The user can approve, reject, or request changes. "
            "Only call this after you have explored the codebase and designed "
            "a clear implementation plan."
        ),
    )
    # Mark exit_plan_mode as interactive so the spinner doesn't block input().
    object.__setattr__(exit_tool, "interactive", True)
    return [enter_tool, exit_tool]
