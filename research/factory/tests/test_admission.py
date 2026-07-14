from __future__ import annotations

import copy
import unittest

from grad_research.admission import AdmissionError, validate_paid_run

from helpers import paid_run_spec


class PaidAdmissionTests(unittest.TestCase):
    def test_complete_spec_is_admitted_and_content_bound(self):
        spec, now = paid_run_spec()
        result = validate_paid_run(spec, now=now)
        self.assertEqual("admit", result["decision"])
        self.assertEqual(64, len(result["admission_sha256"]))
        self.assertGreater(result["reserved_usd"], 0)

    def test_every_full_path_preflight_is_required(self):
        spec, now = paid_run_spec()
        del spec["preflight"]["tokenizer_identity"]
        with self.assertRaisesRegex(AdmissionError, "tokenizer_identity"):
            validate_paid_run(spec, now=now)

    def test_failed_preflight_rejects_before_mutation(self):
        spec, now = paid_run_spec()
        spec["preflight"]["parser_fixture"]["pass"] = False
        with self.assertRaisesRegex(AdmissionError, "parser_fixture"):
            validate_paid_run(spec, now=now)

    def test_preflight_evidence_must_bind_the_exact_identity(self):
        spec, now = paid_run_spec()
        spec["preflight"]["tokenizer_identity"]["bound_sha256"] = "c" * 64
        with self.assertRaisesRegex(AdmissionError, "wrong identity"):
            validate_paid_run(spec, now=now)

    def test_budget_must_cover_deadline_exposure_and_cleanup(self):
        spec, now = paid_run_spec(deadline_offset_seconds=600)
        spec["budget"]["max_spend_usd"] = 0.11
        with self.assertRaisesRegex(AdmissionError, "maximum exposure"):
            validate_paid_run(spec, now=now)

    def test_candidate_must_change_one_named_variable(self):
        spec, now = paid_run_spec()
        spec["candidate_id"] = spec["control_id"]
        with self.assertRaisesRegex(AdmissionError, "candidate"):
            validate_paid_run(spec, now=now)

    def test_cleanup_contract_is_fail_closed(self):
        spec, now = paid_run_spec()
        broken = copy.deepcopy(spec)
        broken["cleanup"]["verify_inventory_absent"] = False
        with self.assertRaisesRegex(AdmissionError, "verify_inventory_absent"):
            validate_paid_run(broken, now=now)

    def test_core_telemetry_cannot_be_declared_unavailable(self):
        spec, now = paid_run_spec()
        request = next(
            signal for signal in spec["telemetry_contract"]["signals"] if signal["category"] == "request"
        )
        request.update(
            {
                "status": "unavailable",
                "reason": "request hook is missing",
                "next_probe": "instrument request lifecycle before spending",
            }
        )
        with self.assertRaisesRegex(AdmissionError, "core categories"):
            validate_paid_run(spec, now=now)

    def test_artifact_roles_must_cover_the_telemetry_plan(self):
        spec, now = paid_run_spec()
        spec["artifact_contract"]["required"] = [
            artifact
            for artifact in spec["artifact_contract"]["required"]
            if artifact["role"] != "system_samples"
        ]
        with self.assertRaisesRegex(AdmissionError, "system_samples"):
            validate_paid_run(spec, now=now)

    def test_deep_profiler_cannot_score_a_candidate_arm(self):
        from grad_research.telemetry import build_telemetry_contract

        spec, now = paid_run_spec()
        spec["telemetry_contract"] = build_telemetry_contract("diagnostic_only")
        spec["artifact_contract"]["required"].append(
            {"role": "deep_trace", "path": "deep-trace.json", "media_type": "application/json"}
        )
        with self.assertRaisesRegex(AdmissionError, "diagnostic or repair"):
            validate_paid_run(spec, now=now)


if __name__ == "__main__":
    unittest.main()
