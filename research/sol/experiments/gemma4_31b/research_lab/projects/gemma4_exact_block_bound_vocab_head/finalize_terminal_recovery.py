#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import tempfile


CLAIMED_AT = "2026-07-27T01:10:22.676483Z"
RELEASED_AT = "2026-07-27T01:20:18.549926Z"
CLAIM_SECONDS = 595.873443
ACTUAL_SPEND = 0.407134204483


def digest(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    project = args.project
    artifact = project / "artifacts/h200-exact-block-bound-20260727t0100z"
    canonical = artifact / "EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json"
    terminal = json.loads(canonical.read_text())
    terminal["spend"].update({
        "claim_released_at_utc": RELEASED_AT,
        "claim_seconds": CLAIM_SECONDS,
        "actual_spend_usd": ACTUAL_SPEND,
    })
    write(canonical, terminal)
    repair_path = artifact / "REPAIR_TERMINAL.json"
    repair = json.loads(repair_path.read_text())
    repair.update({
        "claim_released_at_utc": RELEASED_AT,
        "claim_seconds": CLAIM_SECONDS,
        "actual_spend_usd": ACTUAL_SPEND,
        "release_condition": "ready",
        "owner_terminated": {"pid": 2236177, "start_ticks": 123063995},
        "canonical_terminal_sha256": digest(canonical),
    })
    write(repair_path, repair)
    status_path = project / "STATUS.json"
    status = json.loads(status_path.read_text())
    status.update({
        "status": "closed",
        "active_session": None,
        "actual_spend_usd": ACTUAL_SPEND,
        "decision": "close_exact_block_bound_mechanism",
        "result": "attempt_1_terminal_recovered_and_valid_negative",
        "summary": "The one consumed exact block-bound component invocation was recovered without replay after a post-science permission defect. It certified skipped blocks but failed exact top-1 identity and was 9.943840 ms versus 0.860144 ms dense; close this mechanism.",
        "next_action": "No further work in this mechanism; retain the recovered terminal as a typed negative.",
        "scientific_sample_consumed": True,
        "terminal_artifact": "artifacts/h200-exact-block-bound-20260727t0100z/EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json",
        "terminal_sha256": digest(canonical),
        "repair_terminal_artifact": "artifacts/h200-exact-block-bound-20260727t0100z/REPAIR_TERMINAL.json",
        "repair_terminal_sha256": digest(repair_path),
        "closed_at": RELEASED_AT,
        "claim_accounting": {
            "bench_id": "h200-causal-head-e00b9qw8d6qd7wrjj1",
            "claimed_at_utc": CLAIMED_AT,
            "released_at_utc": RELEASED_AT,
            "claim_seconds": CLAIM_SECONDS,
            "hourly_cost_usd": 2.4597222,
            "actual_spend_usd": ACTUAL_SPEND,
            "checkpoint_bytes_transferred": 0,
        },
    })
    write(status_path, status)
    print(json.dumps({"terminal_sha256": digest(canonical), "repair_sha256": digest(repair_path), "status_sha256": digest(status_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
