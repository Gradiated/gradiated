from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .admission import validate_paid_run
from .artifacts import ArtifactStore
from .context import build_coordinator_context
from .events import EventStore
from .labd import LabDatabase
from .portfolio import select_portfolio, validate_scout
from .records import (
    DIAGNOSTIC_OUTCOMES,
    SCIENTIFIC_OUTCOMES,
    SUCCESSFUL_OUTCOMES,
    validate_baseline,
    validate_observation,
    validate_result,
)
from .run_specs import validate_local_run, validate_result_binding
from .telemetry import validate_telemetry_summary
from .util import ValidationError, content_hash


class ResearchDirector:
    def __init__(self, root: str | Path, program_id: str):
        self.store = EventStore(root, program_id)
        self.artifacts = ArtifactStore(root, program_id)
        self.program_id = program_id

    def state(self) -> dict[str, Any]:
        return self.store.project()

    def freeze_baseline(self, baseline: dict[str, Any]) -> dict[str, Any]:
        validate_baseline(baseline)
        current = self.state()["baseline"]
        if current is not None and current != baseline:
            raise ValidationError("baseline changes require a new explicit program or baseline-refresh event")
        if current == baseline:
            return baseline
        self.store.append_once("baseline_frozen", baseline, idempotency_key="baseline:initial")
        return baseline

    def record_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        validate_observation(observation)
        state = self.state()
        if state["baseline"] is None:
            raise ValidationError("freeze a baseline before recording observations")
        for reference in observation["artifact_refs"]:
            self.artifacts.verify_reference(reference)
        existing = state["observations"].get(observation["id"])
        if existing is not None:
            if existing != observation:
                raise ValidationError("observation identity was reused with different content")
            return observation
        self.store.append_once(
            "observation_recorded",
            observation,
            idempotency_key=f"observation:{observation['id']}",
        )
        return observation

    def refresh_baseline(self, baseline: dict[str, Any], *, reason: str) -> dict[str, Any]:
        validate_baseline(baseline)
        if self.state()["baseline"] is None:
            raise ValidationError("freeze the initial baseline before refreshing it")
        from .util import require_text

        require_text("baseline refresh reason", reason)
        if self.state()["baseline"] == baseline:
            raise ValidationError("baseline refresh must change the baseline identity")
        self.store.append_once(
            "baseline_refreshed",
            {"schema_version": 1, "baseline": baseline, "reason": reason},
            idempotency_key=f"baseline-refresh:{baseline['id']}",
        )
        return baseline

    def _validate_run_context(self, spec: dict[str, Any]) -> dict[str, Any]:
        state = self.state()
        baseline = state["baseline"]
        if baseline is None:
            raise ValidationError("run registration requires a frozen baseline")
        if spec.get("program_id") != self.program_id:
            raise ValidationError("run spec belongs to another research program")
        if spec.get("scout_id") not in state["scouts"]:
            raise ValidationError("run spec requires a recorded scout")
        if spec.get("baseline_id") != baseline["id"] or spec.get("baseline_sha256") != content_hash(baseline):
            raise ValidationError("run spec is not bound to the frozen baseline")
        if spec["gates"]["quality"]["policy_sha256"] != baseline["quality_policy_sha256"]:
            raise ValidationError("run quality gate differs from the frozen baseline")
        if spec["gates"]["slo"]["policy_sha256"] != baseline["slo_policy_sha256"]:
            raise ValidationError("run SLO gate differs from the frozen baseline")
        return state

    def register_local_run(self, spec: dict[str, Any]) -> dict[str, Any]:
        validate_local_run(spec)
        state = self._validate_run_context(spec)
        for reference in spec["artifact_refs"]:
            self.artifacts.verify_reference(reference)
        existing = state["runs"].get(spec["run_id"])
        if existing is not None:
            if existing.get("spec") != spec:
                raise ValidationError("run identity was reused with a different specification")
            return spec
        self.store.append_once(
            "run_registered",
            {"schema_version": 1, "spec": spec},
            idempotency_key=f"run-registration:{spec['run_id']}",
        )
        return spec

    def propose_scouts(self, cards: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        state = self.state()
        validated = []
        for card in cards:
            validate_scout(card)
            missing = sorted(set(card["observation_ids"]) - state["observations"].keys())
            if missing:
                raise ValidationError(f"scout {card['id']} references unknown observations: {', '.join(missing)}")
            existing = state["scouts"].get(card["id"])
            if existing is not None:
                if existing != card:
                    raise ValidationError(f"scout identity {card['id']} was reused with different content")
                continue
            validated.append(card)
        self.store.append_many(
            [
                ("scout_proposed", card, None, f"scout:{card['id']}")
                for card in validated
            ]
        )
        return validated

    def select_portfolio(self, cycle: int, *, max_size: int = 5) -> dict[str, Any]:
        state = self.state()
        cards = [card for card in state["scouts"].values() if card["cycle"] == cycle]
        completed_scout_ids = {
            run["result"]["scout_id"]
            for run in state["runs"].values()
            if run.get("status") == "completed" and run.get("result")
        }
        previous_novelty = {
            state["scouts"][scout_id]["novelty_key"]
            for scout_id in completed_scout_ids
            if scout_id in state["scouts"]
        }
        selection = select_portfolio(cards, max_size=max_size, previous_novelty_keys=previous_novelty)
        payload = {
            "schema_version": 1,
            "cycle": cycle,
            "selected_ids": [card["id"] for card in selection["selected"]],
            "coverage": selection["coverage"],
            "ranking_method": selection["ranking_method"],
        }
        existing = state["portfolios"].get(str(cycle))
        if existing is not None:
            if existing != payload:
                raise ValidationError("portfolio cycle was already selected with different content")
            return selection
        self.store.append_once(
            "portfolio_selected",
            payload,
            idempotency_key=f"portfolio:{cycle}",
        )
        return selection

    def admit_paid_run(
        self,
        spec: dict[str, Any],
        *,
        lab: LabDatabase,
        owner: str,
        epoch: int,
        now: datetime,
    ) -> dict[str, Any]:
        admission = validate_paid_run(spec, now=now)
        state = self._validate_run_context(spec)
        baseline = state["baseline"]
        control_identities = spec.get("identities", {})
        baseline_identity_fields = {
            "model_revision": "model_revision",
            "checkpoint_manifest_sha256": "checkpoint_manifest_sha256",
            "tokenizer_manifest_sha256": "tokenizer_manifest_sha256",
            "runtime_manifest_sha256": "runtime_manifest_sha256",
            "workload_manifest_sha256": "workload_manifest_sha256",
        }
        mismatched_control = sorted(
            identity_field
            for identity_field, baseline_field in baseline_identity_fields.items()
            if control_identities.get(identity_field) != baseline[baseline_field]
        )
        if mismatched_control:
            raise ValidationError(
                "paid control identities differ from the frozen baseline: " + ", ".join(mismatched_control)
            )
        selected = {
            scout_id
            for portfolio in state["portfolios"].values()
            for scout_id in portfolio.get("selected_ids", [])
        }
        if spec["scout_id"] not in selected and not spec.get("override_reason"):
            raise ValidationError("unselected scout requires an explicit override_reason")
        existing_run = state["runs"].get(spec["run_id"])
        if existing_run is not None:
            if existing_run.get("spec") != spec:
                raise ValidationError("run identity was reused with a different specification")
            return existing_run["admission"]
        for name, check in spec["preflight"].items():
            evidence = self.artifacts.load_json_reference(check["evidence_sha256"])
            expected = {
                "schema_version": 1,
                "check": name,
                "pass": True,
                "bound_sha256": check["bound_sha256"],
            }
            if not isinstance(evidence, dict) or any(evidence.get(key) != value for key, value in expected.items()):
                raise ValidationError(f"paid preflight evidence for {name} is absent or not content-bound")
        reservation_id = f"reservation:{spec['run_id']}"
        lab.reserve(
            reservation_id=reservation_id,
            campaign_id=spec["campaign_id"],
            program_id=spec["program_id"],
            owner=owner,
            epoch=epoch,
            amount_usd=admission["reserved_usd"],
            cleanup_reserve_usd=admission["cleanup_reserve_usd"],
            expires_at=datetime.fromisoformat(admission["absolute_deadline_utc"].replace("Z", "+00:00")).timestamp(),
            admission_sha256=admission["admission_sha256"],
            now=now.timestamp(),
        )
        self.store.append_once(
            "run_admitted",
            {"schema_version": 1, "spec": spec, "admission": {**admission, "reservation_id": reservation_id}},
            idempotency_key=f"run-admission:{spec['run_id']}",
        )
        return {**admission, "reservation_id": reservation_id}

    def complete_run(self, result: dict[str, Any]) -> dict[str, Any]:
        validate_result(result)
        state = self.state()
        if result["scout_id"] not in state["scouts"]:
            raise ValidationError("result references an unknown scout")
        existing = state["runs"].get(result["run_id"], {}).get("result")
        if existing is not None:
            if existing != result:
                raise ValidationError("run result identity was reused with different content")
            return result
        for reference in result["artifact_refs"]:
            self.artifacts.verify_reference(reference)
        run = state["runs"].get(result["run_id"], {})
        spec = run.get("spec")
        if spec is None:
            raise ValidationError("every result requires an immutable registered or admitted run spec")
        validate_result_binding(result, spec)
        if result["outcome_class"] in SCIENTIFIC_OUTCOMES and spec.get("telemetry_contract", {}).get(
            "scoring_mode"
        ) == "diagnostic_only":
            raise ValidationError("diagnostic-only runs cannot update scientific mechanism beliefs")
        if (
            result["outcome_class"] in DIAGNOSTIC_OUTCOMES
            and spec.get("execution_kind") != "local"
            and spec.get("telemetry_contract", {}).get("scoring_mode") != "diagnostic_only"
        ):
            raise ValidationError("diagnostic_valid requires a diagnostic-only telemetry contract")
        if spec is not None:
            if spec.get("execution_kind") == "local":
                self.store.append_once(
                    "run_completed",
                    result,
                    idempotency_key=f"run-result:{result['run_id']}",
                )
                return result
            manifest_sha256 = result.get("artifact_bundle_sha256")
            if manifest_sha256 is None or manifest_sha256 not in result["artifact_refs"]:
                raise ValidationError("an admitted run result must reference its artifact bundle")
            manifest = self.artifacts.verify_bundle(manifest_sha256, deep=True)
            expected_kind = "run" if result["outcome_class"] in SUCCESSFUL_OUTCOMES else "run_failure"
            if manifest.get("bundle_id") != result["run_id"] or manifest.get("kind") != expected_kind:
                raise ValidationError("result artifact bundle belongs to another run")
            expected_contract_sha256 = content_hash(spec["telemetry_contract"])
            if manifest.get("telemetry_contract_sha256") != expected_contract_sha256:
                raise ValidationError("result artifact bundle is bound to the wrong telemetry contract")
            from .evidence import validate_failure_evidence, validate_run_evidence

            derived_evidence = (
                validate_run_evidence(self.artifacts, manifest, spec)
                if result["outcome_class"] in SUCCESSFUL_OUTCOMES
                else validate_failure_evidence(
                    self.artifacts, manifest, spec, failure_class=result["failure_class"]
                )
            )
            if result["outcome_class"] in SUCCESSFUL_OUTCOMES:
                if abs(
                    float(result.get("observed_effect_fraction", derived_evidence["observed_effect_fraction"]))
                    - float(derived_evidence["observed_effect_fraction"])
                ) > 1e-9:
                    raise ValidationError("result effect differs from raw measurement evidence")
                if result["gates"] != derived_evidence["gates"]:
                    raise ValidationError("result gates differ from raw quality evidence")
            if abs(float(result["cost_usd"]) - float(derived_evidence["result_cost_usd"])) > 1e-9:
                raise ValidationError("result cost differs from raw cost evidence")
            summary = result.get("telemetry_summary")
            if result["outcome_class"] in SUCCESSFUL_OUTCOMES:
                summary = validate_telemetry_summary(summary, spec["telemetry_contract"])
            summary_entries = [
                entry for entry in manifest["entries"] if entry["role"] == "telemetry_summary"
            ]
            if len(summary_entries) != 1:
                raise ValidationError("result artifact bundle must contain one telemetry summary")
            stored_summary = self.artifacts.load_json_reference(summary_entries[0]["sha256"])
            if result["outcome_class"] in SUCCESSFUL_OUTCOMES:
                stored_summary = validate_telemetry_summary(stored_summary, spec["telemetry_contract"])
            if stored_summary != summary:
                raise ValidationError("result telemetry summary differs from its stored artifact")
            if result["outcome_class"] in SUCCESSFUL_OUTCOMES:
                if summary["missing_signals"]:
                    raise ValidationError("a successful result cannot omit planned telemetry")
                if spec["telemetry_contract"]["critical_path_method"] != "not_applicable":
                    if summary["correlation_status"] != "pass":
                        raise ValidationError("a successful result requires correlated telemetry")
                    coverage = summary["attribution_coverage"]
                    if coverage == "not_applicable" or coverage < spec["telemetry_contract"]["critical_path_coverage_gate"]:
                        raise ValidationError("a successful result misses its critical-path attribution gate")
                if spec["telemetry_contract"]["observer_effect"]["required"]:
                    if summary["observer_effect"]["status"] != "pass":
                        raise ValidationError("observer perturbation invalidates this successful result")
        self.store.append_once(
            "run_completed",
            result,
            idempotency_key=f"run-result:{result['run_id']}",
        )
        return result

    def write_state(self) -> Path:
        return self.store.write_state()

    def coordinator_context(self) -> str:
        return build_coordinator_context(self.state())

    def write_coordinator_context(self) -> Path:
        path = self.store.program_dir / "COORDINATOR.md"
        temporary = path.with_suffix(".md.tmp")
        temporary.write_text(self.coordinator_context())
        temporary.replace(path)
        return path
