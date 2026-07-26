from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


PROJECT = pathlib.Path(__file__).resolve().parent
ENDPOINT = PROJECT / "inputs" / "endpoint"
sys.path.insert(0, str(ENDPOINT))

from token_oracle import validate_oracle


def load_candidate_resume():
    spec = importlib.util.spec_from_file_location(
        "candidate_resume_test", ENDPOINT / "candidate_resume.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate_resume_spec_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CANDIDATE = load_candidate_resume()


def function_ast(path: pathlib.Path, name: str) -> str:
    module = ast.parse(path.read_text())
    node = next(
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.dump(node, include_attributes=False)


def append_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )


class GraphCaptureRepairTests(unittest.TestCase):
    def test_persisted_control_oracle_is_exact_32_by_358(self) -> None:
        oracle = json.loads((ENDPOINT / "CONTROL_TOKEN_ORACLE.json").read_text())
        validate_oracle(oracle)
        self.assertEqual(len(oracle["rows"]), 32)
        self.assertEqual(
            {len(row["emitted_token_ids"]) for row in oracle["rows"]},
            {358},
        )
        self.assertFalse(oracle["source"]["control_request_replayed"])

    def test_layout_repair_preserves_all_measured_kernel_asts(self) -> None:
        measured = PROJECT / "packed_m384_attention_v2.py"
        integrated = ENDPOINT / "packed_m384_endpoint.py"
        for name in (
            "_score_partition_kernel",
            "_merge_state_kernel",
            "_value_consumer_kernel",
        ):
            self.assertEqual(
                function_ast(measured, name), function_ast(integrated, name)
            )
        source = integrated.read_text()
        self.assertNotIn(".is_contiguous()", source)
        self.assertIn("tensor.stride(-1) == 1", source)
        self.assertIn("o_extend.stride(0)", source)

    def test_candidate_only_consumer_uses_persisted_oracle_and_fails_closed(
        self,
    ) -> None:
        oracle = json.loads((ENDPOINT / "CONTROL_TOKEN_ORACLE.json").read_text())
        with tempfile.TemporaryDirectory(dir=PROJECT) as value:
            root = pathlib.Path(value)
            artifacts = root / "artifacts"
            candidate_root = artifacts / "candidate"
            candidate_root.mkdir(parents=True)
            input_root = root / "input"
            input_root.mkdir()
            oracle_path = input_root / "CONTROL_TOKEN_ORACLE.json"
            oracle_path.write_text(json.dumps(oracle))
            events = []
            terminal_rows = []
            for row in oracle["rows"]:
                index = row["index"]
                request_id = f"candidate-{index:02d}"
                payload = (
                    "data: "
                    + json.dumps(
                        {
                            "id": request_id,
                            "choices": [{"text": "x"}],
                            "usage": {
                                "prompt_tokens": 4214,
                                "completion_tokens": 358,
                            },
                        }
                    )
                    + "\n\ndata: [DONE]\n\n"
                ).encode()
                (candidate_root / f"response-{index:02d}.sse").write_bytes(
                    payload
                )
                terminal_rows.append(
                    {
                        "index": index,
                        "request_sha256": row["request_sha256"],
                        "response_sha256": hashlib.sha256(payload).hexdigest(),
                        "returned_token_ids": 0,
                    }
                )
                events.extend(
                    [
                        {
                            "stage": "scheduler_to_detokenizer",
                            "rid": request_id,
                            "scheduler_output_ids_delta": list(
                                row["emitted_token_ids"]
                            ),
                        },
                        {
                            "stage": "post_generation_pre_parser_final",
                            "rid": request_id,
                            "completion_counter": 358,
                            "prompt_tokens": 4214,
                            "finish_reason": row["finish_reason"],
                            "parser_input_utf8_hex": row[
                                "parser_input_utf8_hex"
                            ],
                        },
                    ]
                )
            append_jsonl(artifacts / "candidate.token-events.jsonl", events)
            append_jsonl(
                artifacts / "candidate.route.jsonl",
                [
                    *[
                        {"route": "candidate", "local": True, "global": False}
                        for _ in range(50)
                    ],
                    *[
                        {"route": "candidate", "local": False, "global": True}
                        for _ in range(10)
                    ],
                ],
            )
            append_jsonl(
                artifacts / "candidate.candidate.jsonl",
                [
                    *[{"kind": "local_d256"} for _ in range(50)],
                    *[{"kind": "global_d512"} for _ in range(10)],
                ],
            )
            terminal = {
                "pass": True,
                "complete_requests": 32,
                "service_seconds_per_request": 0.6,
                "complete_request_throughput": 32 / 19.2,
                "cache": {
                    "uncached_prompt_tokens_delta": 117728,
                    "cached_prompt_tokens_delta": 17120,
                },
                "rows": terminal_rows,
            }
            result = CANDIDATE.consume(
                root, oracle, terminal, {"bound": True}
            )
            self.assertTrue(result["pass"])
            events[0]["scheduler_output_ids_delta"][0] += 1
            append_jsonl(artifacts / "candidate.token-events.jsonl", events)
            rejected = CANDIDATE.consume(
                root, oracle, terminal, {"bound": True}
            )
            self.assertFalse(rejected["pass"])
            self.assertFalse(
                rejected["gates"]["exact_persisted_control_target_tokens"]
            )


if __name__ == "__main__":
    unittest.main()
