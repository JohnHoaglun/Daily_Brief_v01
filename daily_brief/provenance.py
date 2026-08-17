"""Resolve Git provenance metadata from the current repository."""

import subprocess
from typing import Optional


def _git_format(repo_path: str, fmt: str) -> Optional[str]:
    """Run a single `git log -1 --format=<fmt>` and return stripped output."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=" + fmt],
            shell=False,
            timeout=5,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        output = result.stdout.decode("utf-8", errors="replace").strip()
        return output if output else None
    except (FileNotFoundError, NotADirectoryError):
        return None
    except Exception:
        return None


def resolve_git_commit_sha(repo_path: str = ".") -> Optional[str]:
    """Return the short commit SHA, or None on failure."""
    return _git_format(repo_path, "%h")


def resolve_git_committed_at(repo_path: str = ".") -> Optional[str]:
    """Return the ISO 8601 committed date, or None on failure."""
    return _git_format(repo_path, "%cI")


def resolve_git_author_name(repo_path: str = ".") -> Optional[str]:
    """Return the author name, or None on failure."""
    return _git_format(repo_path, "%an")


def resolve_git_committer_name(repo_path: str = ".") -> Optional[str]:
    """Return the committer name, or None on failure."""
    return _git_format(repo_path, "%cn")
