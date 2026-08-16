from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def read_new_records(inbox: Path, cursor: Path) -> list[dict[str, object]]:
    lines = inbox.read_text(encoding="utf-8").splitlines() if inbox.exists() else []
    try:
        offset = int(cursor.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        offset = 0
    if offset < 0 or offset > len(lines):
        offset = 0
    records = []
    for line in lines[offset:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            records.append(value)
    cursor.write_text(f"{len(lines)}\n", encoding="utf-8")
    return records


def watch(inbox: Path, cursor: Path, heartbeat: Path, poll_seconds: float) -> None:
    while True:
        heartbeat.write_text(f"{time.time():.6f}\n", encoding="utf-8")
        for record in read_new_records(inbox, cursor):
            print(json.dumps(record, sort_keys=True), flush=True)
        time.sleep(poll_seconds)


def main(arguments: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Watch the private Codex dashboard prompt inbox.")
    parser.add_argument("--inbox", type=Path, default=root / "inbox.jsonl")
    parser.add_argument("--cursor", type=Path, default=root / ".monitor-cursor")
    parser.add_argument("--heartbeat", type=Path, default=root / ".monitor-heartbeat")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args(arguments)
    if args.poll_seconds <= 0.0 or args.poll_seconds > 30.0:
        parser.error("--poll-seconds must be in (0, 30]")
    watch(args.inbox, args.cursor, args.heartbeat, args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
