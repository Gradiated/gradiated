from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Mapping, Sequence


EXPECTED_REQUESTS = 32
EXPECTED_PROMPT_TOKENS = 4214
EXPECTED_OUTPUT_TOKENS = 358


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def jsonl(value: bytes) -> list[dict]:
    return [
        json.loads(line)
        for line in value.decode().splitlines()
        if line.strip()
    ]


def response_identity(value: bytes) -> tuple[str, dict]:
    request_ids: set[str] = set()
    usage: dict = {}
    done = False
    for line in value.splitlines():
        if not line.startswith(b"data: "):
            continue
        if line.strip() == b"data: [DONE]":
            done = True
            continue
        row = json.loads(line[6:])
        request_id = row.get("id")
        if request_id:
            request_ids.add(request_id)
        if row.get("usage"):
            usage = row["usage"]
    if len(request_ids) != 1 or not done:
        raise RuntimeError(
            f"ambiguous_sse_identity:{sorted(request_ids)}:done={done}"
        )
    return next(iter(request_ids)), usage


def token_rows(
    terminal: dict,
    responses: Mapping[int, bytes],
    events: Sequence[dict],
) -> list[dict]:
    deltas: dict[str, list[int]] = {}
    finals: dict[str, list[dict]] = {}
    for event in events:
        request_id = event.get("rid")
        if not isinstance(request_id, str):
            raise RuntimeError("token_event_rid_missing")
        if event.get("stage") == "scheduler_to_detokenizer":
            values = event.get("scheduler_output_ids_delta")
            if not isinstance(values, list) or not all(
                isinstance(item, int) for item in values
            ):
                raise RuntimeError(f"token_delta_invalid:{request_id}")
            deltas.setdefault(request_id, []).extend(values)
        elif event.get("stage") == "post_generation_pre_parser_final":
            finals.setdefault(request_id, []).append(event)

    terminal_rows = terminal.get("rows")
    if (
        not terminal.get("pass")
        or terminal.get("complete_requests") != EXPECTED_REQUESTS
        or not isinstance(terminal_rows, list)
        or len(terminal_rows) != EXPECTED_REQUESTS
        or sorted(responses) != list(range(EXPECTED_REQUESTS))
    ):
        raise RuntimeError("control_terminal_incomplete")

    result: list[dict] = []
    seen_ids: set[str] = set()
    for index, raw in sorted(responses.items()):
        terminal_row = terminal_rows[index]
        if terminal_row.get("index") != index:
            raise RuntimeError(f"terminal_index_mismatch:{index}")
        if sha256_bytes(raw) != terminal_row.get("response_sha256"):
            raise RuntimeError(f"response_digest_mismatch:{index}")
        request_id, usage = response_identity(raw)
        if request_id in seen_ids:
            raise RuntimeError(f"duplicate_response_rid:{request_id}")
        seen_ids.add(request_id)
        final_rows = finals.get(request_id, [])
        token_ids = deltas.get(request_id, [])
        if len(final_rows) != 1:
            raise RuntimeError(
                f"ambiguous_final_event:{index}:{request_id}:{len(final_rows)}"
            )
        final = final_rows[0]
        if (
            len(token_ids) != EXPECTED_OUTPUT_TOKENS
            or final.get("completion_counter") != EXPECTED_OUTPUT_TOKENS
            or final.get("prompt_tokens") != EXPECTED_PROMPT_TOKENS
            or usage.get("completion_tokens") != EXPECTED_OUTPUT_TOKENS
            or usage.get("prompt_tokens") != EXPECTED_PROMPT_TOKENS
        ):
            raise RuntimeError(
                f"token_trace_count_mismatch:{index}:{request_id}:"
                f"{len(token_ids)}:{final.get('completion_counter')}:{usage}"
            )
        result.append(
            {
                "index": index,
                "request_sha256": terminal_row["request_sha256"],
                "response_sha256": terminal_row["response_sha256"],
                "rid": request_id,
                "emitted_token_ids": token_ids,
                "completion_counter": final["completion_counter"],
                "prompt_tokens": final["prompt_tokens"],
                "finish_reason": final.get("finish_reason"),
                "parser_input_utf8_hex": final.get("parser_input_utf8_hex"),
            }
        )
    return result


def response_files(root: pathlib.Path) -> dict[int, bytes]:
    result: dict[int, bytes] = {}
    for path in sorted(root.glob("response-*.sse")):
        index = int(path.stem.rsplit("-", 1)[1])
        result[index] = path.read_bytes()
    return result


def validate_oracle(value: dict) -> None:
    rows = value.get("rows")
    if (
        value.get("schema_version") != 1
        or value.get("type") != "packed_m384_persisted_control_token_oracle"
        or not isinstance(rows, list)
        or len(rows) != EXPECTED_REQUESTS
        or [row.get("index") for row in rows] != list(range(EXPECTED_REQUESTS))
        or len({row.get("rid") for row in rows}) != EXPECTED_REQUESTS
        or any(
            len(row.get("emitted_token_ids", [])) != EXPECTED_OUTPUT_TOKENS
            or row.get("completion_counter") != EXPECTED_OUTPUT_TOKENS
            or row.get("prompt_tokens") != EXPECTED_PROMPT_TOKENS
            for row in rows
        )
    ):
        raise RuntimeError("control_token_oracle_invalid")
