from pathlib import Path
from typing import Any
import os

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache",  ".venv", "venv", ".mypy_cache", ".ruff_cache", ".npm", "node_modules"}

WORKSPACE_PATH = "/"
WORKSPACE = Path(WORKSPACE_PATH)

def safe_path(relative_path: str) -> Path:
    """
    Resolve a user-provided path inside WORKSPACE.
    Prevents paths such as ../../etc/passwd.
    """
    path = (WORKSPACE / relative_path).resolve()

    if path != WORKSPACE and WORKSPACE not in path.parents:
        raise ValueError(f"Path escapes workspace: {relative_path}")

    return path

def list_files(
    purpose: str, 
    path: str = ".",
    glob_filter_to: str = "*",
    exclude: set[str] | None = None,
    limit: int = 300,
) -> str:
    """List files and directories in the current project workspace.
    only returns the top limit entries, glob_filter_to or exclude to focus if required
    glob_filter_to is a glob string pattern
    exclude is a string set of directories
    glob_filter docs: https://docs.python.org/3/library/glob.html#glob.glob
     """
    exclude = EXCLUDED_DIRS | (exclude or set())
    target_path = safe_path(path)

    entries = []
    truncated = False

    for candidate in target_path.rglob(glob_filter_to):
        relative = candidate.relative_to(WORKSPACE)

        if any(part in exclude for part in relative.parts):
            continue

        if len(entries) == limit:
            truncated = True
            break

        suffix = "/" if candidate.is_dir() else ""
        entries.append(f"{relative}{suffix}")

    if truncated:
        entries.append(
            f"truncated: showing {limit} entries; more results exist. "
            "Use a narrower glob_filter_to or exclude directories by name."
        )

    return "\n".join(entries) if entries else "(workspace is empty)"
    
    
print(list_files("for fun and profit", path=".", glob_filter_to="*", exclude={"boot", "EFI", "dev", "proc", "etc"}))
