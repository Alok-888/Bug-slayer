"""
Bug Slayer - File safety helpers

Repositories are untrusted. A repository can contain symbolic links, for
example `setup.sh -> /Users/you/.zshrc`. Writing "into the repository" through
such a link would overwrite a file on the user's computer, outside the sandbox.

Every file Bug Slayer writes into, or reads from, a repository goes through
these helpers:
  * writes are refused if the path is a symbolic link or ends up outside the
    repository folder;
  * reads are limited to regular files inside the repository (so a link to
    /dev/zero or to a private file is skipped) and to a sane size.
"""

import os
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]

MAX_READ_BYTES = 2 * 1024 * 1024  # READMEs and manifests are far smaller than 2 MB


class UnsafePathError(Exception):
    """Raised when a write would leave the repository or follow a symbolic link."""


def is_inside(path: PathLike, root: PathLike) -> bool:
    """True if `path` (after resolving every link) is inside `root`."""
    try:
        real = os.path.realpath(path)
        base = os.path.realpath(root)
        return os.path.commonpath([real, base]) == base
    except ValueError:  # different drives on Windows
        return False


def check_writable(path: PathLike, root: Optional[PathLike] = None) -> Path:
    """
    Returns the path if it is safe to write, otherwise raises UnsafePathError.
    Safe means: not a symbolic link, and (when `root` is given) inside `root`.
    """
    p = Path(path)
    if p.is_symlink():
        raise UnsafePathError(f"refusing to write through a symbolic link: {p.name}")
    if root is not None and not is_inside(p.parent, root):
        raise UnsafePathError(f"refusing to write outside the repository: {p}")
    return p


def safe_write_text(path: PathLike, content: str, root: Optional[PathLike] = None,
                    newline: Optional[str] = None) -> None:
    """write_text that never follows a symbolic link and never leaves `root`."""
    p = check_writable(path, root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(p), flags, 0o644)
    with open(fd, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)


def is_safe_to_read(path: PathLike, root: Optional[PathLike] = None) -> bool:
    """A regular file (not a device or a link out of the repository), not too big."""
    p = Path(path)
    try:
        if root is not None and not is_inside(p, root):
            return False
        if not p.is_file():
            return False
        return p.stat().st_size <= MAX_READ_BYTES
    except OSError:
        return False


def safe_read_text(path: PathLike, root: Optional[PathLike] = None) -> str:
    """read_text for repository files; returns "" for anything unsafe to read."""
    if not is_safe_to_read(path, root):
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
