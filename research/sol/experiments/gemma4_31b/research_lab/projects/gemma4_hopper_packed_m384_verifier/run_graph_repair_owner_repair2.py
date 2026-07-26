#!/usr/bin/env python3
"""Repair the pre-submission graph-delta staging parent-directory defect."""

from __future__ import annotations

import pathlib
import shlex

import run_graph_repair_owner as owner


copy = owner.scp_to


def scp_to_with_parent(
    user: str, host: str, source: pathlib.Path, destination: str
):
    parent = pathlib.PurePosixPath(destination).parent.as_posix()
    prepared = owner.ssh(
        user,
        host,
        shlex.join(["mkdir", "-p", parent]),
        timeout=owner.remain(120),
    )
    if prepared.returncode:
        raise RuntimeError(
            f"repair_stage_parent_prepare_failed:{parent}:{prepared.stderr[-1000:]}"
        )
    return copy(user, host, source, destination)


owner.scp_to = scp_to_with_parent

if __name__ == "__main__":
    raise SystemExit(owner.main())
