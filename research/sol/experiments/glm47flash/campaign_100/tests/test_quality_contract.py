import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "quality"
sys.path.insert(0, str(QUALITY))

from build_quality import build_quality
from score_pair import ScoreError, score_pair
from validate_quality import QualityError, load_and_validate


class QualityContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        build_quality(self.path)
        self.bundle = load_and_validate(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_suite_is_disjoint_complete_and_policy_is_immutable(self):
        expected = {
            "tool_call",
            "coding",
            "long_context_retrieval",
            "multi_turn_continuation",
            "teacher_forced_loss",
            "serving_correctness",
        }
        dev = self.bundle["fixtures"]["development"]
        holdout = self.bundle["fixtures"]["holdout"]
        self.assertEqual({case["category"] for case in dev}, expected)
        self.assertEqual({case["category"] for case in holdout}, expected)
        self.assertFalse({case["case_id"] for case in dev} & {case["case_id"] for case in holdout})
        self.assertEqual(self.bundle["policy"]["max_overall_point_regression"], 0.02)
        self.assertEqual(self.bundle["policy"]["max_critical_category_regression"], 0.05)
        self.assertTrue(self.bundle["policy"]["catastrophic_category_failure_is_reject"])
        self.assertEqual(self.bundle["policy"]["mtp_identity_requirement"], "exact_normalized_output_identity")
        for case in dev + holdout:
            if case["category"] == "long_context_retrieval":
                self.assertGreaterEqual(len(case["synthetic_context"]), 40_000)
                self.assertEqual(case["tokenizer_binding"]["status"], "required_before_gpu_execution")
            if case["category"] == "teacher_forced_loss":
                self.assertIn("teacher_forced_text", case)
                self.assertEqual(case["scorer"]["kind"], "teacher_forced_logprobs")

    def test_identical_good_responses_pass_pair_screen(self):
        responses = self.path / "sample_development_responses.jsonl"
        result = score_pair(self.path, "development", responses, responses)
        self.assertTrue(result["point_screen_pass"])
        self.assertFalse(result["provisional_due_to_uncertainty"])
        self.assertEqual(result["overall_regression"], 0.0)

    def test_holdout_sample_is_semantically_disjoint_and_executable(self):
        dev = self.bundle["fixtures"]["development"]
        holdout = self.bundle["fixtures"]["holdout"]
        dev_prompts = {case["prompt"] for case in dev}
        holdout_prompts = {case["prompt"] for case in holdout}
        self.assertFalse(dev_prompts & holdout_prompts)
        responses = self.path / "sample_holdout_responses.jsonl"
        result = score_pair(self.path, "holdout", responses, responses)
        self.assertTrue(result["point_screen_pass"])

    def test_critical_regression_fails(self):
        control = self.path / "sample_development_responses.jsonl"
        candidate = self.path / "candidate.jsonl"
        rows = [json.loads(line) for line in control.read_text().splitlines()]
        tool = next(row for row in rows if row["case_id"] == "dev_tool_01")
        tool["output"] = '{"name":"read_file","arguments":{}}'
        candidate.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))
        result = score_pair(self.path, "development", control, candidate)
        self.assertFalse(result["point_screen_pass"])
        self.assertIn("critical_category_regression", result["reject_reasons"])

    def test_coding_fixture_runs_executable_tests(self):
        control = self.path / "sample_development_responses.jsonl"
        candidate = self.path / "candidate.jsonl"
        rows = [json.loads(line) for line in control.read_text().splitlines()]
        coding = next(row for row in rows if row["case_id"] == "dev_code_01")
        coding["output"] = "def clamp(value, low, high):\n    return value\n"
        candidate.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))
        result = score_pair(self.path, "development", control, candidate)
        self.assertEqual(result["candidate"]["categories"]["coding"], 0.0)

    def test_missing_or_malformed_responses_fail_closed(self):
        malformed = self.path / "malformed.jsonl"
        malformed.write_text('{"case_id":"dev_tool_01","output":')
        with self.assertRaises(ScoreError):
            score_pair(self.path, "development", malformed, malformed)

    def test_tampered_policy_is_rejected(self):
        policy = self.path / "policy.json"
        data = json.loads(policy.read_text())
        data["max_overall_point_regression"] = 0.2
        policy.write_text(json.dumps(data))
        with self.assertRaises(QualityError):
            load_and_validate(self.path)

    def test_caller_supplied_nll_is_never_accepted(self):
        control = self.path / "sample_development_responses.jsonl"
        candidate = self.path / "candidate.jsonl"
        rows = [json.loads(line) for line in control.read_text().splitlines()]
        loss = next(row for row in rows if row["case_id"] == "dev_loss_01")
        loss["output"] = {
            "teacher_forced_nll": 0.0,
            "compliance": True,
        }
        candidate.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))
        result = score_pair(self.path, "development", control, candidate)
        self.assertFalse(result["point_screen_pass"])
        self.assertIn("teacher_forced_loss_regression", result["reject_reasons"])


if __name__ == "__main__":
    unittest.main()
