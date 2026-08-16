#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile


CLAIMED_AT = "2026-07-27T01:10:22.676483Z"
RATE = 2.4597222
EXPECTED = {
    "owner": "77a3d87ce87771730eaa7dcd8f4b45771fb5122090f93fcc14ba9863d44af1b8",
    "scorer": "9bb9b28cc7b25d30d7ee884685660005cae71fe552aa7938d7f53cb568d0235a",
    "capture": "ce7095836aea47701fc34ebacb2f0754c9066066062500a05fbd6136c59b4d54",
    "weight": "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def stamp() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args()
    root = args.artifact
    attempt = root / "attempt-1.EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json"
    terminal = json.loads(attempt.read_text())
    markers = {
        "science_started": root / "attempt-1.science_started.json",
        "dense_first_call": root / "attempt-1.arm-markers-dense_first_call.json",
        "candidate_first_call": root / "attempt-1.arm-markers-candidate_first_call.json",
    }
    if not (
        terminal.get("classification") == "exact_block_bound_vocab_head_terminal"
        and terminal.get("execution", {}).get("cuda") is True
        and terminal.get("execution", {}).get("submission_count") == 1
        and terminal.get("complete_output_consumption", {}).get("top1_rows_consumed") == 1536
        and all(terminal.get("source_hashes", {}).get(k) == v for k, v in EXPECTED.items())
        and json.loads(markers["science_started"].read_text()).get("science_started") is True
        and all(json.loads(markers[k].read_text()).get("complete") is True for k in ("dense_first_call", "candidate_first_call"))
    ):
        raise SystemExit("attempt_1_contract_invalid")
    stdout = root / "attempt-1.worker.stdout"
    if digest(stdout) != "ceb5a2515ca52b28a741f7f24fa18d57bd2df501fa1b48ecffca7cd56565683d":
        raise SystemExit("attempt_1_stdout_hash_invalid")
    now = stamp()
    claimed = dt.datetime.fromisoformat(CLAIMED_AT.replace("Z", "+00:00"))
    seconds = (now - claimed).total_seconds()
    spend = seconds * RATE / 3600
    terminal.setdefault("spend", {}).update({
        "claim_started_at_utc": CLAIMED_AT,
        "claim_seconds_at_terminal_adoption": seconds,
        "actual_spend_usd_at_terminal_adoption": spend,
        "checkpoint_bytes_transferred": 0,
    })
    atomic(root / "EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json", terminal)
    recovered = {name: {"path": str(path), "sha256": digest(path)} for name, path in {"terminal": attempt, "worker_stdout": stdout, **markers}.items()}
    repair = {
        "schema_version": 1,
        "classification": "post_science_permission_recovery_terminal_adopted",
        "attempt_generation": 1,
        "worker_exit": 0,
        "claimed_at_utc": CLAIMED_AT,
        "adopted_at_utc": now.isoformat().replace("+00:00", "Z"),
        "claim_seconds_at_adoption": seconds,
        "actual_spend_usd_at_adoption": spend,
        "remote_mutation": "chmod only the four existing attempt-1 terminal/marker files and traversal directories for retrieval",
        "science_replayed": False,
        "validated_contract": True,
        "canonical_terminal_sha256": digest(root / "EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json"),
        "retrieved": recovered,
    }
    atomic(root / "REPAIR_TERMINAL.json", repair)
    print(json.dumps({"canonical": repair["canonical_terminal_sha256"], "repair": digest(root / "REPAIR_TERMINAL.json"), "spend": spend}, sort_keys=True))


if __name__ == "__main__":
    main()
