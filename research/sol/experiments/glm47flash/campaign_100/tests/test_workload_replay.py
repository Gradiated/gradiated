import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = ROOT / "workloads"
sys.path.insert(0, str(WORKLOADS))

from build_bundle import build_bundle
from replay_api import ReplayError, materialize_fixture_payload, measure_openai_stream, openai_transport_tools, validate_request
from validate_bundle import load_and_validate


class Clock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


def event(value):
    return f"data: {json.dumps(value, separators=(',', ':'))}\n\n".encode()


class WorkloadReplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        build_bundle(self.root)
        self.bundle = load_and_validate(self.root)
        payload = materialize_fixture_payload(self.bundle, "development_append_1")
        self.request = {
            "schema_version": 1,
            "request_id": "request-1",
            "fixture_id": "development_append_1",
            "messages": payload["messages"],
            "tools": payload["tools"],
            "max_output_tokens": 128,
            "expected_input_tokens": 252,
            "scheduled_offset_ms": 0,
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_records_typed_streaming_latency_tokens_and_truncation(self):
        lines = [
            event({"choices": [{"delta": {"content": "A"}, "finish_reason": None}], "usage": {"prompt_tokens": 252, "completion_tokens": 1}}),
            event({"choices": [{"delta": {"content": "B"}, "finish_reason": None}], "usage": {"prompt_tokens": 252, "completion_tokens": 2}}),
            event({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 252, "completion_tokens": 2, "total_tokens": 254}}),
            b"data: [DONE]\n\n",
        ]
        result = measure_openai_stream(
            validate_request(self.bundle, self.request),
            lines,
            Clock([1_000_000_000, 1_050_000_000, 1_080_000_000, 1_090_000_000]),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["latency_ms"]["ttft"], 50.0)
        self.assertEqual(result["latency_ms"]["itl"], [30.0])
        self.assertEqual(result["latency_ms"]["end_to_end"], 90.0)
        self.assertEqual(result["tokens"], {"input": 252, "output": 2, "total": 254})
        self.assertEqual(result["truncation"], {"detected": False, "finish_reason": "stop"})
        self.assertIsNone(result["error"])

    def test_openai_transport_wraps_tools_without_mutating_frozen_schema(self):
        frozen = self.request["tools"]
        transported = openai_transport_tools(frozen)

        self.assertEqual(transported, [{"type": "function", "function": frozen[0]}])
        self.assertNotIn("type", frozen[0])
        self.assertEqual(frozen[0]["name"], "read_file")

    def test_missing_per_event_token_counts_fails_closed(self):
        lines = [
            event({"choices": [{"delta": {"content": "A"}, "finish_reason": None}]}),
            event({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 252, "completion_tokens": 1, "total_tokens": 253}}),
            b"data: [DONE]\n\n",
        ]
        with self.assertRaisesRegex(ReplayError, "ITL"):
            measure_openai_stream(
                validate_request(self.bundle, self.request),
                lines,
                Clock([1_000_000_000, 1_050_000_000, 1_060_000_000]),
            )

    def test_usage_only_final_event_and_non_text_token_delta_are_observable(self):
        lines = [
            event({"choices": [{"delta": {"reasoning_content": "A"}, "finish_reason": None}], "usage": {"prompt_tokens": 252, "completion_tokens": 1}}),
            event({"choices": [{"delta": {"tool_calls": [{"index": 0}]}, "finish_reason": None}], "usage": {"prompt_tokens": 252, "completion_tokens": 2}}),
            event({"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 252, "completion_tokens": 2, "total_tokens": 254}}),
            event({"choices": [], "usage": {"prompt_tokens": 252, "completion_tokens": 2, "total_tokens": 254}}),
            b"data: [DONE]\n\n",
        ]

        result = measure_openai_stream(
            validate_request(self.bundle, self.request),
            lines,
            Clock([1_000_000_000, 1_010_000_000, 1_030_000_000, 1_040_000_000, 1_050_000_000]),
        )

        self.assertEqual(result["latency_ms"]["ttft"], 10.0)
        self.assertEqual(result["latency_ms"]["itl"], [20.0])
        self.assertEqual(result["truncation"], {"detected": False, "finish_reason": "tool_calls"})

    def test_request_must_match_frozen_tokenizer_binding(self):
        request = dict(self.request)
        request["expected_input_tokens"] = 251
        with self.assertRaisesRegex(ReplayError, "tokenizer binding"):
            validate_request(self.bundle, request)

    def test_request_content_must_match_frozen_fixture(self):
        request = dict(self.request)
        request["messages"] = [{"role": "user", "content": "same length is not enough"}]
        with self.assertRaisesRegex(ReplayError, "frozen fixture"):
            validate_request(self.bundle, request)

    def test_length_finish_is_typed_truncation(self):
        request = dict(self.request)
        request["max_output_tokens"] = 1
        lines = [
            event({"choices": [{"delta": {"content": "A"}, "finish_reason": None}], "usage": {"prompt_tokens": 252, "completion_tokens": 1}}),
            event({"choices": [{"delta": {}, "finish_reason": "length"}], "usage": {"prompt_tokens": 252, "completion_tokens": 1, "total_tokens": 253}}),
            b"data: [DONE]\n\n",
        ]
        result = measure_openai_stream(
            validate_request(self.bundle, request),
            lines,
            Clock([1_000_000_000, 1_010_000_000, 1_020_000_000]),
        )
        self.assertEqual(result["truncation"], {"detected": True, "finish_reason": "length"})

    def test_frozen_fixed_workload_length_finish_at_declared_cap_is_expected(self):
        request = {
            "schema_version": 1,
            "request_id": "fixed-request-1",
            "fixture_id": "development_fixed_1",
            "prompt": "code",
            "max_output_tokens": 1,
            "expected_input_tokens": 8192,
            "scheduled_offset_ms": 0,
        }
        lines = [
            event({"choices": [{"delta": {"content": "A"}, "finish_reason": None}], "usage": {"prompt_tokens": 8192, "completion_tokens": 1}}),
            event({"choices": [{"delta": {}, "finish_reason": "length"}], "usage": {"prompt_tokens": 8192, "completion_tokens": 1, "total_tokens": 8193}}),
            b"data: [DONE]\n\n",
        ]

        result = measure_openai_stream(
            validate_request(self.bundle, request),
            lines,
            Clock([1_000_000_000, 1_010_000_000, 1_020_000_000]),
        )

        self.assertEqual(result["truncation"], {"detected": False, "finish_reason": "length"})

    def test_frozen_fixed_workload_length_finish_before_declared_cap_fails_closed(self):
        request = {
            "schema_version": 1,
            "request_id": "fixed-request-1",
            "fixture_id": "development_fixed_1",
            "prompt": "code",
            "max_output_tokens": 2,
            "expected_input_tokens": 8192,
            "scheduled_offset_ms": 0,
        }
        lines = [
            event({"choices": [{"delta": {"content": "A"}, "finish_reason": None}], "usage": {"prompt_tokens": 8192, "completion_tokens": 1}}),
            event({"choices": [{"delta": {}, "finish_reason": "length"}], "usage": {"prompt_tokens": 8192, "completion_tokens": 1, "total_tokens": 8193}}),
            b"data: [DONE]\n\n",
        ]

        with self.assertRaisesRegex(ReplayError, "before the declared output cap"):
            measure_openai_stream(
                validate_request(self.bundle, request),
                lines,
                Clock([1_000_000_000, 1_010_000_000, 1_020_000_000]),
            )


if __name__ == "__main__":
    unittest.main()
