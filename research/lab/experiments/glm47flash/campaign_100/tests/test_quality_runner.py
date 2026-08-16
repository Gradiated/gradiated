import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "quality"
sys.path.insert(0, str(QUALITY))

from build_quality import build_quality
from run_pair import QualityAPIClient, RunnerError, run_endpoint
from score_pair import score_pair
from validate_quality import load_and_validate


class FakeClient:
    def __init__(self, cases, deterministic=True, malformed_logprobs=False):
        self.cases = {case["case_id"]: case for case in cases}
        self.deterministic = deterministic
        self.malformed_logprobs = malformed_logprobs
        self.chat_calls = {}

    def chat(self, case, messages):
        self.chat_calls[case["case_id"]] = self.chat_calls.get(case["case_id"], 0) + 1
        kind = case["scorer"]["kind"]
        if kind == "json_exact":
            output = json.dumps(case["scorer"]["expected"], sort_keys=True, separators=(",", ":"))
        elif kind == "normalized_exact":
            output = case["scorer"]["expected"]
        elif case["split"] == "development":
            output = "def clamp(value, low, high):\n    return max(low, min(high, value))\n"
        else:
            output = "def exclusive_upper(start, stop):\n    return list(range(start, stop))\n"
        if not self.deterministic and self.chat_calls[case["case_id"]] > 1:
            output += " changed"
        return {"output": output, "raw_sha256": hashlib.sha256(output.encode()).hexdigest()}

    def teacher_force(self, case, text):
        if self.malformed_logprobs:
            return {"meta_info": {"input_token_logprobs": []}, "teacher_forced_nll": 0.0, "compliance": True}
        return {
            "meta_info": {
                "input_token_logprobs": [
                    [None, 1, "<bos>"],
                    [-1.0, 2, "quality"],
                    [-1.25, 3, " sentinel"],
                    [-0.75, 4, "."],
                ]
            },
            "teacher_forced_nll": 99.0,
            "compliance": False,
        }


class QualityRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        build_quality(self.path)
        self.bundle = load_and_validate(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_executes_all_categories_and_computes_nll_from_logprobs(self):
        cases = self.bundle["fixtures"]["development"]
        responses = self.path / "responses.jsonl"
        evidence = self.path / "evidence.json"
        run_endpoint(self.bundle, "development", FakeClient(cases), responses, evidence)

        rows = [json.loads(line) for line in responses.read_text().splitlines()]
        loss = next(row for row in rows if row["case_id"] == "dev_loss_01")
        self.assertNotIn("teacher_forced_nll", loss["output"])
        self.assertEqual(loss["output"]["input_token_logprobs"][0]["logprob"], -1.0)
        result = score_pair(self.path, "development", responses, responses)
        self.assertTrue(result["point_screen_pass"])
        measured_nll = next(
            case["metrics"]["teacher_forced_nll"]
            for case in result["control"]["cases"]
            if case["category"] == "teacher_forced_loss"
        )
        self.assertEqual(measured_nll, 1.0)

    def test_deterministic_serving_mismatch_fails_closed(self):
        cases = self.bundle["fixtures"]["development"]
        with self.assertRaisesRegex(RunnerError, "deterministic"):
            run_endpoint(
                self.bundle,
                "development",
                FakeClient(cases, deterministic=False),
                self.path / "responses.jsonl",
                self.path / "evidence.json",
            )

    def test_missing_runtime_input_logprobs_fails_closed_despite_claimed_nll(self):
        cases = self.bundle["fixtures"]["development"]
        with self.assertRaisesRegex(RunnerError, "input token logprobs"):
            run_endpoint(
                self.bundle,
                "development",
                FakeClient(cases, malformed_logprobs=True),
                self.path / "responses.jsonl",
                self.path / "evidence.json",
            )

    def test_disable_thinking_is_an_explicit_request_policy(self):
        client = QualityAPIClient(
            "http://127.0.0.1:30000",
            self.bundle["policy"]["execution_contract"],
            disable_thinking=True,
        )
        captured = {}

        def fake_post(endpoint, payload):
            captured.update(payload)
            return {
                "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]
            }, "0" * 64

        client.post = fake_post
        client.chat({}, [{"role": "user", "content": "Say ok."}])
        self.assertEqual(captured["chat_template_kwargs"], {"enable_thinking": False})


if __name__ == "__main__":
    unittest.main()
