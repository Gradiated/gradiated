use foundry_core::action_ledger::{ActionWork, EvidenceKind};
use foundry_core::glm_decode::{
    BoundSelection, BoundedDecodeWork, CompletenessBlocker, DecodeCacheState,
    DecodeCheckpointVariant, DecodeRouteInput, DecodeTokenCountScope, DecodeWorkload,
    ExplicitRouteAggregates, GLM_DECODE_LOWERING_REQUEST_SCHEMA_VERSION, GlmDecodeLoweringReport,
    GlmDecodeLoweringRequest, MtpDecodeInput, MtpDecodeWork, OpenU64Bounds,
    PinnedRouteReportSelection, WeightCachePolicy, evaluate_glm_decode_lowering,
};
use foundry_core::glm_storage::{
    ByteBounds, CheckpointPayloadEvidence, RoutedExpertStorageEvidence,
};
use foundry_core::spec::{ActiveParameterCount, Precision, glm_5_2_bf16_reference};
use std::fs;
use std::path::Path;

const BF16_PAYLOAD: u64 = 1_506_659_919_872;
const NVFP4_PAYLOAD: u64 = 464_794_806_272;
const NVFP4_REVISION: &str = "aec724e8c7b8ee9db3b48c01c320f63f9cdaf8aa";
const NVFP4_ROUTED_LOWER: u64 = 362_387_865_600;

#[test]
fn exact_ffn_parameters_flops_and_resident_bytes_reconcile() {
    let report = evaluate_glm_decode_lowering(&request()).unwrap();
    let result = &report.result;

    assert_eq!(
        result.active_parameters.released_active_parameter_count,
        ActiveParameterCount::Approximate {
            parameters: 40_000_000_000
        }
    );
    assert_eq!(
        result
            .active_parameters
            .exact_whole_model_active_parameter_count,
        None
    );
    assert_eq!(
        result
            .active_parameters
            .exact_active_routed_expert_parameter_count_per_candidate_token,
        22_649_241_600
    );
    assert_eq!(
        result
            .active_parameters
            .exact_active_shared_and_dense_ffn_parameter_count_per_candidate_token,
        3_510_632_448
    );
    assert_eq!(
        result
            .active_parameters
            .exact_active_ffn_parameter_count_per_candidate_token,
        26_159_874_048
    );
    assert_eq!(
        result.compute.exact_ffn_flops_per_candidate_token,
        52_319_748_096
    );
    assert_eq!(result.compute.exact_ffn_flops, 209_278_992_384);
    assert_eq!(
        result.weights.exact_ffn_resident_bytes,
        Some(1_456_572_727_296)
    );
    assert_eq!(
        result.weights.exact_non_ffn_resident_bytes,
        Some(50_087_192_576)
    );
    assert_eq!(
        result.weights.exact_dsa_indexer_resident_bytes,
        Some(393_619_968)
    );
}

#[test]
fn bounded_route_cache_attention_and_mtp_work_remain_bounded_in_ledgers() {
    let report = evaluate_glm_decode_lowering(&request()).unwrap();
    let result = &report.result;

    assert_eq!(result.route.total_dispatches, 2_400);
    assert_eq!(
        result.route.unique_routed_expert_instances,
        OpenU64Bounds::closed(600, 2_400)
    );
    assert_eq!(
        result.weights.routed_expert_hbm_read_bytes,
        OpenU64Bounds::closed(45_298_483_200, 181_193_932_800)
    );
    assert_eq!(
        result.weights.shared_and_dense_ffn_hbm_read_bytes,
        OpenU64Bounds::exact(7_021_264_896)
    );
    assert_ne!(
        result.lower_bound_ledger.content_id().unwrap(),
        result
            .upper_bound_ledger
            .as_ref()
            .unwrap()
            .content_id()
            .unwrap()
    );
    assert_eq!(
        result.hardware_study_ledger.as_ref().unwrap(),
        result.upper_bound_ledger.as_ref().unwrap()
    );
}

