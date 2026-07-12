use foundry_core::action_ledger::ActionLedger;
use foundry_core::action_ledger::{
    ComputeClass, MemoryTier, SchedulerDecision, SynchronizationKind,
};
use foundry_core::glm_decode::GlmDecodeLoweringReport;
use foundry_core::ledger_roofline::{
    CacheTimingSpec, ComputeEngineSpec, HardwareExecutionBlocker, HardwareTimingEvidence,
    HardwareTimingEvidenceKind, LEDGER_ROOFLINE_REQUEST_SCHEMA_VERSION, LedgerHardwareTimingSpec,
    LedgerRooflineClaimBlocker, LedgerRooflineHardwarePlan, LedgerRooflineReport,
    LedgerRooflineRequest, MemoryPathTimingSpec, ModelFormatContract, ModelFormatSupportSpec,
    NetworkTimingSpec, SchedulerTimingSpec, SynchronizationTimingSpec, evaluate_ledger_roofline,
};
use std::fs;
use std::path::Path;

const GLM_LEDGER: &str = include_str!("fixtures/glm-5.2-decode-ledger-v1.json");

#[test]
fn dependency_critical_path_is_optimistic_and_custom_hardware_is_relative_to_baseline() {
    let report = evaluate_ledger_roofline(&request()).unwrap();
    let baseline = &report.result.hardware[0];
    let custom = &report.result.hardware[1];

    assert_eq!(baseline.hardware_id, "baseline");
    assert_eq!(baseline.action_timings.len(), 19);
    assert!(baseline.optimistic_critical_path_seconds <= baseline.serial_action_seconds);
    assert_eq!(baseline.relative_ideal_speedup_vs_baseline, 1.0);
    assert!(custom.optimistic_critical_path_seconds < baseline.optimistic_critical_path_seconds);
    assert!(custom.relative_ideal_speedup_vs_baseline > 1.0);
    assert_eq!(
        custom.relative_ideal_speedup_vs_baseline,
        baseline.optimistic_critical_path_seconds / custom.optimistic_critical_path_seconds
    );
    assert!(
        custom.optimistic_committed_tokens_per_second
            > baseline.optimistic_committed_tokens_per_second
    );
}

#[test]
fn every_action_requires_an_explicit_supported_hardware_path() {
    let mut missing_compute = request();
    missing_compute.hardware[0]
        .compute_engines
        .retain(|engine| engine.class != ComputeClass::TopK);
    assert!(evaluate_ledger_roofline(&missing_compute).is_err());

    let mut missing_memory = request();
    missing_memory.hardware[0].memory_paths.clear();
    assert!(evaluate_ledger_roofline(&missing_memory).is_err());

    let mut missing_cache = request();
    missing_cache.hardware[0].cache_tiers.clear();
    assert!(evaluate_ledger_roofline(&missing_cache).is_err());
}

#[test]
fn action_scoped_compute_engines_select_exact_actions_and_reject_overlap() {
    let mut scoped = request();
    let hardware = &mut scoped.hardware[0];
    let generic = hardware
        .compute_engines
        .iter()
        .position(|engine| engine.class == ComputeClass::MatrixMultiply)
        .map(|index| hardware.compute_engines.remove(index))
        .unwrap();
    let mut non_expert = generic.clone();
    non_expert.action_ids = Some(vec![
        "mla_decode".into(),
        "mtp_draft".into(),
        "mtp_verify".into(),
    ]);
    non_expert.flops_per_second = 10.0e12;
    let mut expert = generic;
    expert.action_ids = Some(vec!["moe_experts".into()]);
    expert.flops_per_second = 1.0e15;
    hardware.compute_engines.extend([non_expert, expert]);

    let report = evaluate_ledger_roofline(&scoped).unwrap();
    let timings = &report.result.hardware[0].action_timings;
    let expert = timings
        .iter()
        .find(|timing| timing.action_id == "moe_experts")
        .unwrap();
    let mla = timings
        .iter()
        .find(|timing| timing.action_id == "mla_decode")
        .unwrap();
    assert!(expert.throughput_component_seconds < mla.throughput_component_seconds);

    let mut overlapping = scoped;
    let engine = overlapping.hardware[0]
        .compute_engines
        .iter_mut()
        .find(|engine| engine.action_ids.as_ref().is_some_and(|ids| ids.len() == 1))
        .unwrap();
    engine
        .action_ids
        .as_mut()
        .unwrap()
        .push("mla_decode".into());
    assert!(evaluate_ledger_roofline(&overlapping).is_err());
}

