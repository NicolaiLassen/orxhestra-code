"""Tests for the permission mode system."""

from __future__ import annotations

from orxhestra_code.permissions import PermissionState, check_permission

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