#[test]
fn opaque_nvfp4_storage_lowers_as_bounds_without_exact_layout_claims() {
    let report = evaluate_glm_decode_lowering(&nvfp4_request()).unwrap();
    let result = &report.result;

    assert_eq!(result.model_id, "nvidia/GLM-5.2-NVFP4");
    assert_eq!(result.model_revision, NVFP4_REVISION);
    assert_eq!(result.weights.exact_routed_expert_resident_bytes, None);
    assert_eq!(result.weights.exact_ffn_resident_bytes, None);
    assert_eq!(result.weights.exact_non_ffn_resident_bytes, None);
    assert_eq!(result.weights.exact_dsa_indexer_resident_bytes, None);
    assert_eq!(
        result.weights.routed_expert_resident_byte_bounds,
        Some(OpenU64Bounds::closed(NVFP4_ROUTED_LOWER, NVFP4_PAYLOAD))
    );
    assert_eq!(
        result.weights.average_routed_expert_storage_byte_bounds,
        Some(OpenU64Bounds::closed(18_874_368, 24_208_063))
    );
    assert_eq!(
        result.weights.non_routed_resident_byte_bounds,
        Some(OpenU64Bounds::closed(0, 102_406_940_672))
    );
    assert_eq!(
        result.weights.routed_expert_hbm_read_bytes,
        OpenU64Bounds::closed(0, NVFP4_PAYLOAD)
    );
    assert_eq!(
        result.weights.shared_and_dense_ffn_hbm_read_bytes,
        OpenU64Bounds::closed(0, 102_406_940_672)
    );
    assert_eq!(
        result.weights.total_ffn_hbm_read_bytes,
        OpenU64Bounds::closed(0, NVFP4_PAYLOAD)
    );
    let ffn_reads = ffn_weight_reads(result.upper_bound_ledger.as_ref().unwrap());
    assert_eq!(ffn_reads, vec![("opaque_ffn_weights_read", NVFP4_PAYLOAD)]);
    assert!(
        result
            .completeness
            .blockers
            .contains(&CompletenessBlocker::OpaqueCheckpointLayout)
    );
    assert!(!result.completeness.complete_hardware_timing_claim_permitted);
    assert!(!result.completeness.cost_per_token_claim_permitted);
    assert_eq!(
        result.completeness.checkpoint_quality_claim_permitted,
        Some(false)
    );
}

#[test]
fn opaque_nvfp4_reread_policy_caps_each_candidate_at_one_payload_pass() {
    let mut request = nvfp4_request();
    request.cache.weight_cache_policy = WeightCachePolicy::NoWeightReuseAcrossCandidateTokens;

    let report = evaluate_glm_decode_lowering(&request).unwrap();
    let weights = &report.result.weights;

    assert_eq!(
        weights.routed_expert_hbm_read_bytes,
        OpenU64Bounds::closed(0, NVFP4_PAYLOAD * 4)
    );
    assert_eq!(
        weights.shared_and_dense_ffn_hbm_read_bytes,
        OpenU64Bounds::closed(0, 102_406_940_672 * 4)
    );
    assert_eq!(
        weights.total_ffn_hbm_read_bytes,
        OpenU64Bounds::closed(0, NVFP4_PAYLOAD * 4)
    );
    assert_eq!(
        ffn_weight_reads(report.result.upper_bound_ledger.as_ref().unwrap()),
        vec![("opaque_ffn_weights_read", NVFP4_PAYLOAD * 4)]
    );
}

#[test]
fn emitted_hardware_ledger_contains_every_typed_action_class() {
    let report = evaluate_glm_decode_lowering(&request()).unwrap();
    let ledger = report.result.hardware_study_ledger.as_ref().unwrap();

    assert!(ledger.validate().is_ok());
    assert!(ledger.actions.iter().any(|action| action.is_compute()));
    assert!(ledger.actions.iter().any(|action| action.is_memory()));
    assert!(ledger.actions.iter().any(|action| action.is_cache()));
    assert!(ledger.actions.iter().any(|action| action.is_network()));
    assert!(
        ledger
            .actions
            .iter()
            .any(|action| action.is_synchronization())
    );
    assert!(ledger.actions.iter().any(|action| action.is_scheduler()));
    assert!(
        ledger
            .actions
            .iter()
            .all(|action| action.measurements.is_none())
    );
    assert!(
        ledger
            .actions
            .iter()
            .filter_map(|action| match &action.work {
                ActionWork::Compute(work) if work.label == "exact_glm_active_routed_expert_ffn" => {
                    Some(work.flops.get())
                }
                _ => None,
            })
            .all(|flops| flops == 181_193_932_800)
    );
}

