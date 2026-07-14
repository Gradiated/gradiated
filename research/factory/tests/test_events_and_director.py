from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from grad_research.director import ResearchDirector
from grad_research.events import EventIntegrityError, EventStore
from grad_research.util import ValidationError, content_hash

from helpers import HASH_A, scout


def baseline() -> dict:
    return {
        "schema_version": 1,
        "id": "glm47-stock",
        "model_revision": "glm-4.7-flash-complete",
        "checkpoint_manifest_sha256": HASH_A,
        "tokenizer_manifest_sha256": HASH_A,
        "runtime_manifest_sha256": HASH_A,
        "workload_manifest_sha256": HASH_A,
        "quality_policy_sha256": HASH_A,
        "slo_policy_sha256": HASH_A,
        "cost_denominator": "quality_and_slo_eligible_output_tokens",
    }


def observation(cycle: int, summary: str, artifact_ref: str) -> dict:
    return {
        "schema_version": 1,
        "id": f"obs-{cycle}",
        "cycle": cycle,
        "evidence_class": "measured",
        "summary": summary,
        "scope": {
            "model": "glm-4.7-flash",
            "revision": "complete",
            "workload": "fixed-8k-c8",
            "phase": "decode",
            "concurrency": "8",
            "software": "vllm-0.15",
            "hardware": "l40s",
        },
        "metrics": [{
            "name": "critical_path_fraction",
            "value": 0.35,
            "unit": "fraction",
            "time_semantics": "summed_component_duration",
            "coverage": 0.98,
        }],
        "instrumentation_gaps": [],
        "artifact_refs": [artifact_ref],
    }


def result(
    run_id: str,
    scout_id: str,
    outcome: str,
    *,
    artifact_ref: str,
    effect: float | None = None,
    residual: str | None = None,
    spec: dict,
) -> dict:
    value = {
        "schema_version": 1,
        "id": f"result-{run_id}",
        "run_id": run_id,
        "scout_id": scout_id,
        "control_id": spec["control_id"],
        "candidate_id": spec["candidate_id"],
        "changed_variable": spec["changed_variable"],
        "baseline_sha256": spec["baseline_sha256"],
        "prediction_sha256": content_hash(spec["prediction"]),
        "outcome_class": outcome,
        "fidelity": spec["fidelity"],
        "scope": spec["claim_scope"],
        "cost_usd": 0.0,
        "artifact_refs": [artifact_ref],
        "next_action": "continue with the residual",
    }
    if outcome.startswith("scientific_"):
        value.update({
            "gates": {"correctness": True, "quality": True, "slo": True},
            "primary_metric": spec["prediction"]["metric"],
            "observed_effect_fraction": effect,
            "predicted_effect_fraction": spec["prediction"]["point_estimate_fraction"],
            "residual_bottleneck": residual,
        })
    else:
        value["failure_class"] = "tokenizer_identity"
    return value


def register_local(director: ResearchDirector, run_id: str, scout_id: str) -> dict:
    input_ref = director.artifacts.put_json({"run_id": run_id, "seed": 1, "kind": "local-test"})
    spec = {
        "schema_version": 1,
        "execution_kind": "local",
        "run_id": run_id,
        "program_id": "glm47",
        "scout_id": scout_id,
        "fidelity": "simulation",
        "baseline_id": "glm47-stock",
        "baseline_sha256": content_hash(baseline()),
        "control_id": "local-control",
        "candidate_id": f"local-candidate-{run_id}",
        "changed_variable": f"change for {run_id}",
        "claim_scope": {"model": "glm-4.7-flash", "workload": "fixed-8k-c8", "hardware": "l40s"},
        "prediction": {
            "metric": "output_tokens_per_second",
            "expected_direction": "increase",
            "point_estimate_fraction": 0.4,
            "minimum_effect_fraction": 0.05,
            "plausible_ceiling_fraction": 0.4,
            "falsifier": "effect is below the materiality gate",
        },
        "measurement_contract": {
            "protocol": "deterministic",
            "effect_formula": "candidate_over_control_minus_one",
            "minimum_candidate_repetitions": 1,
            "statistic": "median",
        },
        "gates": {
            "correctness": {"policy_sha256": HASH_A, "required": True},
            "quality": {"policy_sha256": HASH_A, "required": True},
            "slo": {"policy_sha256": HASH_A, "required": True},
        },
        "command": f"local-test {run_id}",
        "seed": 1,
        "timeout_seconds": 60,
        "max_cost_usd": 0.0,
        "artifact_refs": [input_ref],
    }
    director.register_local_run(spec)
    return spec