#[test]
fn required_mixed_format_rejects_an_unsupported_baseline_and_blocks_counterfactuals() {
    let mut request = request();
    request.required_model_format = Some(ModelFormatContract::SelectiveExpertNvfp4);
    request.hardware[0].model_format_support = vec![format_support(true, "baseline")];
    request.hardware[1].model_format_support = vec![format_support(false, "custom")];

    let report = evaluate_ledger_roofline(&request).unwrap();
    let baseline = &report.result.hardware[0];
    let custom = &report.result.hardware[1];

    assert_eq!(
        baseline.required_model_format_support,
        Some(format_support(true, "baseline"))
    );
    assert!(baseline.execution_blockers.is_empty());
    assert_eq!(
        custom.required_model_format_support,
        Some(format_support(false, "custom"))
    );
    assert_eq!(
        custom.execution_blockers,
        vec![HardwareExecutionBlocker::RequiredModelFormatNotNativelySupported]
    );
    assert!(
        report
            .result
            .claims
            .blockers
            .contains(&LedgerRooflineClaimBlocker::HardwareExecutionUnsupported)
    );

    request.hardware[0].model_format_support = vec![format_support(false, "baseline")];
    assert!(evaluate_ledger_roofline(&request).is_err());
}

#[test]
fn modeled_roofline_never_unlocks_end_to_end_latency_energy_or_cost_claims() {
    let report = evaluate_ledger_roofline(&request()).unwrap();
    let claims = &report.result.claims;

    assert!(!claims.end_to_end_latency_claim_permitted);
    assert!(!claims.energy_claim_permitted);
    assert!(!claims.cost_per_token_claim_permitted);
    assert!(
        claims
            .blockers
            .contains(&LedgerRooflineClaimBlocker::LedgerContainsAssumptions)
    );
    assert!(
        claims
            .blockers
            .contains(&LedgerRooflineClaimBlocker::HardwareTimingIsNotCalibrated)
    );
    assert!(
        claims
            .blockers
            .contains(&LedgerRooflineClaimBlocker::SharedResourceContentionIsNotModeled)
    );
    assert!(
        claims
            .blockers
            .contains(&LedgerRooflineClaimBlocker::ServingAndQueueingAreNotModeled)
    );
}

#[test]
fn report_identity_is_stable_and_detects_tampering() {
    let first = evaluate_ledger_roofline(&request()).unwrap();
    let second = evaluate_ledger_roofline(&request()).unwrap();

    assert_eq!(first.content_id, second.content_id);
    assert!(first.verify_content_id().unwrap());
    let mut tampered = first;
    tampered.result.hardware[0].optimistic_critical_path_seconds += 1.0;
    assert!(!tampered.verify_content_id().unwrap());
}

#[test]
fn checked_in_glm_hardware_roofline_round_trips_exactly() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let plan: LedgerRooflineHardwarePlan = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-ledger-roofline-v1.json")).unwrap(),
    )
    .unwrap();
    let ledger = ActionLedger::from_json(GLM_LEDGER).unwrap();
    let stored: LedgerRooflineReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/decode-ledger-roofline-v1.json")).unwrap(),
    )
    .unwrap();
    let evaluated = evaluate_ledger_roofline(&plan.into_request(ledger)).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert_eq!(stored.result.hardware.len(), 2);
    assert!(stored.result.hardware[1].relative_ideal_speedup_vs_baseline > 5.0);
    assert!(!stored.result.claims.cost_per_token_claim_permitted);
}

