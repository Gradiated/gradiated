import importlib.util
import json
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "nebius" / "observer_workload.py"
spec = importlib.util.spec_from_file_location("observer_workload", SOURCE)
observer_workload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer_workload)


class ObserverWorkloadTests(unittest.TestCase):
    def test_request_is_exact_and_carries_deterministic_correlation_id(self):
        request_id = observer_workload.request_id("run-1", "A1", 7)
        request = observer_workload.build_request("prompt", request_id)
        self.assertEqual("run-1:A1:007", request_id)
        self.assertEqual("run-1:A1:007", request.headers["X-request-id"])
        payload = json.loads(request.data)
        self.assertEqual(32, payload["max_tokens"])
        self.assertEqual(0, payload["temperature"])
        self.assertTrue(payload["ignore_eos"])
        self.assertTrue(payload["stream"])
        self.assertTrue(payload["return_token_ids"])

    def test_barrier_arm_preserves_eight_exact_rows(self):
        lock = threading.Lock()
        entered = []

        def completion(prompt, request_id):
            with lock:
                entered.append(request_id)
            return {
                "run_id": "run-1",
                "arm_id": "A1",
                "request_id": request_id,
                "status": "success",
                "input_tokens": 8192,
                "output_tokens": 32,
                "finish_reason": "length",
                "arrival_ns": 1,
                "first_token_ns": 2,
                "end_ns": 34,
                "token_timestamps_ns": list(range(2, 34)),
                "ttft_ms": 1.0,
                "tpot_ms": 1.0,
                "end_to_end_ms": 33.0,
                "stream_sha256": "a" * 64,
            }

        result = observer_workload.run_arm(
            "prompt", "run-1", "A1", completion=completion, concurrency=8, requests=8
        )
        self.assertTrue(result["geometry_pass"])
        self.assertEqual(8, len(result["rows"]))
        self.assertEqual(8, len(set(entered)))
        self.assertEqual(256, result["total_output_tokens"])
        self.assertTrue(all(len(row["token_timestamps_ns"]) == 32 for row in result["rows"]))

    def test_geometry_validation_rejects_silent_truncation(self):
        rows = [
            {
                "request_id": f"run-1:A1:{index:03d}",
                "status": "success",
                "input_tokens": 8192,
                "output_tokens": 32,
                "finish_reason": "length",
                "token_timestamps_ns": list(range(32)),
            }
            for index in range(8)
        ]
        rows[3]["output_tokens"] = 31
        with self.assertRaisesRegex(observer_workload.ObserverWorkloadError, "geometry"):
            observer_workload.validate_rows(rows, requests=8)


if __name__ == "__main__":
    unittest.main()