#[test]
fn hardware_timing_and_cost_claims_stay_blocked() {
    let report = evaluate_glm_decode_lowering(&request()).unwrap();
    let completeness = &report.result.completeness;

    assert!(!completeness.work_bounds_collapsed);
    assert!(!completeness.all_actions_calibrated);
    assert!(!completeness.complete_hardware_timing_claim_permitted);
    assert!(!completeness.cost_per_token_claim_permitted);
    assert!(
        completeness
            .blockers
            .contains(&CompletenessBlocker::NonCollapsedWorkBounds)
    );
    assert!(
        completeness
            .blockers
            .contains(&CompletenessBlocker::MissingActionCalibration)
    );
    assert!(
        report
            .result
            .hardware_study_ledger
            .as_ref()
            .unwrap()
            .actions
            .iter()
            .any(|action| action.evidence.kind == EvidenceKind::Assumption)
    );
}

#[test]
fn pinned_route_report_selection_scales_with_conservative_integer_bounds() {
    let mut request = request();
    request.route = DecodeRouteInput::PinnedRouteReportSelection(PinnedRouteReportSelection {
        report_content_id: "a4c04217d6f8d41755f2134d2f6f4f1fd675945b383807efda75656ee092a1f2"
            .into(),
        scenario_id: "synthetic-source-affine-hotset".into(),
        topology_id: "modeled-fully-connected-8x".into(),
        strategy_id: "traffic-aware-primary-plus-1024-replicas".into(),
        sample_total_dispatches: 39_321_600,
        sample_remote_dispatches: 21_267_392,
        sample_endpoint_payload_bytes: 522_667_425_792,
        sample_endpoint_message_count: 266_752,
        sample_network_hop_payload_bytes: 522_667_425_792,
        sample_network_hop_message_count: 266_752,
        unique_routed_expert_instances: OpenU64Bounds::closed(600, 2_400),
        participants: 8,
        evidence: foundry_core::action_ledger::EvidenceProvenance {
            kind: EvidenceKind::Assumption,
            source_artifact_id: "experiments/glm-5.2/moe-route-skew-v1.json".into(),
        },
        basis: "selected modeled route strategy scaled to this decode step".into(),
    });

    let report = evaluate_glm_decode_lowering(&request).unwrap();

    assert_eq!(
        report.result.route.remote_dispatches,
        OpenU64Bounds::closed(1_298, 1_299)
    );
    assert_eq!(
        report.result.route.endpoint_payload_bytes,
        OpenU64Bounds::closed(31_899_648, 31_924_224)
    );
    assert_eq!(
        report.result.route.endpoint_message_count,
        OpenU64Bounds::closed(16, 17)
    );
    assert_eq!(
        report.result.route.network_hop_payload_bytes,
        report.result.route.endpoint_payload_bytes
    );
    assert_eq!(
        report.result.route.network_hop_message_count,
        report.result.route.endpoint_message_count
    );
    let pin = report.result.route.route_report_selection.as_ref().unwrap();
    assert_eq!(
        pin.report_content_id,
        "a4c04217d6f8d41755f2134d2f6f4f1fd675945b383807efda75656ee092a1f2"
    );
    assert_eq!(pin.scenario_id, "synthetic-source-affine-hotset");
    assert_eq!(pin.topology_id, "modeled-fully-connected-8x");
    assert_eq!(pin.strategy_id, "traffic-aware-primary-plus-1024-replicas");
}

#[test]
fn open_upper_work_prevents_an_upper_bound_hardware_ledger() {
    let mut request = request();
    request.attention_dsa.attention_flops.upper = None;

    let report = evaluate_glm_decode_lowering(&request).unwrap();

    assert!(report.result.upper_bound_ledger.is_none());
    assert!(report.result.hardware_study_ledger.is_none());
    assert!(
        report
            .result
            .completeness
            .blockers
            .contains(&CompletenessBlocker::OpenWorkBounds)
    );
}

