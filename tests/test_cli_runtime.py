from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import rich.syntax

from orxhestra_code import config as config_module
from orxhestra_code import main as main_module
from orxhestra_code.config import CoderConfig, load_config
from orxhestra_code.main import RuntimeContext, _handle_diff_command, _handle_effort_command
from orxhestra_code.permissions import PermissionState


class _FakeWriter:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print_rich(self, message: str = "", *_args: object, **_kwargs: object) -> None:
        self.messages.append(message)


def test_permission_mode_cli_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "_load_yaml_config", lambda: {})
    monkeypatch.setenv("ORX_PERMISSION_MODE", "trust")

    cfg = load_config(["--permission-mode", "plan"])

    assert cfg.permission_mode == "plan"


def test_permission_mode_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_module,
        "_load_yaml_config",
        lambda: {"permission_mode": "accept-edits"},
    )
    monkeypatch.setenv("ORX_PERMISSION_MODE", "trust")

    cfg = load_config([])

    assert cfg.permission_mode == "trust"


@pytest.mark.asyncio
async def test_effort_command_shows_current_effort(tmp_path: Path) -> None:
    writer = _FakeWriter()
    runtime_ctx = RuntimeContext(
        cfg=CoderConfig(effort="medium"),
        workspace=tmp_path,
        orx_path=tmp_path / "orx.yaml",
    )

    await _handle_effort_command(
        SimpleNamespace(model_name="claude-sonnet-4-6"),
        None,
        writer=writer,
        runtime_ctx=runtime_ctx,
        perm_state=PermissionState("default"),
    )

    assert writer.messages == [
        "  [orx.status]Current effort: medium[/orx.status]",
        "  [orx.status]Usage: /effort <low|medium|high>[/orx.status]",
    ]


@pytest.mark.asyncio
async def test_effort_command_rebuilds_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    writer = _FakeWriter()
    state = SimpleNamespace(
        model_name="claude-sonnet-4-6",
        runner=SimpleNamespace(agent=object()),
    )
    runtime_ctx = RuntimeContext(
        cfg=CoderConfig(model="anthropic/claude-sonnet-4-6", effort="low"),
        workspace=tmp_path,
        orx_path=tmp_path / "old.yaml",
    )
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        main_module,
        "_build_orx_yaml",
        lambda cfg, workspace: workspace / f"{cfg.effort}.yaml",
    )

    async def _fake_rebuild(
        current_state: object,
        orx_path: Path,
        model_name: str,
        workspace: str,
    ) -> None:
        calls["rebuild"] = (current_state, orx_path, model_name, workspace)

    monkeypatch.setattr(main_module, "rebuild_state", _fake_rebuild)
    monkeypatch.setattr(
        main_module,
        "_inject_plan_tools",
        lambda *args: calls.setdefault("plan", True),
    )
    monkeypatch.setattr(
        main_module,
        "_inject_web_tools",
        lambda *args: calls.setdefault("web", True),
    )
    monkeypatch.setattr(
        main_module,
        "_inject_permission_callback",
        lambda *args: calls.setdefault("permissions", True),
    )

    await _handle_effort_command(
        state,
        "high",
        writer=writer,
        runtime_ctx=runtime_ctx,
        perm_state=PermissionState("default"),
        usage_tracker=object(),
    )

    assert runtime_ctx.cfg.effort == "high"
    assert runtime_ctx.orx_path == tmp_path / "high.yaml"
    assert calls["rebuild"] == (
        state,
        tmp_path / "high.yaml",
        "claude-sonnet-4-6",
        str(tmp_path),
    )
    assert calls["plan"] is True
    assert calls["web"] is True
    assert calls["permissions"] is True
    assert writer.messages[-1] == "  [orx.status]Effort: high[/orx.status]"


@pytest.mark.asyncio
async def test_diff_command_shows_no_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    writer = _FakeWriter()

    monkeypatch.setattr(main_module, "_run_git_capture", lambda *_args, **_kwargs: "")

    await _handle_diff_command(None, writer=writer, workspace="/tmp")

    assert writer.messages == [
        "  [orx.status]No uncommitted changes.[/orx.status]"
    ]


@pytest.mark.asyncio
async def test_diff_command_shows_preview_and_truncation_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _FakeWriter()
    patch = "\n".join(
        f"line {index}"
        for index in range(1, main_module._DIFF_PREVIEW_LINE_LIMIT + 2)
    )

    def _fake_run_git_capture(args: list[str], workspace: str | None) -> str:
        assert workspace == "/tmp"
        responses = {
            (
                "diff",
                "--stat",
            ): " foo.py | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)",
            ("diff",): patch,
            ("diff", "--cached", "--stat"): "",
            ("diff", "--cached"): "",
        }
        return responses[tuple(args)]

    monkeypatch.setattr(main_module, "_run_git_capture", _fake_run_git_capture)
    monkeypatch.setattr(
        rich.syntax,
        "Syntax",
        lambda text, *_args, **_kwargs: text,
    )

    await _handle_diff_command(None, writer=writer, workspace="/tmp")

    preview = next(
        message for message in writer.messages if message.startswith("line 1")
    )
    assert "  [orx.status]Unstaged changes:[/orx.status]" in writer.messages
    assert "  [orx.status]Patch preview:[/orx.status]" in writer.messages
    assert (
        "  [orx.status]Preview truncated. "
        "Use /diff full for the full patch.[/orx.status]"
        in writer.messages
    )
    assert f"line {main_module._DIFF_PREVIEW_LINE_LIMIT}" in preview
    assert f"line {main_module._DIFF_PREVIEW_LINE_LIMIT + 1}" not in preview


@pytest.mark.asyncio
async def test_diff_command_supports_staged_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _FakeWriter()
    calls: list[tuple[str, ...]] = []

    def _fake_run_git_capture(args: list[str], workspace: str | None) -> str:
        assert workspace == "/tmp"
        key = tuple(args)
        calls.append(key)
        responses = {
            ("diff", "--cached", "--stat"): " foo.py | 1 +",
            ("diff", "--cached"): "full patch\nline 2",
        }
        return responses[key]

    monkeypatch.setattr(main_module, "_run_git_capture", _fake_run_git_capture)
    monkeypatch.setattr(
        rich.syntax,
        "Syntax",
        lambda text, *_args, **_kwargs: text,
    )

    await _handle_diff_command("staged full", writer=writer, workspace="/tmp")

    assert calls == [("diff", "--cached", "--stat"), ("diff", "--cached")]
    assert "  [orx.status]Staged changes:[/orx.status]" in writer.messages
    assert "  [orx.status]Patch:[/orx.status]" in writer.messages
    assert "full patch\nline 2" in writer.messages
    assert not any("Preview truncated" in message for message in writer.messages)