class EventAndDirectorTests(unittest.TestCase):
    def test_invalid_outcome_does_not_update_scientific_beliefs(self):
        with tempfile.TemporaryDirectory() as directory:
            director = ResearchDirector(directory, "glm47")
            director.freeze_baseline(baseline())
            observation_ref = director.artifacts.put_json({"observation": "attention proxy dominates"})
            director.record_observation(observation(1, "attention proxy dominates", observation_ref))
            director.propose_scouts([scout("attention-1", slot="bottleneck_adjacent", family="attention", origin="trace_local")])
            invalid_ref = director.artifacts.put_json({"failure": "tokenizer_identity"})
            invalid_spec = register_local(director, "invalid", "attention-1")
            director.complete_run(
                result(
                    "invalid",
                    "attention-1",
                    "harness_invalid",
                    artifact_ref=invalid_ref,
                    spec=invalid_spec,
                )
            )
            state = director.state()
            self.assertEqual({}, state["mechanism_beliefs"])
            self.assertEqual(1, state["outcome_counts"]["harness_invalid"])

            valid_ref = director.artifacts.put_json({"observed_effect_fraction": 0.01})
            valid_spec = register_local(director, "valid", "attention-1")
            director.complete_run(
                result(
                    "valid",
                    "attention-1",
                    "scientific_negative",
                    artifact_ref=valid_ref,
                    effect=0.01,
                    residual="dense compute or host scheduling",
                    spec=valid_spec,
                )
            )
            state = director.state()
            self.assertEqual(1, state["mechanism_beliefs"]["attention-1"]["negative"])
            self.assertEqual("attention", state["mechanism_beliefs"]["attention-1"]["family"])
            self.assertEqual("dense compute or host scheduling", state["residual_bottleneck"])
            self.assertAlmostEqual(-0.39, state["mechanism_beliefs"]["attention-1"]["latest_prediction_error_fraction"])

    def test_local_diagnostic_updates_residual_without_updating_mechanism_beliefs(self):
        with tempfile.TemporaryDirectory() as directory:
            director = ResearchDirector(directory, "glm47")
            director.freeze_baseline(baseline())
            observation_ref = director.artifacts.put_json({"observation": "quality screen may be unstable"})
            director.record_observation(observation(1, "quality screen may be unstable", observation_ref))
            director.propose_scouts(
                [scout("attention-1", slot="bottleneck_adjacent", family="measurement", origin="adversarial")]
            )
            spec = register_local(director, "local-diagnostic", "attention-1")
            evidence_ref = director.artifacts.put_json({"nominal_pair_failure_fraction": 0.25})
            diagnostic = result(
                "local-diagnostic",
                "attention-1",
                "harness_invalid",
                artifact_ref=evidence_ref,
                spec=spec,
            )
            diagnostic.update(
                {
                    "outcome_class": "diagnostic_valid",
                    "gates": {"correctness": True, "quality": True, "slo": True},
                    "diagnostic_summary": "one nominal pair failed the stability gate",
                    "residual_bottleneck": "the compact quality screen remains unstable",
                }
            )
            diagnostic.pop("failure_class")
            director.complete_run(diagnostic)
            state = director.state()
            self.assertEqual(1, state["research_metrics"]["valid_diagnostic_outcomes"])
            self.assertEqual({}, state["mechanism_beliefs"])
            self.assertEqual(diagnostic["residual_bottleneck"], state["residual_bottleneck"])

    def test_baseline_refresh_is_explicit_and_reasoned(self):
        with tempfile.TemporaryDirectory() as directory:
            director = ResearchDirector(directory, "glm47")
            director.freeze_baseline(baseline())
            refreshed = {**baseline(), "id": "glm47-stock-v2", "runtime_manifest_sha256": "b" * 64}
            director.refresh_baseline(refreshed, reason="new tuned stock runtime after a valid scheduler gain")
            state = director.state()
            self.assertEqual("glm47-stock-v2", state["baseline"]["id"])
            self.assertEqual(1, len(state["baseline_history"]))

    def test_two_complete_discovery_cycles_generate_resumable_context(self):
        with tempfile.TemporaryDirectory() as directory:
            director = ResearchDirector(directory, "glm47")
            director.freeze_baseline(baseline())
            observation_one_ref = director.artifacts.put_json({"observation": "grouped attention proxy is large"})
            director.record_observation(
                observation(1, "grouped attention proxy is large", observation_one_ref)
            )
            cycle_one = [
                scout("attention-1", slot="bottleneck_adjacent", family="attention", origin="trace_local"),
                scout("attention-2", slot="bottleneck_adjacent", family="attention", origin="first_principles"),
                scout("runtime-1", slot="cross_stack", family="runtime", origin="literature_recombination"),
                scout("model-1", slot="model_architecture", family="representation", origin="cross_model_analogy"),
                scout("skeptic-1", slot="adversarial", family="measurement", origin="adversarial"),
            ]
            director.propose_scouts(cycle_one)
            self.assertTrue(director.select_portfolio(1)["coverage"]["ready"])
            result_one_ref = director.artifacts.put_json({"observed_effect_fraction": 0.01})
            result_one_spec = register_local(director, "server-transfer", "attention-1")
            director.complete_run(
                result(
                    "server-transfer",
                    "attention-1",
                    "scientific_negative",
                    artifact_ref=result_one_ref,
                    effect=0.01,
                    residual="dense GEMM or host dependency",
                    spec=result_one_spec,
                )
            )

            observation_two_ref = director.artifacts.put_json(
                {"observation": "dense GEMM is the largest residual family"}
            )
            director.record_observation(
                observation(2, "dense GEMM is the largest residual family", observation_two_ref)
            )
            cycle_two = [
                scout("dense-1", slot="bottleneck_adjacent", family="dense", origin="trace_local", cycle=2),
                scout("dense-2", slot="bottleneck_adjacent", family="dense", origin="first_principles", cycle=2),
                scout("scheduler-2", slot="cross_stack", family="scheduler", origin="literature_recombination", cycle=2),
                scout("representation-2", slot="model_architecture", family="representation", origin="cross_model_analogy", cycle=2),
                scout("skeptic-2", slot="adversarial", family="measurement", origin="adversarial", cycle=2),
            ]
            director.propose_scouts(cycle_two)
            self.assertTrue(director.select_portfolio(2)["coverage"]["ready"])
            result_two_ref = director.artifacts.put_json({"observed_effect_fraction": 0.08})
            result_two_spec = register_local(director, "representation", "representation-2")
            director.complete_run(
                result(
                    "representation",
                    "representation-2",
                    "scientific_positive",
                    artifact_ref=result_two_ref,
                    effect=0.08,
                    residual="scheduler launch gaps",
                    spec=result_two_spec,
                )
            )

            state_path = director.write_state()
            context = director.coordinator_context()
            state = json.loads(state_path.read_text())
            self.assertEqual(2, state["current_cycle"])
            self.assertEqual(2, state["research_metrics"]["valid_scientific_outcomes"])
            self.assertIn("scheduler launch gaps", context)
            self.assertIn("adversarial", context)
            self.assertIn("prediction", context.lower())

    def test_unregistered_zero_cost_result_cannot_update_beliefs(self):
        with tempfile.TemporaryDirectory() as directory:
            director = ResearchDirector(directory, "glm47")
            director.freeze_baseline(baseline())
            observation_ref = director.artifacts.put_json({"observation": "attention"})
            director.record_observation(observation(1, "attention", observation_ref))
            director.propose_scouts(
                [scout("attention-1", slot="bottleneck_adjacent", family="attention", origin="trace_local")]
            )
            evidence_ref = director.artifacts.put_json({"claimed_effect": 0.5})
            fake_spec = {
                "control_id": "stock",
                "candidate_id": "fake",
                "changed_variable": "unregistered",
                "baseline_sha256": content_hash(baseline()),
                "prediction": {"metric": "throughput", "point_estimate_fraction": 0.5},
                "fidelity": "matched_server",
                "claim_scope": {"model": "glm-4.7-flash"},
            }
            with self.assertRaisesRegex(ValidationError, "immutable registered"):
                director.complete_run(
                    result(
                        "unknown",
                        "attention-1",
                        "scientific_positive",
                        artifact_ref=evidence_ref,
                        effect=0.5,
                        residual="unknown",
                        spec=fake_spec,
                    )
                )
            self.assertEqual({}, director.state()["mechanism_beliefs"])

    def test_hash_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(directory, "glm47")
            store.append("baseline_frozen", baseline())
            raw = store.events_path.read_text()
            store.events_path.write_text(raw.replace("glm47-stock", "tampered-stock"))
            with self.assertRaises(EventIntegrityError):
                store.load()


if __name__ == "__main__":
    unittest.main()
