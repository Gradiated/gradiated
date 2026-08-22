#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class RowResult:
    accepted_drafts: int
    commit_length: int
    emitted_tokens: tuple[int, ...]
    committed_input_tokens: tuple[int, ...]
    committed_verify_kv_slots: tuple[int, ...]
    freed_verify_kv_slots: tuple[int, ...]
    target_bonus_token: int
    next_pending_token: int
    new_kv_committed_length: int


@dataclass(frozen=True)
class BatchResult:
    batch_size: int
    block_size: int
    target_vocab_size: int
    rows: tuple[RowResult, ...]
    semantic_invariant: str
    kv_invariant: str


def _validate_token(token: Any, vocab_size: int, label: str) -> int:
    if isinstance(token, bool) or not isinstance(token, int):
        raise ContractError(f"{label} must be an integer token id")
    if token < 0 or token >= vocab_size:
        raise ContractError(f"{label}={token} is outside [0,{vocab_size})")
    return token


def _validate_matrix(
    value: Any,
    *,
    label: str,
    vocab_size: int,
    expected_width: int | None = None,
) -> tuple[tuple[int, ...], ...]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{label} must be a nonempty list of rows")
    rows: list[tuple[int, ...]] = []
    width = expected_width
    for row_index, row in enumerate(value):
        if not isinstance(row, list) or not row:
            raise ContractError(f"{label}[{row_index}] must be a nonempty list")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ContractError(
                f"{label}[{row_index}] width={len(row)} does not match {width}"
            )
        rows.append(
            tuple(
                _validate_token(token, vocab_size, f"{label}[{row_index}][{i}]")
                for i, token in enumerate(row)
            )
        )
    return tuple(rows)


def consume_exact_greedy_chain(
    *,
    proposals: Sequence[Sequence[int]],
    target_top1: Sequence[Sequence[int]],
    current_tokens: Sequence[int],
    prefix_kv_lengths: Sequence[int],
    verify_kv_slots: Sequence[Sequence[int]],
    target_vocab_size: int,
    required_block_size: int | None = None,
) -> BatchResult:
    proposal_rows = _validate_matrix(
        [list(row) for row in proposals],
        label="proposals",
        vocab_size=target_vocab_size,
        expected_width=required_block_size,
    )
    block_size = len(proposal_rows[0])
    if block_size < 2:
        raise ContractError("block_size must include current token and a proposal")
    target_rows = _validate_matrix(
        [list(row) for row in target_top1],
        label="target_top1",
        vocab_size=target_vocab_size,
        expected_width=block_size,
    )
    batch_size = len(proposal_rows)
    if len(target_rows) != batch_size:
        raise ContractError("target_top1 batch size does not match proposals")
    if not (
        len(current_tokens)
        == len(prefix_kv_lengths)
        == len(verify_kv_slots)
        == batch_size
    ):
        raise ContractError("per-row metadata batch sizes do not match proposals")

    results: list[RowResult] = []
    for row_index, (proposal, target) in enumerate(zip(proposal_rows, target_rows)):
        current = _validate_token(
            current_tokens[row_index], target_vocab_size, f"current_tokens[{row_index}]"
        )
        if proposal[0] != current:
            raise ContractError(
                f"proposals[{row_index}][0]={proposal[0]} is not current token {current}"
            )
        prefix_len = prefix_kv_lengths[row_index]
        if isinstance(prefix_len, bool) or not isinstance(prefix_len, int) or prefix_len < 0:
            raise ContractError(f"prefix_kv_lengths[{row_index}] must be nonnegative")
        slots = verify_kv_slots[row_index]
        if len(slots) != block_size:
            raise ContractError(
                f"verify_kv_slots[{row_index}] width={len(slots)} does not match {block_size}"
            )
        if any(isinstance(slot, bool) or not isinstance(slot, int) or slot < 0 for slot in slots):
            raise ContractError(f"verify_kv_slots[{row_index}] must be nonnegative integers")
        if len(set(slots)) != len(slots):
            raise ContractError(f"verify_kv_slots[{row_index}] must be unique")

        accepted = 0
        for candidate, target_token in zip(proposal[1:], target[:-1]):
            if candidate != target_token:
                break
            accepted += 1
        bonus = target[accepted]
        commit_length = accepted + 1
        emitted = proposal[1:commit_length] + (bonus,)
        committed_inputs = proposal[:commit_length]

        if emitted[:-1] != target[:accepted] or emitted[-1] != target[accepted]:
            raise AssertionError("internal target-semantic invariant failed")
        if committed_inputs[1:] != emitted[:-1]:
            raise AssertionError("internal KV/output prefix invariant failed")

        results.append(
            RowResult(
                accepted_drafts=accepted,
                commit_length=commit_length,
                emitted_tokens=emitted,
                committed_input_tokens=committed_inputs,
                committed_verify_kv_slots=tuple(slots[:commit_length]),
                freed_verify_kv_slots=tuple(slots[commit_length:]),
                target_bonus_token=bonus,
                next_pending_token=bonus,
                new_kv_committed_length=prefix_len + commit_length,
            )
        )

    return BatchResult(
        batch_size=batch_size,
        block_size=block_size,
        target_vocab_size=target_vocab_size,
        rows=tuple(results),
        semantic_invariant=(
            "Each emitted token is a target greedy decision on the accepted path; "
            "the first mismatch is replaced by the target bonus."
        ),
        kv_invariant=(
            "Commit target verify-input KV for current+accepted drafts only; "
            "free the verify suffix and leave the target bonus pending."
        ),
    )


def run_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    contract = fixture["contract"]
    result = consume_exact_greedy_chain(
        proposals=fixture["proposals"],
        target_top1=fixture["target_top1"],
        current_tokens=fixture["current_tokens"],
        prefix_kv_lengths=fixture["prefix_kv_lengths"],
        verify_kv_slots=fixture["verify_kv_slots"],
        target_vocab_size=contract["target_vocab_size"],
        required_block_size=contract["block_size"],
    )
    expected = fixture.get("expected_accepted_drafts")
    actual = [row.accepted_drafts for row in result.rows]
    if expected is not None and actual != expected:
        raise ContractError(f"accepted drafts {actual} do not match expected {expected}")
    payload = {
        "schema_version": 1,
        "classification": "valid_cpu_source_consumer_result",
        "fixture_sha256": hashlib.sha256(
            json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "contract": contract,
        "result": json.loads(json.dumps(asdict(result))),
        "checks": {
            "all_expected_accept_lengths_match": expected is None or actual == expected,
            "all_rows_emit_target_bonus": all(
                row.emitted_tokens[-1] == row.target_bonus_token for row in result.rows
            ),
            "all_rows_leave_bonus_pending": all(
                row.next_pending_token == row.target_bonus_token for row in result.rows
            ),
            "no_rejected_kv_committed": all(
                len(row.committed_verify_kv_slots) == row.commit_length
                and len(row.committed_verify_kv_slots)
                + len(row.freed_verify_kv_slots)
                == result.block_size
                for row in result.rows
            ),
        },
    }
    payload["all_checks_pass"] = all(payload["checks"].values())
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    payload = run_fixture(fixture)
    atomic_write_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
