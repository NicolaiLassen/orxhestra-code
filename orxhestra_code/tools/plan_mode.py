"""EnterPlanMode / ExitPlanMode tools for plan-then-execute workflow.

The agent calls ``enter_plan_mode`` when it decides a task is non-trivial.
This switches permissions to read-only so the agent can explore the
codebase and design a plan.  When ready, it calls ``exit_plan_mode``
with the plan text.  The user is prompted to approve, reject, or edit
the plan before the agent proceeds to implement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

if TYPE_CHECKING:
    from orxhestra_code.permissions import PermissionState


def make_plan_mode_tools(
    perm_state: PermissionState,
) -> list[StructuredTool]:
    """Create the enter/exit plan mode tool pair.

    Parameters
    ----------
    perm_state : PermissionState
        Mutable permission state shared with the before_tool callback.

    Returns
    -------
    list[StructuredTool]
        Two tools: ``enter_plan_mode`` and ``exit_plan_mode``.
    """
    _previous_mode: dict[str, str] = {}

    def enter_plan_mode() -> str:
        """Enter plan mode for read-only codebase exploration.

        Call this BEFORE starting any non-trivial implementation task.
        In plan mode you can read files, search, and analyze, but you
        cannot write, edit, or run shell commands.  Use this to explore
        the codebase and design your approach before writing code.

        After exploring, call exit_plan_mode with your implementation
        plan to get user approval before proceeding.
        """
        _previous_mode["saved"] = perm_state.mode
        perm_state.mode = "plan"
        return (
            "Plan mode activated. You are now in READ-ONLY mode.\n"
            "You can: read files, glob, grep, list directories, analyze code.\n"
            "You CANNOT: write files, edit files, run shell commands.\n\n"
            "Explore the codebase, then call exit_plan_mode with your plan."
        )

    def exit_plan_mode(plan: str) -> str:
        """Exit plan mode and present the implementation plan for user approval.

        Parameters
        ----------
        plan : str
            Your implementation plan in markdown format.  Include:
            - What files you'll create or modify
            - Key changes in each file
            - Testing approach
            - Any risks or concerns
        """
        import sys

        # Clear spinner line and show plan.
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        print(f"\n{'=' * 60}")
        print("IMPLEMENTATION PLAN")
        print(f"{'=' * 60}")
        print(plan)
        print(f"{'=' * 60}")

        try:
            answer = input("\n  ? Approve this plan? [y/n/e(dit)] > ").strip().lower()
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