#[test]
fn mismatched_checkpoint_route_and_bounds_are_rejected() {
    let mut checkpoint = request();
    checkpoint.checkpoint.checkpoint.payload_bytes -= 1;
    assert!(evaluate_glm_decode_lowering(&checkpoint).is_err());

    let mut route_request = request();
    let DecodeRouteInput::ExplicitAggregates(route) = &mut route_request.route else {
        panic!("expected explicit route aggregates")
    };
    route.total_dispatches -= 1;
    assert!(evaluate_glm_decode_lowering(&route_request).is_err());

    let mut bounds = request();
    bounds.attention_dsa.attention_flops = OpenU64Bounds::closed(200, 100);
    assert!(evaluate_glm_decode_lowering(&bounds).is_err());

    let mut active = request();
    let foundry_core::spec::ModelArchitecture::HybridMoeMlaDsa(hybrid) =
        &mut active.model.architecture
    else {
        panic!("expected hybrid model")
    };
    hybrid.active_parameter_count = ActiveParameterCount::Exact {
        parameters: 40_000_000_000,
    };
    assert!(evaluate_glm_decode_lowering(&active).is_err());

    let mut opaque_upper = nvfp4_request();
    let RoutedExpertStorageEvidence::OpaqueAggregateBounds { bytes, .. } =
        &mut opaque_upper.checkpoint.routed_expert_storage
    else {
        panic!("expected opaque routed-expert storage")
    };
    bytes.upper = NVFP4_PAYLOAD + 1;
    assert!(evaluate_glm_decode_lowering(&opaque_upper).is_err());

    let mut opaque_reversed = nvfp4_request();
    let RoutedExpertStorageEvidence::OpaqueAggregateBounds { bytes, .. } =
        &mut opaque_reversed.checkpoint.routed_expert_storage
    else {
        panic!("expected opaque routed-expert storage")
    };
    bytes.lower = bytes.upper + 1;
    assert!(evaluate_glm_decode_lowering(&opaque_reversed).is_err());

    let mut opaque_identity = nvfp4_request();
    opaque_identity.checkpoint.checkpoint.model_id = "nvidia/not-the-pinned-model".into();
    assert!(evaluate_glm_decode_lowering(&opaque_identity).is_err());
}

