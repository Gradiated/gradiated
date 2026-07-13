#!/usr/bin/env python3
"""Atomically claim and release repository-local task packets."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "tasks" / "inbox"
ACTIVE = ROOT / "tasks" / "active"
DONE = ROOT / "tasks" / "done"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def packet_id(value: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise SystemExit("task id must contain only letters, numbers, '.', '_' or '-'")
    return value


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def lock_path(task_id: str) -> Path:
    return ACTIVE / f"{task_id}.lock"


def packet_path(task_id: str) -> Path:
    return ACTIVE / f"{task_id}.md"


def default_packet(args: argparse.Namespace) -> str:
    return f"""# Task: {args.task_id}

## Outcome

<What will be true when this is done?>

## Owner and coordination

- GitHub issue: {args.issue or ''}
- GitHub project:
- owner: {args.owner}
- Codex thread:
- created: {now()}
- started: {now()}
- last updated: {now()}
- scope: {args.scope}
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value:
- acceptance checks:
- quality gate:
- SLO or budget:
- timeout:
- artifact locations:
- resume command:
- rollback or cleanup:

## Plan

1.
2.
3.

## Result

- status: active
- verification:
- changed paths:
- limitations or blocked paths:
- commit:
- next action:
"""


def start(args: argparse.Namespace) -> int:
    task_id = packet_id(args.task_id)
    ACTIVE.mkdir(parents=True, exist_ok=True)
    lock = lock_path(task_id)
    try:
        lock.mkdir()
    except FileExistsError:
        metadata = lock / "claim.json"
        print(f"already claimed: {task_id}")
        if metadata.exists():
            print(metadata.read_text())
        return 2

    try:
        metadata = {
            "task_id": task_id,
            "owner": args.owner,
            "issue": args.issue,
            "scope": args.scope,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "claimed_at": now(),
        }
        (lock / "claim.json").write_text(json.dumps(metadata, indent=2) + "\n")
        packet = packet_path(task_id)
        inbox_packet = INBOX / f"{task_id}.md"
        if not packet.exists() and inbox_packet.exists():
            shutil.move(inbox_packet, packet)
        if not packet.exists():
            packet.write_text(default_packet(args))
    except Exception:
        shutil.rmtree(lock, ignore_errors=True)
        raise

    print(f"claimed: {task_id}")
    print(f"packet: {packet_path(task_id).relative_to(ROOT)}")
    print(f"lock: {lock.relative_to(ROOT)}")
    return 0


def release(args: argparse.Namespace) -> int:
    task_id = packet_id(args.task_id)
    lock = lock_path(task_id)
    packet = packet_path(task_id)
    if not lock.exists():
        raise SystemExit(f"no active claim for {task_id}")
    if packet.exists():
        text = packet.read_text()
        text = re.sub(r"- status: (?:inbox|active|blocked|done)", f"- status: {args.status}", text, count=1)
        text = text.rstrip() + f"\n- released: {now()}\n"
        packet.write_text(text)
        if args.status == "done":
            DONE.mkdir(parents=True, exist_ok=True)
            shutil.move(packet, DONE / packet.name)
    shutil.rmtree(lock)
    print(f"released: {task_id} ({args.status})")
    return 0


def status(_: argparse.Namespace) -> int:
    locks = sorted(ACTIVE.glob("*.lock"))
    if not locks:
        print("no active local claims")
        return 0
    for lock in locks:
        metadata = lock / "claim.json"
        print(metadata.read_text().rstrip() if metadata.exists() else str(lock))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start_parser = sub.add_parser("start", help="atomically claim or create a task packet")
    start_parser.add_argument("task_id")
    start_parser.add_argument("--issue")
    start_parser.add_argument("--owner", default=os.environ.get("CODEX_AGENT_ID", getpass.getuser()))
    start_parser.add_argument("--scope", required=True)
    start_parser.set_defaults(func=start)

    release_parser = sub.add_parser("release", help="release a local claim")
    release_parser.add_argument("task_id")
    release_parser.add_argument("--status", choices=("blocked", "done"), default="done")
    release_parser.set_defaults(func=release)

    status_parser = sub.add_parser("status", help="list local claims")
    status_parser.set_defaults(func=status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
