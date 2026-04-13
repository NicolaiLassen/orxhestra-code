"""Load project instructions from ``CLAUDE.md`` files.

Walks from the workspace directory up to the filesystem root, collecting
project and user instruction files, resolving ``@path`` imports, and
truncating oversized content.
"""

from __future__ import annotations

import re
from pathlib import Path

# Maximum total characters for all instruction content combined.
_MAX_TOTAL_CHARS: int = 100_000
# Maximum single file size before truncation.
_MAX_FILE_CHARS: int = 50_000
# Maximum import depth to prevent circular references.
_MAX_IMPORT_DEPTH: int = 5

# Files to look for at each directory level (project scope).
_PROJECT_FILES: list[str] = [
    "CLAUDE.md",
    "CLAUDE.local.md",
    ".orx/instructions.md",
    ".orx/CLAUDE.md",
    ".claude/CLAUDE.md",
]

# User-level instruction files (loaded last, lowest priority).
_USER_FILES: list[Path] = [
    Path.home() / ".claude" / "CLAUDE.md",
    Path.home() / ".orx-coder" / "CLAUDE.md",
]


def _resolve_imports(
    content: str,
    base_dir: Path,
    visited: set[Path],
    depth: int = 0,
) -> str:
    """Resolve ``@path/to/file`` directives within instruction content.

    Parameters
    ----------
    content : str
        Instruction file content to process.
    base_dir : Path
        Base directory used to resolve relative import paths.
    visited : set[Path]
        Already visited files used to avoid cycles.
    depth : int, optional
        Current import depth.

    Returns
    -------
    str
        Content with supported imports expanded.
    """
    if depth >= _MAX_IMPORT_DEPTH:
        return content

    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("@") and not stripped.startswith("@@"):
            import_path = base_dir / stripped[1:].strip()
            resolved = import_path.resolve()
            if resolved in visited or not resolved.is_file():
                lines.append(line)
                continue
            visited.add(resolved)
            try:
                imported = resolved.read_text()
                if len(imported) > _MAX_FILE_CHARS:
                    imported = imported[:_MAX_FILE_CHARS] + (
                        f"\n\n[TRUNCATED — file exceeds {_MAX_FILE_CHARS} chars]"
                    )
                imported = _resolve_imports(
                    imported, resolved.parent, visited, depth + 1,
                )
                lines.append(imported)
            except OSError:
                lines.append(line)
        else:
            lines.append(line)
    return "\n".join(lines)


def _strip_html_comments(text: str) -> str:
    """Remove HTML comments from instruction content.

    Parameters
    ----------
    text : str
        Instruction text to clean.

    Returns
    -------
    str
        Text with HTML comments removed.
    """
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _read_instruction_file(
    path: Path,
    visited_imports: set[Path],
) -> str | None:
    """Read and preprocess one instruction file.

    Parameters
    ----------
    path : Path
        Instruction file path.
    visited_imports : set[Path]
        Visited import targets used to avoid cycles.

    Returns
    -------
    str or ``None``
        Processed instruction content, if available.
    """
    if not path.is_file():
        return None
    try:
        content = path.read_text().strip()
    except OSError:
        return None
    if not content:
        return None

    # Truncate oversized files.
    if len(content) > _MAX_FILE_CHARS:
        content = content[:_MAX_FILE_CHARS] + (
            f"\n\n[TRUNCATED — file exceeds {_MAX_FILE_CHARS} chars]"
        )

    # Resolve @import directives.
    visited_imports.add(path.resolve())
    content = _resolve_imports(content, path.parent, visited_imports)

    # Strip HTML comments.
    content = _strip_html_comments(content)

    return content.strip()


def load_project_instructions(workspace: Path) -> str:
    """Collect instruction text for a workspace.

    Parameters
    ----------
    workspace : Path
        Workspace directory to search from.

    Returns
    -------
    str
        Concatenated instruction text.
    """
    sections: list[str] = []
    visited_dirs: set[Path] = set()
    visited_imports: set[Path] = set()
    total_chars = 0

    # Walk from workspace up to root.
    current: Path = workspace.resolve()
    while current not in visited_dirs:
        visited_dirs.add(current)
        for filename in _PROJECT_FILES:
            candidate: Path = current / filename
            content = _read_instruction_file(candidate, visited_imports)
            if content:
                sections.append(
                    f"# Project instructions ({candidate})\n\n{content}"
                )
                total_chars += len(content)
                if total_chars >= _MAX_TOTAL_CHARS:
                    sections.append(
                        f"\n[TRUNCATED — total instructions exceed "
                        f"{_MAX_TOTAL_CHARS} chars]"
                    )
                    return "\n\n".join(sections)
        parent: Path = current.parent
        if parent == current:
            break
        current = parent

    # User-level instructions (lowest priority).
    for user_file in _USER_FILES:
        content = _read_instruction_file(user_file, visited_imports)
        if content:
            sections.append(
                f"# User instructions ({user_file})\n\n{content}"
            )
            total_chars += len(content)
            if total_chars >= _MAX_TOTAL_CHARS:
                break

    return "\n\n".join(sections)