#[test]
fn whole_decode_lowering_replaces_the_smoke_fixture_before_hardware_screening() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let plan: LedgerRooflineHardwarePlan = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-ledger-roofline-v1.json")).unwrap(),
    )
    .unwrap();
    let lowering: GlmDecodeLoweringReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();
    let stored: LedgerRooflineReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/whole-decode-ledger-roofline-v1.json")).unwrap(),
    )
    .unwrap();
    let ledger = lowering.result.hardware_study_ledger.unwrap();
    let accounting = ledger.accounting().unwrap();
    let evaluated = evaluate_ledger_roofline(&plan.into_request(ledger)).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert_eq!(accounting.flops.get(), 3_387_115_969_536);
    assert_eq!(stored.result.committed_tokens, 12);
    assert!(stored.result.hardware[1].relative_ideal_speedup_vs_baseline > 3.0);
    assert!(stored.result.hardware[1].relative_ideal_speedup_vs_baseline < 4.0);
    assert!(!stored.result.claims.end_to_end_latency_claim_permitted);
    assert!(!stored.result.claims.cost_per_token_claim_permitted);
}

#[test]
fn throughput_only_counterfactual_keeps_future_incumbent_in_the_comparison() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let plan: LedgerRooflineHardwarePlan = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-whole-decode-throughput-counterfactual-v1.json"))
            .unwrap(),
    )
    .unwrap();
    let lowering: GlmDecodeLoweringReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();
    let stored: LedgerRooflineReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/whole-decode-throughput-counterfactual-v1.json"))
            .unwrap(),
    )
    .unwrap();
    let ledger = lowering.result.hardware_study_ledger.unwrap();
    let evaluated = evaluate_ledger_roofline(&plan.into_request(ledger)).unwrap();
    let custom = &stored.result.hardware[1];
    let future_incumbent = &stored.result.hardware[2];

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert!(custom.relative_ideal_speedup_vs_baseline > 2.0);
    assert!(custom.relative_ideal_speedup_vs_baseline < 2.2);
    assert!(
        future_incumbent.optimistic_committed_tokens_per_second
            > custom.optimistic_committed_tokens_per_second
    );
    assert!(!stored.result.claims.cost_per_token_claim_permitted);
}

#[test]
fn nvfp4_blackwell_lower_and_upper_rooflines_round_trip_and_bracket_custom() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let plan: LedgerRooflineHardwarePlan = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-nvfp4-blackwell-roofline-v1.json")).unwrap(),
    )
    .unwrap();
    let lowering: GlmDecodeLoweringReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/nvfp4-whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();
    let stored_lower: LedgerRooflineReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/nvfp4-blackwell-roofline-lower-v1.json")).unwrap(),
    )
    .unwrap();
    let stored_upper: LedgerRooflineReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/nvfp4-blackwell-roofline-upper-v1.json")).unwrap(),
    )
    .unwrap();

    assert_eq!(
        plan.required_model_format,
        Some(ModelFormatContract::SelectiveExpertNvfp4)
    );
    assert!(
        plan.hardware
            .iter()
            .all(|hardware| !hardware.hardware_id.contains("h200"))
    );
    assert_blackwell_plan_rates(&plan);

    let evaluated_lower = evaluate_ledger_roofline(
        &plan
            .clone()
            .into_request(lowering.result.lower_bound_ledger.clone()),
    )
    .unwrap();
    let evaluated_upper = evaluate_ledger_roofline(
        &plan.into_request(lowering.result.upper_bound_ledger.clone().unwrap()),
    )
    .unwrap();

    assert_eq!(evaluated_lower, stored_lower);
    assert_eq!(evaluated_upper, stored_upper);
    assert!(stored_lower.verify_content_id().unwrap());
    assert!(stored_upper.verify_content_id().unwrap());
    assert_eq!(
        stored_lower.content_id,
        "df1218793c14fd749e208cd2005730f1a7aa27d108be75f6f0150b85d960960e"
    );
    assert_eq!(
        stored_upper.content_id,
        "8c245b30dbfc4a764ea4786f342c71f6cab11855422d6926bc45058171410d37"
    );
    assert_eq!(
        stored_lower.result.ledger_content_id,
        "685a946a02499d65dfaeb436a753fd4e917c85cc890f75f17e8833a8652076f6"
    );
    assert_eq!(
        stored_upper.result.ledger_content_id,
        "01a2b3549b8c7d558dd4e920f77a02657b59c08b2e622bc6caf86efba322f021"
    );

    let lower_custom = &stored_lower.result.hardware[2];
    let upper_custom = &stored_upper.result.hardware[2];
    assert!(lower_custom.relative_ideal_speedup_vs_baseline < 1.0);
    assert!(upper_custom.relative_ideal_speedup_vs_baseline > 1.3);
    assert_eq!(
        upper_custom.execution_blockers,
        vec![HardwareExecutionBlocker::RequiredModelFormatNotNativelySupported]
    );
    for report in [&stored_lower, &stored_upper] {
        assert!(!report.result.claims.end_to_end_latency_claim_permitted);
        assert!(!report.result.claims.energy_claim_permitted);
        assert!(!report.result.claims.cost_per_token_claim_permitted);
        assert!(
            report
                .result
                .claims
                .blockers
                .contains(&LedgerRooflineClaimBlocker::HardwareExecutionUnsupported)
        );
    }
}

