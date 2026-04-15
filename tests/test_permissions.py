"""Tests for the permission mode system."""

from __future__ import annotations

import asyncio
import threading

import pytest

from orxhestra_code.permissions import (
    PermissionState,
    check_permission,
    make_before_tool_callback,
)

# ── Default mode ─────────────────────────────────────────────────


def test_default_reads_allowed() -> None:
    assert check_permission("default", "read_file", {}) == "allow"
    assert check_permission("default", "ls", {}) == "allow"
    assert check_permission("default", "glob", {}) == "allow"


def test_default_writes_ask() -> None:
    assert check_permission("default", "write_file", {}) == "ask"
    assert check_permission("default", "edit_file", {}) == "ask"
    assert check_permission("default", "shell_exec", {}) == "ask"


def test_default_web_ask() -> None:
    assert check_permission("default", "web_search", {}) == "ask"
    assert check_permission("default", "web_fetch", {}) == "ask"


# ── Plan mode ────────────────────────────────────────────────────


def test_plan_reads_allowed() -> None:
    assert check_permission("plan", "read_file", {}) == "allow"
    assert check_permission("plan", "glob", {}) == "allow"
    assert check_permission("plan", "grep", {}) == "allow"


def test_plan_writes_denied() -> None:
    assert check_permission("plan", "write_file", {}) == "deny"
    assert check_permission("plan", "edit_file", {}) == "deny"
    assert check_permission("plan", "shell_exec", {}) == "deny"
    assert check_permission("plan", "mkdir", {}) == "deny"


def test_plan_web_denied() -> None:
    assert check_permission("plan", "web_search", {}) == "deny"
    assert check_permission("plan", "web_fetch", {}) == "deny"


# ── Accept-edits mode ───────────────────────────────────────────


def test_accept_edits_writes_allowed() -> None:
    assert check_permission("accept-edits", "write_file", {}) == "allow"
    assert check_permission("accept-edits", "edit_file", {}) == "allow"
    assert check_permission("accept-edits", "mkdir", {}) == "allow"
    assert check_permission("accept-edits", "read_file", {}) == "allow"


def test_accept_edits_shell_ask() -> None:
    assert check_permission("accept-edits", "shell_exec", {}) == "ask"


def test_accept_edits_web_ask() -> None:
    assert check_permission("accept-edits", "web_search", {}) == "ask"
    assert check_permission("accept-edits", "web_fetch", {}) == "ask"


# ── Auto-approve / trust ────────────────────────────────────────


def test_auto_approve_all_allowed() -> None:
    assert check_permission("auto-approve", "shell_exec", {}) == "allow"
    assert check_permission("auto-approve", "write_file", {}) == "allow"
    assert check_permission("auto-approve", "web_search", {}) == "allow"
    assert check_permission("auto-approve", "read_file", {}) == "allow"


def test_trust_all_allowed() -> None:
    assert check_permission("trust", "shell_exec", {}) == "allow"
    assert check_permission("trust", "write_file", {}) == "allow"
    assert check_permission("trust", "web_search", {}) == "allow"


# ── State cycling ────────────────────────────────────────────────


def test_permission_state_cycle() -> None:
    ps = PermissionState("default")
    assert ps.cycle() == "plan"
    assert ps.cycle() == "accept-edits"
    assert ps.cycle() == "auto-approve"
    assert ps.cycle() == "trust"
    assert ps.cycle() == "default"


# ── Concurrent approval serialization ──────────────────────────


@pytest.mark.asyncio
async def test_concurrent_approvals_are_serialized() -> None:
    """Multiple concurrent tool calls needing approval must be serialized."""
    call_log: list[str] = []
    active = threading.Event()

    def fake_approval(label: str) -> str:
        """Simulates a blocking approval that takes time."""
        assert not active.is_set(), "Two approvals running concurrently!"
        active.set()
        call_log.append(f"start:{label}")
        # Simulate user thinking time.
        import time
        time.sleep(0.05)
        call_log.append(f"end:{label}")
        active.clear()
        return "y"

    perm_state = PermissionState("default")
    before_tool = make_before_tool_callback(perm_state, approval_fn=fake_approval)

    # Fire 3 concurrent web_search approvals.
    await asyncio.gather(
        before_tool(None, "web_search", {"query": "a"}),
        before_tool(None, "web_search", {"query": "b"}),
        before_tool(None, "web_search", {"query": "c"}),
    )

    # All 3 should have completed (no deadlock).
    assert len(call_log) == 6
    # Each start must be followed by its end before the next start.
    starts = [i for i, e in enumerate(call_log) if e.startswith("start:")]
    ends = [i for i, e in enumerate(call_log) if e.startswith("end:")]
    for s, e in zip(starts, ends):
        assert s < e, "start must come before end"


@pytest.mark.asyncio
async def test_approval_allow_all_upgrades_mode() -> None:
    """Selecting 'allow all' should upgrade to auto-approve."""
    def fake_approval(label: str) -> str:
        return "a"

    perm_state = PermissionState("default")
    before_tool = make_before_tool_callback(perm_state, approval_fn=fake_approval)

    await before_tool(None, "web_search", {"query": "test"})
    assert perm_state.mode == "auto-approve"
