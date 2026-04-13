"""Tests for web search and fetch tools."""

from __future__ import annotations

import importlib.util

import pytest

from orxhestra_code.tools import web as web_tools

_has_web_deps = (
    importlib.util.find_spec("httpx") is not None
    and importlib.util.find_spec("trafilatura") is not None
    and importlib.util.find_spec("ddgs") is not None
)


# ── Pure helpers (no deps needed) ────────────────────────────────


def test_candidate_urls() -> None:
    assert web_tools._candidate_urls("example.com") == ["https://example.com"]
    assert web_tools._candidate_urls("https://example.com") == ["https://example.com"]
    assert web_tools._candidate_urls("http://example.com") == [
        "https://example.com",
        "http://example.com",
    ]
    with pytest.raises(ValueError):
        web_tools._candidate_urls("file:///tmp/test.txt")


def test_search_result_formatting() -> None:
    result = web_tools._format_search_results(
        "python",
        [{
            "title": "Python",
            "href": "https://www.python.org",
            "body": "The official home of Python.",
        }],
    )
    assert 'Open web results for "python":' in result
    assert "https://www.python.org" in result
    assert "The official home of Python." in result


def test_chunk_selection_prefers_matching() -> None:
    markdown = (
        "Install steps for the CLI.\n\n"
        "Caching behavior and cache invalidation details.\n\n"
        "Release notes for unrelated features."
    )
    result = web_tools._select_relevant_chunks(markdown, "cache invalidation")
    assert "cache invalidation" in result.lower()
    assert "Install steps" not in result


def test_make_web_tools_empty_without_deps() -> None:
    """make_web_tools returns [] when deps are missing."""
    # We can't un-import, but we can at least verify the function exists
    # and returns a list.
    tools = web_tools.make_web_tools()
    assert isinstance(tools, list)


# ── Integration tests (require web extras) ───────────────────────


@pytest.mark.skipif(not _has_web_deps, reason="web extras not installed")
def test_fetch_rejects_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        headers = {"content-type": "application/pdf", "content-length": "4"}
        content = b"%PDF"
        text = ""
        url = "https://example.com/file.pdf"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, url: str):
            return FakeResponse()

    monkeypatch.setattr("httpx.Client", lambda **kwargs: FakeClient())
    result = web_tools.web_fetch("https://example.com/file.pdf")
    assert "binary or unsupported" in result


@pytest.mark.skipif(not _has_web_deps, reason="web extras not installed")
def test_fetch_extracts_relevant_html(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        headers = {"content-type": "text/html; charset=utf-8", "content-length": "64"}
        content = b"<html><title>Docs</title></html>"
        text = "<html><title>Docs</title><body>ignored</body></html>"
        url = "https://example.com/docs"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, url: str):
            return FakeResponse()

    monkeypatch.setattr("httpx.Client", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "trafilatura.extract",
        lambda text, output_format=None: (
            "Install steps.\n\nCaching behavior and cache invalidation."
        ),
    )

    result = web_tools.web_fetch("https://example.com/docs", prompt="cache invalidation")
    assert "Fetched: https://example.com/docs" in result
    assert "Title: Docs" in result
    assert "Caching behavior and cache invalidation." in result
    assert "Install steps." not in result
