"""Web search and fetch tools for the coding agent.

Provides helpers for open-web search, URL validation, content extraction,
and lightweight relevance ranking for fetched pages.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool

_MAX_FETCH_BYTES = 10_000_000
_MAX_OUTPUT_CHARS = 100_000
_MAX_SEARCH_RESULTS = 10
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "what",
    "when", "where", "which", "with", "why",
}
_USER_AGENT = "orx-coder/0.0"


def _candidate_urls(url: str) -> list[str]:
    """Build candidate URLs for a user-provided URL string.

    Parameters
    ----------
    url : str
        URL text supplied by the caller.

    Returns
    -------
    list[str]
        Candidate URLs to try in order, preferring ``https``.
    """
    raw = url.strip()
    if not raw:
        raise ValueError("URL must not be empty.")

    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only http:// and https:// URLs are supported.")

    if parsed.scheme == "http":
        https_url = parsed._replace(scheme="https").geturl()
        return [https_url, raw]
    return [raw]


def _is_text_content_type(content_type: str) -> bool:
    """Check whether a content type is likely text-based.

    Parameters
    ----------
    content_type : str
        Response content type header value.

    Returns
    -------
    bool
        ``True`` when the content type is treated as text.
    """
    lowered = content_type.lower()
    if not lowered:
        return True
    return (
        lowered.startswith("text/")
        or "html" in lowered
        or "xml" in lowered
        or "json" in lowered
        or "javascript" in lowered
    )


def _extract_title(content: str) -> str | None:
    """Extract the HTML ``<title>`` text from page content.

    Parameters
    ----------
    content : str
        HTML source text.

    Returns
    -------
    str or ``None``
        Extracted title text when present.
    """
    match = re.search(r"<title[^>]*>(.*?)</title>", content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = html.unescape(match.group(1))
    title = re.sub(r"\s+", " ", title).strip()
    return title or None


def _trim_output(text: str, limit: int = _MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    """Trim output text to the configured size limit.

    Parameters
    ----------
    text : str
        Text to trim.
    limit : int, optional
        Maximum number of characters to keep.

    Returns
    -------
    tuple[str, bool]
        Trimmed text and whether truncation occurred.
    """
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip(), True


def _keyword_tokens(text: str) -> list[str]:
    """Extract distinct keyword tokens from free-form text.

    Parameters
    ----------
    text : str
        Source text to tokenize.

    Returns
    -------
    list[str]
        Deduplicated keyword tokens with stop words removed.
    """
    tokens = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9_]{3,}", text.lower()):
        if token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _select_relevant_chunks(markdown: str, prompt: str | None, limit: int = 5) -> str:
    """Select the most relevant markdown chunks for a prompt.

    Parameters
    ----------
    markdown : str
        Extracted markdown content.
    prompt : str or ``None``, optional
        Prompt used to rank relevant chunks.
    limit : int, optional
        Maximum number of chunks to return.

    Returns
    -------
    str
        Relevant content excerpt.
    """
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", markdown) if chunk.strip()]
    if not chunks:
        return ""

    if not prompt or not prompt.strip():
        return "\n\n".join(chunks[:limit])

    keywords = _keyword_tokens(prompt)
    if not keywords:
        return "\n\n".join(chunks[:limit])

    scored: list[tuple[int, int, str]] = []
    for index, chunk in enumerate(chunks):
        lowered = chunk.lower()
        score = sum(lowered.count(keyword) for keyword in keywords)
        if score:
            scored.append((score, index, chunk))

    if not scored:
        return "\n\n".join(chunks[:limit])

    scored.sort(key=lambda item: (-item[0], item[1]))
    return "\n\n".join(chunk for _, _, chunk in scored[:limit])


def _format_search_results(query: str, results: list[dict[str, str]]) -> str:
    """Format raw web search results for display.

    Parameters
    ----------
    query : str
        Search query text.
    results : list[dict[str, str]]
        Raw search results from the provider.

    Returns
    -------
    str
        Human-readable search results.
    """
    if not results:
        return f'No web results found for "{query}".'

    lines = [f'Open web results for "{query}":', ""]
    for index, result in enumerate(results, start=1):
        title = (result.get("title") or result.get("name") or "Untitled").strip()
        href = (result.get("href") or result.get("url") or "").strip()
        body = (result.get("body") or result.get("snippet") or "").strip()
        lines.append(f"{index}. {title}")
        if href:
            lines.append(f"   URL: {href}")
        if body:
            lines.append(f"   Snippet: {body}")
        lines.append("")
    return "\n".join(lines).rstrip()


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the open web and format the results.

    Parameters
    ----------
    query : str
        Search query text.
    max_results : int, optional
        Maximum number of results to return.

    Returns
    -------
    str
        Formatted search results.
    """
    import asyncio

    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Query must not be empty.")

    def _do_search() -> list:
        from ddgs import DDGS

        limit = max(1, min(max_results, _MAX_SEARCH_RESULTS))
        return list(DDGS().text(cleaned_query, max_results=limit))

    results = await asyncio.to_thread(_do_search)
    return _format_search_results(cleaned_query, results)