fn request() -> LedgerRooflineRequest {
    LedgerRooflineRequest {
        schema_version: LEDGER_ROOFLINE_REQUEST_SCHEMA_VERSION,
        study_id: "ledger-roofline-test".into(),
        baseline_hardware_id: "baseline".into(),
        required_model_format: None,
        ledger: ActionLedger::from_json(GLM_LEDGER).unwrap(),
        hardware: vec![hardware("baseline", 1.0), hardware("custom", 2.0)],
    }
}

fn hardware(id: &str, multiplier: f64) -> LedgerHardwareTimingSpec {
    let evidence = HardwareTimingEvidence {
        kind: HardwareTimingEvidenceKind::ModeledAssumption,
        source_artifact_id: format!("{id}-modeled-timing"),
    };
    LedgerHardwareTimingSpec {
        hardware_id: id.into(),
        evidence: evidence.clone(),
        model_format_support: Vec::new(),
        compute_engines: vec![
            compute(ComputeClass::MatrixMultiply, multiplier, &evidence),
            compute(ComputeClass::AttentionScore, multiplier, &evidence),
            compute(ComputeClass::TopK, multiplier, &evidence),
        ],
        memory_paths: vec![MemoryPathTimingSpec {
            source: MemoryTier::Hbm,
            destination: MemoryTier::OnChip,
            bandwidth_bytes_per_second: 1.0e12 * multiplier,
            fixed_latency_seconds: 1.0e-6 / multiplier,
            evidence: evidence.clone(),
        }],
        cache_tiers: vec![CacheTimingSpec {
            tier: MemoryTier::OnChip,
            key_space: None,
            bandwidth_bytes_per_second: 10.0e12 * multiplier,
            fixed_latency_seconds: 0.2e-6 / multiplier,
            evidence: evidence.clone(),
        }],
        network: NetworkTimingSpec {
            aggregate_bandwidth_bytes_per_second: 100.0e9 * multiplier,
            fixed_latency_seconds: 1.0e-6 / multiplier,
            latency_seconds_per_message: 0.1e-6 / multiplier,
            evidence: evidence.clone(),
        },
        synchronization: SynchronizationTimingSpec {
            fixed_latency_seconds: 1.0e-6 / multiplier,
            latency_seconds_per_participant: 0.1e-6 / multiplier,
            supported_kinds: vec![SynchronizationKind::Barrier],
            evidence: evidence.clone(),
        },
        scheduler: SchedulerTimingSpec {
            fixed_latency_seconds: 1.0e-6 / multiplier,
            latency_seconds_per_request: 0.1e-6 / multiplier,
            latency_seconds_per_token: 0.01e-6 / multiplier,
            supported_decisions: vec![
                SchedulerDecision::BatchFormation,
                SchedulerDecision::ExpertRouting,
                SchedulerDecision::MtpDraft,
                SchedulerDecision::TokenCommit,
            ],
            evidence,
        },
    }
}

