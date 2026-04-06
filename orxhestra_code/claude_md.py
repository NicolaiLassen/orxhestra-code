"""Load project instructions from CLAUDE.md files.

Walks from the workspace directory up to the filesystem root,
collecting any ``CLAUDE.md`` or ``.orx/instructions.md`` files.
Closest files (deepest in the tree) take highest priority and
appear first in the output.
"""

from __future__ import annotations

from pathlib import Path

_INSTRUCTION_FILES: list[str] = [
    "CLAUDE.md",
    ".orx/instructions.md",
    ".orx/CLAUDE.md",
]


def load_project_instructions(workspace: Path) -> str:
    """Collect project instruction files from *workspace* up to root.

    Parameters
    ----------
    workspace : Path
        The project root directory to start searching from.

    Returns
    -------
    str
        Concatenated instructions, closest files first.
        Empty string if no instruction files are found.
    """
    sections: list[str] = []
    current: Path = workspace.resolve()

    visited: set[Path] = set()
    while current not in visited:
        visited.add(current)
        for filename in _INSTRUCTION_FILES:
            candidate: Path = current / filename
            if candidate.is_file():
                try:
                    content: str = candidate.read_text().strip()
                    if content:
                        sections.append(
                            f"# Project instructions ({candidate})\n\n{content}"
                        )
                except OSError:
                    continue
        parent: Path = current.parent
        if parent == current:
            break
        current = parent

    return "\n\n".join(sections)
