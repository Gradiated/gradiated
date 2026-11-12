"""Select workflow subchecks from their declared input paths."""

import json
import os
import sys
from fnmatch import fnmatchcase
from pathlib import Path


def matches(path, patterns):
    """A path matches when a pattern selects it and no `!` pattern excludes it."""
    excluded = any(
        fnmatchcase(path, pattern[1:]) for pattern in patterns if pattern.startswith("!")
    )
    return not excluded and any(
        fnmatchcase(path, pattern) for pattern in patterns if not pattern.startswith("!")
    )


def select(paths, scopes, workflow, force=False):
    common = (workflow, ".github/actions/relevant/*", "mise.toml")
    run_all = force or any(
        fnmatchcase(path, pattern) for path in paths for pattern in common
    )
    return {
        check: run_all or any(matches(path, patterns) for path in paths)
        for check, patterns in scopes.items()
    }


def main():
    scopes = json.loads(Path(sys.argv[1]).read_text())
    force = "--force" in sys.argv[3:]
    paths = [] if force else sys.stdin.read().splitlines()
    result = select(paths, scopes, sys.argv[2], force)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("checks=" + json.dumps(result, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