async def web_fetch(url: str, prompt: str | None = None) -> str:
    """Fetch a URL and extract readable text content.

    Parameters
    ----------
    url : str
        URL to fetch.
    prompt : str or ``None``, optional
        Prompt used to rank the most relevant extracted content.

    Returns
    -------
    str
        Fetched content summary or an error message.
    """
    import httpx

    last_error: Exception | None = None
    response: httpx.Response | None = None

    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        for candidate in _candidate_urls(url):
            try:
                response = await client.get(candidate)
                response.raise_for_status()
                break
            except httpx.HTTPError as exc:
                last_error = exc
                response = None

    if response is None:
        message = str(last_error) if last_error else "unknown error"
        return f"Failed to fetch URL: {message}"

    content_type = response.headers.get("content-type", "")
    if not _is_text_content_type(content_type):
        return (
            "Fetched content is binary or unsupported. "
            "Use a direct download tool instead."
        )

    content_length = response.headers.get("content-length")
    try:
        size_hint = int(content_length) if content_length else None
    except ValueError:
        size_hint = None
    if size_hint and size_hint > _MAX_FETCH_BYTES:
        return f"Fetched content exceeds the {_MAX_FETCH_BYTES} byte limit."

    body_bytes = response.content
    if len(body_bytes) > _MAX_FETCH_BYTES:
        return f"Fetched content exceeds the {_MAX_FETCH_BYTES} byte limit."

    import asyncio
    import trafilatura

    text = response.text
    title = _extract_title(text)
    if "html" in content_type.lower() or text.lstrip().startswith("<"):
        extracted = await asyncio.to_thread(
            trafilatura.extract, text, output_format="markdown",
        ) or ""
    else:
        extracted = text

    extracted = extracted.strip()
    if not extracted:
        return f"Fetched {response.url} but could not extract readable text."

    excerpt = _select_relevant_chunks(extracted, prompt)
    excerpt, truncated = _trim_output(excerpt)

    lines = [f"Fetched: {response.url}"]
    if title:
        lines.append(f"Title: {title}")
    if prompt and prompt.strip():
        lines.append("")
        lines.append("Relevant content:")
    else:
        lines.append("")
        lines.append("Extracted content:")
    lines.append(excerpt)
    if truncated:
        lines.append("")
        lines.append(f"[truncated to {_MAX_OUTPUT_CHARS} characters]")
    return "\n".join(lines)


def make_web_tools() -> list[StructuredTool]:
    """Create the structured web tool definitions.

    Returns an empty list when the optional ``web`` dependencies
    (``ddgs``, ``httpx``, ``trafilatura``) are not installed.

    Returns
    -------
    list[StructuredTool]
        Structured search and fetch tools, or ``[]`` if deps missing.
    """
    try:
        import ddgs  # noqa: F401
        import httpx  # noqa: F401
        import trafilatura  # noqa: F401
    except ImportError:
        return []
    search_tool = StructuredTool.from_function(
        coroutine=web_search,
        name="web_search",
        description=(
            "Search the open web without a search API key. "
            "Returns a small set of results with title, URL, and snippet."
        ),
    )
    fetch_tool = StructuredTool.from_function(
        coroutine=web_fetch,
        name="web_fetch",
        description=(
            "Fetch a URL, extract readable page content, and optionally rank "
            "the most relevant sections using a prompt."
        ),
    )
    return [search_tool, fetch_tool]