#[test]
fn schemas_and_report_identity_are_strict_and_stable() {
    let mut json = serde_json::to_value(request()).unwrap();
    json["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<GlmDecodeLoweringRequest>(json).is_err());

    let first = evaluate_glm_decode_lowering(&request()).unwrap();
    let second = evaluate_glm_decode_lowering(&request()).unwrap();
    assert_eq!(first.content_id, second.content_id);
    assert!(first.verify_content_id().unwrap());
}

#[test]
fn checked_whole_decode_artifact_reproduces_from_its_request() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request = serde_json::from_slice::<GlmDecodeLoweringRequest>(
        &fs::read(root.join("configs/glm-5.2-whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();
    let checked = serde_json::from_slice::<GlmDecodeLoweringReport>(
        &fs::read(root.join("experiments/glm-5.2/whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();

    let reproduced = evaluate_glm_decode_lowering(&request).unwrap();

    assert_eq!(reproduced, checked);
    assert!(checked.verify_content_id().unwrap());
    assert_eq!(checked.result.route.total_dispatches, 9_600);
    assert_eq!(checked.result.compute.exact_ffn_flops, 837_115_969_536);
    assert_eq!(checked.result.semantic_kv_resident_bytes, 11_777_605_632);
    assert_eq!(
        checked.result.compute.total_flops,
        OpenU64Bounds::closed(837_115_969_536, 3_387_115_969_536)
    );
    assert!(!checked.result.completeness.cost_per_token_claim_permitted);
    assert!(
        checked
            .result
            .hardware_study_ledger
            .as_ref()
            .unwrap()
            .actions
            .iter()
            .all(|action| action.measurements.is_none())
    );
}

#[test]
fn checked_nvfp4_whole_decode_artifact_reproduces_from_its_request() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request = serde_json::from_slice::<GlmDecodeLoweringRequest>(
        &fs::read(root.join("configs/glm-5.2-nvfp4-whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();
    let checked = serde_json::from_slice::<GlmDecodeLoweringReport>(
        &fs::read(root.join("experiments/glm-5.2/nvfp4-whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();

    let reproduced = evaluate_glm_decode_lowering(&request).unwrap();

    assert_eq!(reproduced, checked);
    assert!(checked.verify_content_id().unwrap());
    assert_eq!(
        checked.content_id,
        "de14e9be74e0f3a89baf3c09a94714d8a0aa72bde6221affe2235a5b74544845"
    );
    assert_eq!(checked.result.model_id, "nvidia/GLM-5.2-NVFP4");
    assert_eq!(checked.result.model_revision, NVFP4_REVISION);
    assert_eq!(
        checked.result.weights.total_ffn_hbm_read_bytes,
        OpenU64Bounds::closed(0, NVFP4_PAYLOAD)
    );
    assert!(
        checked
            .result
            .completeness
            .blockers
            .contains(&CompletenessBlocker::OpaqueCheckpointLayout)
    );
    assert_eq!(
        checked
            .result
            .completeness
            .checkpoint_quality_claim_permitted,
        Some(false)
    );
}

#[test]
fn zero_work_optional_actions_do_not_break_decode_stage_dependencies() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request = serde_json::from_slice::<GlmDecodeLoweringRequest>(
        &fs::read(root.join("configs/glm-5.2-whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();
    let report = evaluate_glm_decode_lowering(&request).unwrap();
    let lower = &report.result.lower_bound_ledger;
    let verify_schedule = lower
        .actions
        .iter()
        .find(|action| action.id.as_str() == "mtp_verify_schedule")
        .unwrap();

    assert!(
        verify_schedule
            .dependencies
            .iter()
            .any(|dependency| dependency.as_str() == "mtp_draft_schedule")
    );

    let mut disabled = request;
    disabled.mtp = MtpDecodeInput::Disabled(foundry_core::action_ledger::EvidenceProvenance {
        kind: EvidenceKind::ReleasedFact,
        source_artifact_id: "released:mtp-disabled-test".into(),
    });
    let report = evaluate_glm_decode_lowering(&disabled).unwrap();
    let commit = report
        .result
        .lower_bound_ledger
        .actions
        .iter()
        .find(|action| action.id.as_str() == "token_commit")
        .unwrap();

    assert!(
        commit
            .dependencies
            .iter()
            .any(|dependency| dependency.as_str() == "semantic_kv_store")
    );
}

fn request() -> GlmDecodeLoweringRequest {
    GlmDecodeLoweringRequest {
        schema_version: GLM_DECODE_LOWERING_REQUEST_SCHEMA_VERSION,
        lowering_id: "glm-decode-lowering-test".into(),
        model: glm_5_2_bf16_reference(),
        checkpoint: DecodeCheckpointVariant {
            variant_id: "glm-5.2-bf16".into(),
            checkpoint: CheckpointPayloadEvidence {
                model_id: "zai-org/GLM-5.2".into(),
                checkpoint_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
                payload_bytes: BF16_PAYLOAD,
                source_artifact_id: "glm-bf16-tensor-index".into(),
            },
            routed_expert_storage: RoutedExpertStorageEvidence::ModelSpecExact {
                source_artifact_id: "glm-bf16-config-and-index".into(),
            },
        },
        network_activation_precision: Precision::Bf16,
        workload: DecodeWorkload {
            batch_size: 2,
            context_tokens_per_request: 8_192,
            candidate_tokens: 4,
            committed_tokens: 3,
            token_count_scope: DecodeTokenCountScope::AggregateAcrossBatch,
            evidence_source_artifact_id: "synthetic:decode-workload-test".into(),
        },
        route: DecodeRouteInput::ExplicitAggregates(ExplicitRouteAggregates {
            total_dispatches: 2_400,
            unique_routed_expert_instances: OpenU64Bounds::closed(600, 2_400),
            remote_dispatches: OpenU64Bounds::closed(1_200, 1_800),
            endpoint_payload_bytes: OpenU64Bounds::closed(29_491_200, 44_236_800),
            endpoint_message_count: OpenU64Bounds::closed(2, 4_800),
            network_hop_payload_bytes: OpenU64Bounds::closed(29_491_200, 88_473_600),
            network_hop_message_count: OpenU64Bounds::closed(2, 9_600),
            participants: 8,
            evidence: foundry_core::action_ledger::EvidenceProvenance {
                kind: EvidenceKind::Assumption,
                source_artifact_id: "modeled:decode-route-test".into(),
            },
            basis: "bounded source-sharded top-8 route aggregate".into(),
        }),
        attention_dsa: BoundedDecodeWork {
            attention_flops: OpenU64Bounds::closed(100, 200),
            attention_non_flop_operations: OpenU64Bounds::closed(10, 20),
            attention_weight_bytes: OpenU64Bounds::closed(1_000, 2_000),
            activation_bytes: OpenU64Bounds::closed(500, 1_000),
            dsa_indexer_flops: OpenU64Bounds::closed(10, 20),
            dsa_indexer_weight_bytes: OpenU64Bounds::closed(100, 200),
            dsa_topk_non_flop_operations: OpenU64Bounds::closed(1_000, 2_000),
            other_non_ffn_flops: OpenU64Bounds::closed(30, 60),
            other_non_ffn_non_flop_operations: OpenU64Bounds::closed(40, 80),
            other_non_ffn_weight_bytes: OpenU64Bounds::closed(300, 600),
            evidence: foundry_core::action_ledger::EvidenceProvenance {
                kind: EvidenceKind::Assumption,
                source_artifact_id: "modeled:attention-dsa-test".into(),
            },
            basis: "finite test-only attention and indexer bounds".into(),
        },
        cache: DecodeCacheState {
            semantic_kv_read_bytes: OpenU64Bounds::closed(1_000, 2_000),
            semantic_kv_write_bytes: OpenU64Bounds::exact(500),
            dsa_index_lookup_bytes: OpenU64Bounds::closed(100, 200),
            dsa_index_store_bytes: OpenU64Bounds::closed(100, 200),
            dsa_index_lookup_hit: true,
            weight_cache_policy: WeightCachePolicy::UniqueWeightsLoadedOncePerDecodeStep,
            evidence: foundry_core::action_ledger::EvidenceProvenance {
                kind: EvidenceKind::Assumption,
                source_artifact_id: "modeled:cache-test".into(),
            },
            basis: "finite test-only cache bounds".into(),
        },
        mtp: MtpDecodeInput::Enabled(MtpDecodeWork {
            draft_tokens: 2,
            draft_flops: OpenU64Bounds::closed(300, 400),
            verification_flops: OpenU64Bounds::closed(500, 600),
            state_read_bytes: OpenU64Bounds::closed(100, 200),
            state_write_bytes: OpenU64Bounds::closed(100, 200),
            shares_dsa_indices: true,
            synchronization_participants: 2,
            evidence: foundry_core::action_ledger::EvidenceProvenance {
                kind: EvidenceKind::Assumption,
                source_artifact_id: "modeled:mtp-test".into(),
            },
            basis: "finite test-only MTP bounds".into(),
        }),
        hardware_study_bound: BoundSelection::Upper,
    }
}

fn nvfp4_request() -> GlmDecodeLoweringRequest {
    let mut request = request();
    request.lowering_id = "glm-5.2-nvidia-nvfp4-decode-lowering-test".into();
    request.model.model_id = "nvidia/GLM-5.2-NVFP4".into();
    request.model.model_revision = NVFP4_REVISION.into();
    request.checkpoint = DecodeCheckpointVariant {
        variant_id: "glm-5.2-nvidia-nvfp4-expert-selective".into(),
        checkpoint: CheckpointPayloadEvidence {
            model_id: request.model.model_id.clone(),
            checkpoint_revision: request.model.model_revision.clone(),
            payload_bytes: NVFP4_PAYLOAD,
            source_artifact_id: format!(
                "huggingface:nvidia/GLM-5.2-NVFP4@{NVFP4_REVISION}/model.safetensors.index.json"
            ),
        },
        routed_expert_storage: RoutedExpertStorageEvidence::OpaqueAggregateBounds {
            bytes: ByteBounds::new(NVFP4_ROUTED_LOWER, NVFP4_PAYLOAD),
            source_artifact_id: format!(
                "huggingface:nvidia/GLM-5.2-NVFP4@{NVFP4_REVISION}/model.safetensors.index.json"
            ),
            lower_bound_basis:
                "four packed payload bits per BF16-reference logical routed parameter".into(),
            upper_bound_basis: "routed tensors cannot exceed the checkpoint payload".into(),
        },
    };
    request
}

fn ffn_weight_reads(ledger: &foundry_core::action_ledger::ActionLedger) -> Vec<(&str, u64)> {
    ledger
        .actions
        .iter()
        .filter_map(|action| match &action.work {
            ActionWork::Memory(memory)
                if matches!(
                    action.id.as_str(),
                    "routed_expert_weights_read"
                        | "shared_dense_ffn_weights_read"
                        | "opaque_ffn_weights_read"
                ) =>
            {
                Some((action.id.as_str(), memory.bytes.get()))
            }
            _ => None,
        })
        .collect()
}
