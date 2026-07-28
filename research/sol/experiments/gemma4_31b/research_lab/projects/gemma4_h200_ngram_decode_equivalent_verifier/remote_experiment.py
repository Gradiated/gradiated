#!/usr/bin/env python3
"""Pinned four-row discriminator and conditional exact endpoint pair."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import time
import urllib.request


ROOT = pathlib.Path(
    "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier"
)
INPUT = ROOT / "input"
OUT = ROOT / "artifacts"
CHECKPOINT = ROOT / "checkpoint"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
MODEL = "google/gemma-4-31B-it"
SEED_LABEL = "gemma4-background-exact-mix-c32-20260718"
BASE = [
    "--model-path",
    "/work/checkpoint",
    "--tokenizer-path",
    "/work/checkpoint",
    "--served-model-name",
    MODEL,
    "--dtype",
    "bfloat16",
    "--quantization",
    "fp8",
    "--tp-size",
    "1",
    "--kv-cache-dtype",
    "fp8_e5m2",
    "--host",
    "0.0.0.0",
    "--context-length",
    "5000",
    "--max-running-requests",
    "32",
    "--mem-fraction-static",
    "0.85",
    "--enable-metrics",
    "--skip-server-warmup",
    "--enable-dynamic-chunking",
    "--chunked-prefill-size",
    "2048",
    "--enable-fused-qk-norm-rope",
    "--cuda-graph-max-bs",
    "32",
    "--prefill-attention-backend",
    "triton",
    "--decode-attention-backend",
    "triton",
    "--page-size",
    "1",
    "--num-continuous-decode-steps",
    "1",
    "--triton-attention-num-kv-splits",
    "8",
    "--tool-call-parser",
    "gemma4",
    "--port",
    "30000",
]


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def wait_model() -> None:
    for _ in range(300):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:30000/v1/models", timeout=5
            ) as response:
                if MODEL in response.read().decode():
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("model_readiness_timeout")


def post(path: str, body: dict, timeout: int = 900) -> dict:
    request = urllib.request.Request(
        "http://127.0.0.1:30000" + path,
        data=json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_user",
                "description": "Look up a user by id.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "string"}},
                    "required": ["user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_user_details",
                "description": "Get details for a user.",
                "parameters": {
                    "type": "object",
                    "properties": {"user_id": {"type": "string"}},
                    "required": ["user_id"],
                },
            },
        },
    ]


def feature_cases() -> list[dict]:
    common = {
        "model": MODEL,
        "temperature": 0,
        "seed": 20260718,
        "return_logprob": True,
        "top_logprobs_num": 1,
    }
    return [
        {
            "id": "ordinary",
            "path": "/v1/chat/completions",
            "body": {
                **common,
                "messages": [
                    {
                        "role": "user",
                        "content": "State the capital of France in one word.",
                    }
                ],
                "max_tokens": 16,
            },
        },
        {
            "id": "stop_length",
            "path": "/v1/chat/completions",
            "body": {
                **common,
                "messages": [{"role": "user", "content": "Reply exactly with OK."}],
                "max_tokens": 16,
            },
        },
        {
            "id": "cached_prefix",
            "path": "/v1/chat/completions",
            "body": {
                **common,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are concise. Reply with only the requested word.",
                    },
                    {
                        "role": "user",
                        "content": "What color is a clear daytime sky?",
                    },
                ],
                "max_tokens": 16,
            },
        },
        {
            "id": "repeated_pattern",
            "path": "/v1/chat/completions",
            "body": {
                **common,
                "messages": [
                    {
                        "role": "user",
                        "content": "Continue this pattern with four letters: ababab",
                    }
                ],
                "max_tokens": 16,
            },
        },
        {
            "id": "single_tool",
            "path": "/v1/chat/completions",
            "body": {
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": "Call lookup_user for user_id demo_user.",
                    }
                ],
                "tools": tools(),
                "tool_choice": "required",
                "temperature": 0,
                "seed": 20260718,
                "max_tokens": 128,
            },
        },
        {
            "id": "multi_tool",
            "path": "/v1/chat/completions",
            "body": {
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Call lookup_user for user_id demo_user, then "
                            "get_user_details for user_id demo_user. Use both tools "
                            "in that order."
                        ),
                    }
                ],
                "tools": tools(),
                "tool_choice": "required",
                "temperature": 0,
                "seed": 20260718,
                "max_tokens": 128,
            },
        },
    ]


def deterministic_tokens(label: str, count: int) -> list[int]:
    result: list[int] = []
    index = 0
    while len(result) < count:
        digest = hashlib.sha256(f"{SEED_LABEL}|{label}|{index}".encode()).digest()
        for offset in range(0, len(digest), 4):
            result.append(
                1000
                + int.from_bytes(digest[offset : offset + 4], "big") % 249000
            )
            if len(result) == count:
                return result
        index += 1
    return result


def c32_discriminator_case() -> dict:
    prefix = deterministic_tokens("common-prefix", 535)
    suffix = deterministic_tokens("suffix-0", 4214 - 535)
    suffix[0] = 200000
    return {
        "id": "c32_row_00",
        "path": "/v1/completions",
        "body": {
            "model": MODEL,
            "prompt": prefix + suffix,
            "max_tokens": 358,
            "min_tokens": 358,
            "ignore_eos": True,
            "temperature": 0,
            "seed": 20260718,
            "stream": False,
            "return_token_ids": True,
            "add_special_tokens": False,
        },
    }


def normalize(response: dict) -> dict:
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        calls.append(
            {
                "name": function.get("name"),
                "arguments": function.get("arguments"),
                "type": call.get("type"),
                "index": call.get("index"),
            }
        )
    return {
        "content": message.get("content", choice.get("text")),
        "tool_calls": calls,
        "finish_reason": choice.get("finish_reason"),
        "usage": response.get("usage"),
    }


def events(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def wait_final(trace: pathlib.Path, previous: int) -> dict:
    for _ in range(120):
        finals = [
            row
            for row in events(trace)
            if row.get("stage") == "post_generation_pre_parser_final"
        ]
        if len(finals) > previous:
            return finals[-1]
        time.sleep(0.25)
    raise RuntimeError("token_trace_final_timeout")


def serial_capture(arm: str, cases: list[dict]) -> list[dict]:
    trace = OUT / f"{arm}-token-events.jsonl"
    rows = []
    for case in cases:
        previous = sum(
            row.get("stage") == "post_generation_pre_parser_final"
            for row in events(trace)
        )
        response = post(case["path"], case["body"])
        final = wait_final(trace, previous)
        rows.append(
            {
                "id": case["id"],
                "request_sha256": hashlib.sha256(
                    json.dumps(
                        case["body"], sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
                "normalized": normalize(response),
                "trace_final": final,
                "response_sha256": hashlib.sha256(
                    json.dumps(response, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest(),
            }
        )
        atomic(OUT / f"{arm}-serial-rows.json", rows)
    return rows


def launch(arm: str, ngram: bool, discriminator: bool, shadow: bool) -> str:
    name = f"gemma-ngram-decode-equivalent-{arm}"
    run(["sudo", "docker", "rm", "-f", name])
    args = BASE + (["--speculative-algorithm", "NGRAM"] if ngram else [])
    environment = [
        "-e",
        "PYTHONPATH=/work/input:/sgl-workspace/sglang/python",
        "-e",
        f"TOKEN_TRACE_EVENTS=/work/artifacts/{arm}-token-events.jsonl",
        "-e",
        f"FP8_MODULE_AUDIT=/work/artifacts/{arm}-fp8-modules.jsonl",
        "-e",
        f"FP8_CONSUMER_AUDIT=/work/artifacts/{arm}-fp8-consumers.jsonl",
        "-e",
        f"FP8_RUNTIME_AUDIT=/work/artifacts/{arm}-fp8-runtime.json",
    ]
    if ngram:
        environment += [
            "-e",
            "DECODE_EQ_LM_HEAD=1",
            "-e",
            f"DECODE_EQ_AUDIT=/work/artifacts/{arm}-candidate-audit.jsonl",
            "-e",
            f"DECODE_EQ_SHADOW_BASELINE={1 if shadow else 0}",
        ]
    if discriminator:
        environment += [
            "-e",
            f"DISCRIMINATOR_EVENTS=/work/artifacts/{arm}-internal-events.jsonl",
        ]
    result = run(
        [
            "sudo",
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--gpus",
            "all",
            "--ipc=host",
            "--network",
            "host",
            "-v",
            f"{ROOT}:/work",
            "-v",
            f"{INPUT}:/work/input:ro",
            "-v",
            f"{CHECKPOINT}:/work/checkpoint:ro",
            *environment,
            IMAGE,
            "python3",
            "/work/input/endpoint_entrypoint.py",
            *args,
        ]
    )
    atomic(
        OUT / f"{arm}-launch.json",
        {
            "args": args,
            "candidate": ngram,
            "discriminator": discriminator,
            "shadow": shadow,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(f"launch_failed:{arm}:{result.stderr[-800:]}")
    wait_model()
    return name


def stop(name: str, label: str) -> None:
    logs = run(["sudo", "docker", "logs", name])
    (OUT / f"{label}-server.stdout").write_text(logs.stdout)
    (OUT / f"{label}-server.stderr").write_text(logs.stderr)
    result = run(["sudo", "docker", "rm", "-f", name])
    if result.returncode:
        raise RuntimeError(f"container_stop_failed:{name}:{result.stderr[-400:]}")
    time.sleep(3)


def first_difference(left: list[int], right: list[int]) -> int | None:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return None if len(left) == len(right) else min(len(left), len(right))


def discriminator_summary(
    control: list[dict], candidate: list[dict], candidate_events: list[dict]
) -> dict:
    rows = []
    for left, right in zip(control, candidate):
        left_ids = left["trace_final"]["emitted_token_ids"]
        right_ids = right["trace_final"]["emitted_token_ids"]
        divergence = first_difference(left_ids, right_ids)
        rid = right["trace_final"]["rid"]
        internal = [
            row
            for row in candidate_events
            if row.get("stage") == "target_forward" and rid in row.get("rids", [])
        ]
        native_candidate_disagreement = any(
            row.get("native_shadow_argmax_ids") != row.get("argmax_ids")
            for row in internal
        )
        rows.append(
            {
                "id": left["id"],
                "control_tokens": len(left_ids),
                "candidate_tokens": len(right_ids),
                "first_output_divergence": divergence,
                "exact_tokens": divergence is None,
                "native_candidate_logit_argmax_disagreement": native_candidate_disagreement,
                "candidate_rid": rid,
                "target_forward_invocations": [
                    row["invocation"] for row in internal
                ],
            }
        )
    return {
        "schema_version": 1,
        "classification": "four_row_logit_token_discriminator",
        "rows": rows,
        "exact_argmax_and_tokens": all(row["exact_tokens"] for row in rows),
        "native_shadow_present": any(
            "native_shadow_argmax_ids" in row for row in candidate_events
        ),
        "candidate_symbol": (
            "LogitsProcessor._get_logits."
            "decode_equivalent_request_major_depth_slices"
        ),
    }


def batched_text_capture(arm: str) -> list[dict]:
    work = feature_cases()[:4]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(
            executor.map(
                lambda case: post(case["path"], case["body"]),
                work,
            )
        )
    rows = [
        {
            "mode": "batched",
            "id": case["id"],
            "normalized": normalize(response),
            "response_sha256": hashlib.sha256(
                json.dumps(response, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest(),
        }
        for case, response in zip(work, responses)
    ]
    atomic(OUT / f"{arm}-batched-rows.json", rows)
    return rows


def wait_feature_finals(arm: str) -> list[dict]:
    trace = OUT / f"{arm}-token-events.jsonl"
    for _ in range(120):
        finals = [
            row
            for row in events(trace)
            if row.get("stage") == "post_generation_pre_parser_final"
        ]
        if len(finals) >= 10:
            return finals[:10]
        time.sleep(0.25)
    raise RuntimeError(f"ten_row_trace_timeout:{arm}")


def token_projection(rows: list[dict]) -> list[dict]:
    projected = [
        {
            key: row.get(key)
            for key in (
                "scheduler_output_ids",
                "emitted_token_ids",
                "parser_input_utf8_hex",
                "finish_reason",
                "prompt_tokens",
                "completion_counter",
            )
        }
        for row in rows
    ]
    return sorted(
        projected,
        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")),
    )


def cumulative_token_finals(arm: str) -> list[dict]:
    deltas: dict[str, list[int]] = {}
    finals: list[dict] = []
    for event in events(OUT / f"{arm}-token-events.jsonl"):
        rid = event.get("rid")
        if event.get("stage") == "scheduler_to_detokenizer":
            deltas.setdefault(rid, []).extend(event["scheduler_output_ids_delta"])
        elif event.get("stage") == "post_generation_pre_parser_final":
            item = dict(event)
            cumulative = deltas.get(rid, [])
            item["scheduler_output_ids"] = cumulative
            item["emitted_token_ids"] = cumulative
            item["completion_counter_inputs"] = {
                "emitted_token_count": len(cumulative),
                "scheduler_delta_count": len(cumulative),
            }
            finals.append(item)
    return finals


def accounting_exact(rows: list[dict]) -> bool:
    return all(
        row["completion_counter"]
        == row["completion_counter_inputs"]["emitted_token_count"]
        for row in rows
    )


def run_c32(container: str, arm: str) -> dict:
    result = run(
        [
            "sudo",
            "docker",
            "exec",
            container,
            "python3",
            "/work/input/exact_runner.py",
            "--output",
            f"/work/artifacts/{arm}-c32",
            "--arm",
            arm,
            "--concurrency",
            "32",
        ],
        timeout=1800,
    )
    (OUT / f"{arm}-c32.stdout").write_text(result.stdout)
    (OUT / f"{arm}-c32.stderr").write_text(result.stderr)
    if result.returncode not in (0, 72):
        raise RuntimeError(f"c32_runner_failed:{arm}:{result.returncode}")
    return json.loads((OUT / f"{arm}-c32/TERMINAL.json").read_text())


def c32_token_rows(root: pathlib.Path) -> list[list[int]]:
    values = []
    for path in sorted(root.glob("response-*.sse")):
        ids: list[int] = []
        for raw in path.read_bytes().splitlines():
            if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                continue
            item = json.loads(raw[6:])
            choice = (item.get("choices") or [{}])[0]
            ids.extend(choice.get("token_ids") or [])
        values.append(ids)
    return values


def full_arm(arm: str, ngram: bool) -> tuple[list[dict], list[dict], dict]:
    container = launch(arm, ngram, discriminator=False, shadow=False)
    rows = serial_capture(arm, feature_cases())
    rows.extend(batched_text_capture(arm))
    wait_feature_finals(arm)
    feature_finals = cumulative_token_finals(arm)
    if len(feature_finals) != 10:
        raise RuntimeError(f"ten_row_cumulative_trace_count:{arm}:{len(feature_finals)}")
    atomic(OUT / f"{arm}-ten-row-suite.json", rows)
    atomic(OUT / f"{arm}-ten-row-token-trace.json", feature_finals)
    c32_terminal = run_c32(container, arm)
    stop(container, arm)
    c32_finals = [
        row
        for row in cumulative_token_finals(arm)
        if row.get("prompt_tokens") == 4214 and row.get("completion_counter") == 358
    ]
    if len(c32_finals) != 32:
        raise RuntimeError(f"c32_cumulative_trace_count:{arm}:{len(c32_finals)}")
    atomic(OUT / f"{arm}-c32-token-trace.json", c32_finals)
    return rows, feature_finals, {**c32_terminal, "cumulative_trace": c32_finals}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stale_terminal = OUT / "TERMINAL.json"
    if stale_terminal.exists():
        stale_terminal.replace(OUT / "prior-discriminator-terminal.json")
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "conditional_pair_started": False,
            "discriminator_replayed": False,
            "trace_aggregation": "concatenate_every_scheduler_to_detokenizer_delta_per_rid",
        },
    )
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "conditional_pair_started": True,
            "discriminator_replayed": False,
            "trace_aggregation": "concatenate_every_scheduler_to_detokenizer_delta_per_rid",
        },
    )
    if (OUT / "control-full-ten-row-suite.json").exists() and (
        OUT / "control-full-c32/TERMINAL.json"
    ).exists():
        control_suite = json.loads((OUT / "control-full-ten-row-suite.json").read_text())
        control_feature_tokens = cumulative_token_finals("control-full")
        control_c32 = json.loads((OUT / "control-full-c32/TERMINAL.json").read_text())
        control_c32["cumulative_trace"] = [
            row
            for row in control_feature_tokens
            if row.get("prompt_tokens") == 4214
            and row.get("completion_counter") == 358
        ]
        if len(control_feature_tokens) != 43 or len(control_c32["cumulative_trace"]) != 32:
            raise RuntimeError("persisted_control_producer_trace_incomplete")
    else:
        control_suite, control_feature_tokens, control_c32 = full_arm(
            "control-full", False
        )
    atomic(
        OUT / "CONTROL_PRODUCER_STAGE.json",
        {
            "suite": control_suite,
            "feature_tokens": control_feature_tokens,
            "c32": control_c32,
            "persisted": True,
        },
    )
    candidate_suite, candidate_feature_tokens, candidate_c32 = full_arm(
        "candidate-full", True
    )

    feature_api_exact = [
        row["normalized"] for row in control_suite
    ] == [row["normalized"] for row in candidate_suite]
    feature_token_exact = token_projection(
        control_feature_tokens
    ) == token_projection(candidate_feature_tokens)
    feature_accounting_exact = accounting_exact(
        control_feature_tokens + candidate_feature_tokens
    )
    control_tokens = c32_token_rows(OUT / "control-full-c32")
    candidate_tokens = c32_token_rows(OUT / "candidate-full-c32")
    c32_token_exact = (
        len(control_tokens) == 32
        and len(candidate_tokens) == 32
        and control_tokens == candidate_tokens
    )
    control_c32_trace = control_c32["cumulative_trace"]
    candidate_c32_trace = candidate_c32["cumulative_trace"]
    c32_trace_exact = token_projection(control_c32_trace) == token_projection(
        candidate_c32_trace
    )
    c32_accounting_exact = accounting_exact(control_c32_trace + candidate_c32_trace)
    candidate_audit = events(OUT / "candidate-full-candidate-audit.jsonl")
    terminal = {
        "schema_version": 1,
        "classification": "decode_equivalent_exact_suite_and_c32",
        "discriminator_replayed": False,
        "trace_aggregation": "concatenate_every_scheduler_to_detokenizer_delta_per_rid",
        "feature_api_exact": feature_api_exact,
        "feature_token_exact": feature_token_exact,
        "feature_accounting_exact": feature_accounting_exact,
        "c32_token_exact": c32_token_exact,
        "c32_cumulative_scheduler_and_emitted_exact": c32_trace_exact,
        "c32_accounting_exact": c32_accounting_exact,
        "control_c32": control_c32,
        "candidate_c32": candidate_c32,
        "candidate_service_seconds_per_request": candidate_c32.get(
            "service_seconds_per_request"
        ),
        "candidate_audit": candidate_audit,
        "candidate_path_present": bool(candidate_audit),
        "pass": bool(
            feature_api_exact
            and feature_token_exact
            and feature_accounting_exact
            and c32_token_exact
            and c32_trace_exact
            and c32_accounting_exact
            and control_c32.get("pass")
            and candidate_c32.get("pass")
            and candidate_c32.get("service_seconds_per_request", 999)
            <= 0.6381105231
            and candidate_audit
        ),
    }
    atomic(OUT / "TERMINAL.json", terminal)


if __name__ == "__main__":
    main()