fn compute(
    class: ComputeClass,
    multiplier: f64,
    evidence: &HardwareTimingEvidence,
) -> ComputeEngineSpec {
    ComputeEngineSpec {
        class,
        action_ids: None,
        flops_per_second: 100.0e12 * multiplier,
        non_flop_operations_per_second: 10.0e9 * multiplier,
        fixed_latency_seconds: 1.0e-6 / multiplier,
        evidence: evidence.clone(),
    }
}

fn format_support(native: bool, source: &str) -> ModelFormatSupportSpec {
    ModelFormatSupportSpec {
        format: ModelFormatContract::SelectiveExpertNvfp4,
        native,
        evidence: HardwareTimingEvidence {
            kind: HardwareTimingEvidenceKind::PublishedSpecification,
            source_artifact_id: format!("{source}-format-support"),
        },
    }
}

fn assert_blackwell_plan_rates(plan: &LedgerRooflineHardwarePlan) {
    let b200 = &plan.hardware[0];
    let b300 = &plan.hardware[1];
    let custom = &plan.hardware[2];
    assert_eq!(action_rate(b200, "routed_expert_ffn"), 9.0e15);
    assert_eq!(action_rate(b300, "routed_expert_ffn"), 13.5e15);
    assert_eq!(action_rate(custom, "routed_expert_ffn"), 2.0e15);
    assert_eq!(action_rate(b200, "shared_dense_ffn"), 2.25e15);
    assert_eq!(action_rate(b300, "shared_dense_ffn"), 2.25e15);
    assert_eq!(action_rate(custom, "shared_dense_ffn"), 2.0e15);
    assert_eq!(b200.memory_paths[0].bandwidth_bytes_per_second, 8.0e12);
    assert_eq!(b300.memory_paths[0].bandwidth_bytes_per_second, 8.0e12);
    assert_eq!(custom.memory_paths[0].bandwidth_bytes_per_second, 12.0e12);
    assert_eq!(b200.network.aggregate_bandwidth_bytes_per_second, 1.8e12);
    assert_eq!(b300.network.aggregate_bandwidth_bytes_per_second, 1.8e12);
    assert_eq!(custom.network.aggregate_bandwidth_bytes_per_second, 1.6e12);
    for hardware in &plan.hardware {
        assert!(
            hardware
                .compute_engines
                .iter()
                .all(|engine| engine.fixed_latency_seconds
                    == if engine.class == ComputeClass::TopK {
                        5.0e-6
                    } else {
                        4.0e-6
                    })
        );
        assert!(
            hardware
                .memory_paths
                .iter()
                .all(|path| path.fixed_latency_seconds == 1.0e-6)
        );
        assert_eq!(hardware.network.fixed_latency_seconds, 1.0e-6);
        assert_eq!(hardware.network.latency_seconds_per_message, 0.3e-6);
        assert_eq!(hardware.synchronization.fixed_latency_seconds, 0.5e-6);
        assert_eq!(hardware.scheduler.fixed_latency_seconds, 1.0e-6);
    }
}

fn action_rate(hardware: &LedgerHardwareTimingSpec, action_id: &str) -> f64 {
    hardware
        .compute_engines
        .iter()
        .find(|engine| {
            engine
                .action_ids
                .as_ref()
                .is_some_and(|ids| ids.iter().any(|candidate| candidate == action_id))
        })
        .unwrap()
        .flops_per_second
}
