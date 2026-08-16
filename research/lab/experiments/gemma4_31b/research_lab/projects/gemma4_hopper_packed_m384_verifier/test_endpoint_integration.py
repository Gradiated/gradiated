from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


PROJECT = pathlib.Path(__file__).resolve().parent
ENDPOINT = PROJECT / "inputs" / "endpoint"


def load_pair():
    spec = importlib.util.spec_from_file_location(
        "packed_m384_endpoint_pair", ENDPOINT / "endpoint_pair.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("endpoint_pair_spec_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PAIR = load_pair()


def terminal() -> dict:
    return {
        "pass": True,
        "complete_requests": 32,
        "service_seconds_per_request": 0.6,
        "complete_request_throughput": 32 / 19.2,
        "cache": {
            "uncached_prompt_tokens_delta": 117728,
            "cached_prompt_tokens_delta": 17120,
        },
        "rows": [
            {"request_sha256": f"{index:064x}", "returned_token_ids": 358}
            for index in range(32)
        ],
    }


def append_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )


def seed_artifacts(root: pathlib.Path) -> tuple[dict, dict]:
    artifacts = root / "artifacts"
    control = terminal()
    candidate = terminal()
    candidate["service_seconds_per_request"] = 0.55
    for arm in ("control", "candidate"):
        arm_root = artifacts / arm
        arm_root.mkdir(parents=True)
        for index in range(32):
            token_ids = list(range(index * 1000, index * 1000 + 358))
            payload = {
                "choices": [{"token_ids": token_ids, "text": "x"}],
                "usage": {"prompt_tokens": 4214, "completion_tokens": 358},
            }
            (arm_root / f"response-{index:02d}.sse").write_text(
                "data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n"
            )
        events = []
        for index in range(32):
            token_ids = list(range(index * 1000, index * 1000 + 358))
            events.extend(
                [
                    {
                        "stage": "scheduler_to_detokenizer",
                        "rid": str(index),
                        "scheduler_output_ids_delta": token_ids,
                    },
                    {
                        "stage": "post_generation_pre_parser_final",
                        "rid": str(index),
                        "completion_counter": 358,
                        "finish_reason": {"type": "length"},
                        "parser_input_utf8_hex": "78",
                        "prompt_tokens": 4214,
                    },
                ]
            )
        append_jsonl(artifacts / f"{arm}.token-events.jsonl", events)
    routes = [
        *[
            {"route": "candidate", "local": True, "global": False}
            for _ in range(50)
        ],
        *[
            {"route": "candidate", "local": False, "global": True}
            for _ in range(10)
        ],
    ]
    append_jsonl(artifacts / "candidate.route.jsonl", routes)
    dispatch = [
        *[{"kind": "local_d256"} for _ in range(50)],
        *[{"kind": "global_d512"} for _ in range(10)],
    ]
    append_jsonl(artifacts / "candidate.candidate.jsonl", dispatch)
    return control, candidate


class EndpointConsumerTests(unittest.TestCase):
    def test_complete_pair_passes_all_gates(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT) as value:
            root = pathlib.Path(value)
            control, candidate = seed_artifacts(root)
            result = PAIR.consume(root, control, candidate, {"bound": True})
            self.assertTrue(result["pass"])
            self.assertEqual(result["classification"], "endpoint_positive")
            self.assertTrue(all(result["gates"].values()))

    def test_target_token_mutation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT) as value:
            root = pathlib.Path(value)
            control, candidate = seed_artifacts(root)
            response = root / "artifacts" / "candidate" / "response-00.sse"
            response.write_text(
                response.read_text().replace('"token_ids": [0, 1', '"token_ids": [9, 1')
            )
            result = PAIR.consume(root, control, candidate, {"bound": True})
            self.assertFalse(result["pass"])
            self.assertFalse(result["gates"]["exact_sse_target_tokens"])

    def test_target_fallback_event_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT) as value:
            root = pathlib.Path(value)
            control, candidate = seed_artifacts(root)
            path = root / "artifacts" / "candidate.route.jsonl"
            with path.open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "route": "rejected_no_fallback",
                            "local": False,
                            "global": False,
                        }
                    )
                    + "\n"
                )
            result = PAIR.consume(root, control, candidate, {"bound": True})
            self.assertFalse(result["pass"])
            self.assertFalse(
                result["gates"]["candidate_no_fallback_and_exact_50_10_routing"]
            )

    def test_global_capacity_covers_endpoint_bound(self) -> None:
        source = (ENDPOINT / "packed_m384_endpoint.py").read_text()
        self.assertIn("GLOBAL_PREFIX_CAPACITY = 4608", source)
        self.assertLessEqual(4214 + 358 + 12, 4608)


if __name__ == "__main__":
    unittest.main()
