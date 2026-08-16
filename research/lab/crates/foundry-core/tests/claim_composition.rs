use foundry_core::claim_composition::{
    ClaimEvidence, ClaimMetric, ClaimScope, CompositionExclusionReason, CompositionRequest,
    EvidenceClass, RelativeEffect, evaluate_claim_composition,
};

fn scope(model: &str) -> ClaimScope {
    ClaimScope {
        model_id: model.into(),
        model_revision: "revision-v1".into(),
        workload_id: "agentic-v1".into(),
        quality_contract_id: "quality-v1".into(),
        slo_contract_id: "slo-v1".into(),
        baseline_stack_id: "incumbent-v1".into(),
        candidate_stack_id: "candidate-v1".into(),
    }
}

fn evidence(
    id: &str,
    model: &str,
    interventions: &[&str],
    metric: ClaimMetric,
    class: EvidenceClass,
    claim_permitted: bool,
) -> ClaimEvidence {
    ClaimEvidence {
        evidence_id: id.into(),
        source_artifact_id: format!("artifact:{id}"),
        scope: scope(model),
        intervention_ids: interventions.iter().map(|value| (*value).into()).collect(),
        metric,
        relative_effect: RelativeEffect {
            lower: 0.1,
            upper: 0.2,
        },
        evidence_class: class,
        claim_permitted,
    }
}

#[test]
fn refuses_to_compose_marginal_bytes_and_synthetic_cost_into_end_to_end_cost() {
    let request = CompositionRequest {
        schema_version: 1,
        composition_id: "current-business-proof".into(),
        scope: scope("Qwen/Qwen3-0.6B"),
        requested_intervention_ids: vec!["selective_int4".into(), "kv_sharing".into()],
        objective: ClaimMetric::OutputCostPerMillionTokens,
        evidence: vec![
            evidence(
                "int4-bytes",
                "Qwen/Qwen3-0.6B",
                &["selective_int4"],
                ClaimMetric::WeightBytes,
                EvidenceClass::MeasuredComponent,
                true,
            ),
            evidence(
                "kv-bytes",
                "Qwen/Qwen3-0.6B",
                &["kv_sharing"],
                ClaimMetric::KvBytes,
                EvidenceClass::MeasuredQuality,
                false,
            ),
            evidence(
                "glm-pd-cost",
                "zai-org/GLM-5.2",
                &["selective_int4", "kv_sharing"],
                ClaimMetric::OutputCostPerMillionTokens,
                EvidenceClass::Analytical,
                false,
            ),
            evidence(
                "external-cycles",
                "Qwen/Qwen3-0.6B",
                &["selective_int4", "kv_sharing"],
                ClaimMetric::SimulatorCycles,
                EvidenceClass::ExternalSimulator,
                true,
            ),
        ],
    };

    let report = evaluate_claim_composition(&request).unwrap();

    assert!(!report.combined_claim_permitted);
    assert!(report.relative_effect.is_none());
    assert_eq!(report.admissible_evidence_ids, Vec::<String>::new());
    assert!(report.exclusions.iter().any(|exclusion| {
        exclusion.evidence_id == "int4-bytes"
            && exclusion
                .reasons
                .contains(&CompositionExclusionReason::MetricMismatch)
    }));
    assert!(report.exclusions.iter().any(|exclusion| {
        exclusion.evidence_id == "kv-bytes"
            && exclusion
                .reasons
                .contains(&CompositionExclusionReason::ClaimNotPermitted)
    }));
    assert!(report.exclusions.iter().any(|exclusion| {
        exclusion.evidence_id == "glm-pd-cost"
            && exclusion
                .reasons
                .contains(&CompositionExclusionReason::ScopeMismatch)
    }));
    assert!(report.exclusions.iter().any(|exclusion| {
        exclusion.evidence_id == "external-cycles"
            && exclusion
                .reasons
                .contains(&CompositionExclusionReason::MetricMismatch)
            && exclusion
                .reasons
                .contains(&CompositionExclusionReason::EvidenceClassInsufficient)
    }));
    assert!(report.verify_content_id().unwrap());
}

#[test]
fn permits_only_an_exact_scope_matched_end_to_end_joint_cost_claim() {
    let direct = evidence(
        "joint-cost",
        "Qwen/Qwen3-0.6B",
        &["selective_int4", "kv_sharing"],
        ClaimMetric::OutputCostPerMillionTokens,
        EvidenceClass::MeasuredEndToEnd,
        true,
    );
    let request = CompositionRequest {
        schema_version: 1,
        composition_id: "future-business-proof".into(),
        scope: scope("Qwen/Qwen3-0.6B"),
        requested_intervention_ids: vec!["kv_sharing".into(), "selective_int4".into()],
        objective: ClaimMetric::OutputCostPerMillionTokens,
        evidence: vec![direct],
    };

    let report = evaluate_claim_composition(&request).unwrap();

    assert!(report.combined_claim_permitted);
    assert_eq!(report.admissible_evidence_ids, vec!["joint-cost"]);
    assert_eq!(
        report.relative_effect,
        Some(RelativeEffect {
            lower: 0.1,
            upper: 0.2,
        })
    );
    assert!(report.exclusions.is_empty());
}

#[test]
fn exact_cost_claim_with_component_evidence_remains_blocked() {
    let request = CompositionRequest {
        schema_version: 1,
        composition_id: "component-only".into(),
        scope: scope("Qwen/Qwen3-0.6B"),
        requested_intervention_ids: vec!["selective_int4".into()],
        objective: ClaimMetric::InputCostPerMillionTokens,
        evidence: vec![evidence(
            "component-cost",
            "Qwen/Qwen3-0.6B",
            &["selective_int4"],
            ClaimMetric::InputCostPerMillionTokens,
            EvidenceClass::MeasuredComponent,
            true,
        )],
    };

    let report = evaluate_claim_composition(&request).unwrap();

    assert!(!report.combined_claim_permitted);
    assert!(
        report.exclusions[0]
            .reasons
            .contains(&CompositionExclusionReason::EvidenceClassInsufficient)
    );
}

#[test]
fn report_identity_binds_source_artifacts_and_effects() {
    let direct = evidence(
        "joint-cost",
        "Qwen/Qwen3-0.6B",
        &["selective_int4"],
        ClaimMetric::OutputCostPerMillionTokens,
        EvidenceClass::MeasuredEndToEnd,
        true,
    );
    let mut changed = direct.clone();
    changed.source_artifact_id = "artifact:replacement".into();
    changed.relative_effect.upper = 0.3;
    let make_request = |evidence| CompositionRequest {
        schema_version: 1,
        composition_id: "identity-proof".into(),
        scope: scope("Qwen/Qwen3-0.6B"),
        requested_intervention_ids: vec!["selective_int4".into()],
        objective: ClaimMetric::OutputCostPerMillionTokens,
        evidence: vec![evidence],
    };

    let first = evaluate_claim_composition(&make_request(direct)).unwrap();
    let second = evaluate_claim_composition(&make_request(changed)).unwrap();

    assert_ne!(first.request_content_id, second.request_content_id);
    assert_ne!(first.content_id, second.content_id);
}
