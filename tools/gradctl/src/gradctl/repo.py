"""Find the Gradiated checkout for commands that work on the repository."""

from __future__ import annotations

import os
from pathlib import Path

from .core import CliError


def is_root(path: Path) -> bool:
    return (path / 'AGENTS.md').is_file() and (path / 'tools' / 'gradctl').is_dir()


def find_root(start: Path | None = None) -> Path:
    """GRADCTL_REPO if set, otherwise the nearest checkout at or above the working directory."""
    configured = os.environ.get('GRADCTL_REPO')
    if configured:
        path = Path(configured).expanduser().resolve()
        if not is_root(path):
            raise CliError(f'GRADCTL_REPO={configured} is not a Gradiated checkout', 'repo_required',
                           'point GRADCTL_REPO at the repository root, or unset it', 4)
        return path
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if is_root(candidate):
            return candidate
    raise CliError('this command needs a Gradiated checkout', 'repo_required',
                   'run it inside the repository, or set GRADCTL_REPO to its root', 4)
