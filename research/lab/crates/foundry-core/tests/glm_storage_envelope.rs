use foundry_core::glm_storage::{
    ActiveTrafficEnvelope, BreakEvenThroughputAssumption, ByteBounds, CheckpointPayloadEvidence,
    DeviceCostAssumption, EnvelopeEvidence, EnvelopeEvidenceKind,
    GLM_STORAGE_ENVELOPE_REQUEST_SCHEMA_VERSION, GlmCheckpointVariant, GlmStorageEnvelopeReport,
    GlmStorageEnvelopeRequest, HardwareEnvelopeAssumption, MeasuredServingClaimEvidence,
    MemoryBandwidthAssumption, MemoryResidencyAssumptions, RoutedExpertStorageEvidence,
    evaluate_glm_storage_envelope,
};
use foundry_core::spec::glm_5_2_bf16_reference;
use std::fs;
use std::path::Path;

const BF16_PAYLOAD: u64 = 1_506_659_919_872;
const FP8_PAYLOAD: u64 = 755_617_140_416;
const NVFP4_PAYLOAD: u64 = 464_794_806_272;

#[test]
fn exact_payload_cache_and_expert_ledgers_remain_separate_from_opaque_layouts() {
    let report = evaluate_glm_storage_envelope(&request()).unwrap();

    assert!(report.verify_content_id().unwrap());
    assert_eq!(report.result.semantic_mla_cache_bytes_per_token, 89_856);
    assert_eq!(report.result.routed_expert_parameter_count, 724_775_731_200);
    assert_eq!(
        report.result.active_routed_expert_parameter_count_per_token,
        22_649_241_600
    );
    assert_eq!(report.result.routed_expert_layer_instance_count, 19_200);
    assert_eq!(
        report.result.active_routed_expert_layer_instances_per_token,
        600
    );

    let bf16 = variant(&report.result.variants, "glm-5.2-bf16");
    assert_eq!(bf16.checkpoint.payload_bytes, BF16_PAYLOAD);
    assert_eq!(
        bf16.routed_experts.resident_storage_bytes,
        ByteBounds::exact(1_449_551_462_400)
    );
    assert_eq!(
        bf16.routed_experts.per_layer_expert_storage_bytes,
        Some(ByteBounds::exact(75_497_472))
    );
    assert_eq!(
        bf16.routed_experts.active_storage_footprint_bytes_per_token,
        Some(ByteBounds::exact(45_298_483_200))
    );
    assert_eq!(bf16.residency.semantic_mla_cache_bytes, 1_797_120);
    assert_eq!(bf16.residency.extra_cache_bytes, ByteBounds::new(200, 400));
    assert_eq!(bf16.residency.indexer_cache_bytes, ByteBounds::new(0, 600));

    let fp8 = variant(&report.result.variants, "glm-5.2-fp8");
    assert_eq!(fp8.checkpoint.payload_bytes, FP8_PAYLOAD);
    assert_eq!(
        fp8.routed_experts.resident_storage_bytes,
        ByteBounds::new(724_775_731_200, FP8_PAYLOAD)
    );
    assert_eq!(fp8.routed_experts.per_layer_expert_storage_bytes, None);
    assert_eq!(
        fp8.routed_experts.active_storage_footprint_bytes_per_token,
        None
    );

    let nvfp4 = variant(&report.result.variants, "glm-5.2-nvfp4");
    assert_eq!(nvfp4.checkpoint.payload_bytes, NVFP4_PAYLOAD);
    assert_eq!(
        nvfp4.routed_experts.resident_storage_bytes,
        ByteBounds::new(362_387_865_600, NVFP4_PAYLOAD)
    );
    assert_eq!(nvfp4.routed_experts.per_layer_expert_storage_bytes, None);
}

#[test]
fn device_minima_and_uniform_expert_placement_are_checked_exactly() {
    let report = evaluate_glm_storage_envelope(&request()).unwrap();
    let bf16 = variant(&report.result.variants, "glm-5.2-bf16");
    let fp8 = variant(&report.result.variants, "glm-5.2-fp8");
    let nvfp4 = variant(&report.result.variants, "glm-5.2-nvfp4");
    let bf16_hardware = &bf16.hardware[0];

    assert_eq!(
        bf16_hardware.usable_memory_bytes_per_device,
        100_000_000_000
    );
    assert_eq!(bf16_hardware.minimum_devices_for_checkpoint_payload, 16);
    assert_eq!(bf16_hardware.minimum_devices_for_total_residency.lower, 17);
    assert_eq!(
        bf16_hardware
            .expert_placement
            .uniform_layer_expert_slots_per_device,
        Some(1_324)
    );
    assert_eq!(
        bf16_hardware
            .expert_placement
            .minimum_devices_for_uniform_layer_experts,
        Some(15)
    );
    assert_eq!(
        fp8.hardware[0]
            .expert_placement
            .uniform_layer_expert_slots_per_device,
        None
    );
    assert_eq!(fp8.hardware[0].minimum_devices_for_checkpoint_payload, 8);
    assert_eq!(nvfp4.hardware[0].minimum_devices_for_checkpoint_payload, 5);
}

#[test]
fn modeled_route_and_published_bandwidth_inputs_do_not_unlock_e2e_claims() {
    let report = evaluate_glm_storage_envelope(&request()).unwrap();
    let bf16 = variant(&report.result.variants, "glm-5.2-bf16");
    let hardware = &bf16.hardware[0];

    assert!(hardware.bandwidth.is_some());
    assert_eq!(
        hardware.claims.end_to_end_latency_seconds_per_output_token,
        None
    );
    assert_eq!(hardware.claims.cost_per_million_output_tokens_usd, None);
    assert!(!hardware.claims.blockers.is_empty());
    assert!(
        hardware
            .break_even
            .as_ref()
            .unwrap()
            .required_billable_tokens_per_second_for_deployment
            > 0.0
    );
}

#[test]
fn identical_requests_have_stable_report_identity() {
    let first = evaluate_glm_storage_envelope(&request()).unwrap();
    let second = evaluate_glm_storage_envelope(&request()).unwrap();

    assert_eq!(first.content_id, second.content_id);
}

#[test]
fn measured_route_bandwidth_and_serving_pins_unlock_only_the_supported_claims() {
    let mut request = request();
    request.variants.truncate(1);
    request.hardware.truncate(1);
    let traffic = request.variants[0].active_traffic.as_mut().unwrap();
    traffic.evidence = EnvelopeEvidence {
        kind: EnvelopeEvidenceKind::MeasuredHardware,
        source_artifact_id: "measured-route".into(),
    };
    request.hardware[0].bandwidth.evidence = EnvelopeEvidence {
        kind: EnvelopeEvidenceKind::MeasuredHardware,
        source_artifact_id: "measured-bandwidth".into(),
    };
    request.measured_serving_evidence = vec![MeasuredServingClaimEvidence {
        variant_id: "glm-5.2-bf16".into(),
        hardware_id: "test-100gb-18x".into(),
        output_tokens_per_second: foundry_core::glm_storage::FloatBounds::new(100.0, 120.0),
        end_to_end_latency_seconds_per_output_token: foundry_core::glm_storage::FloatBounds::new(
            0.008, 0.012,
        ),
        source_artifact_id: "measured-serving".into(),
        route_traffic_source_artifact_id: "measured-route".into(),
        bandwidth_source_artifact_id: "measured-bandwidth".into(),
    }];

    let report = evaluate_glm_storage_envelope(&request).unwrap();
    let claims = &report.result.variants[0].hardware[0].claims;

    assert_eq!(claims.blockers, Vec::new());
    assert_eq!(
        claims.end_to_end_latency_seconds_per_output_token,
        Some(foundry_core::glm_storage::FloatBounds::new(0.008, 0.012))
    );
    let cost = claims.cost_per_million_output_tokens_usd.unwrap();
    assert!((cost.lower - 291.666_666_666_666_7).abs() < 1e-9);
    assert!((cost.upper - 350.0).abs() < 1e-9);
}

#[test]
fn checked_in_glm_envelope_config_parses_and_evaluates() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let bytes = fs::read(root.join("configs/glm-5.2-storage-envelope-v1.json")).unwrap();
    let request: GlmStorageEnvelopeRequest = serde_json::from_slice(&bytes).unwrap();

    let report = evaluate_glm_storage_envelope(&request).unwrap();
    let stored: GlmStorageEnvelopeReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/storage-envelope-v1.json")).unwrap(),
    )
    .unwrap();

    assert_eq!(report.result.variants.len(), 3);
    assert_eq!(report.result.variants[0].hardware.len(), 3);
    assert_eq!(report, stored);
    assert!(stored.verify_content_id().unwrap());
    assert!(
        report
            .result
            .variants
            .iter()
            .flat_map(|variant| &variant.hardware)
            .all(|hardware| hardware.claims.cost_per_million_output_tokens_usd.is_none())
    );
}

#[test]
fn payload_overrides_and_opaque_bounds_fail_closed_without_evidence_pins() {
    let mut missing_pin = request();
    missing_pin.variants[1]
        .checkpoint
        .source_artifact_id
        .clear();
    assert!(evaluate_glm_storage_envelope(&missing_pin).is_err());

    let mut impossible_bounds = request();
    impossible_bounds.variants[1].routed_expert_storage =
        RoutedExpertStorageEvidence::OpaqueAggregateBounds {
            bytes: ByteBounds::new(FP8_PAYLOAD, FP8_PAYLOAD + 1),
            source_artifact_id: "fp8-index".into(),
            lower_bound_basis: "lower".into(),
            upper_bound_basis: "upper".into(),
        };
    assert!(evaluate_glm_storage_envelope(&impossible_bounds).is_err());
}

fn request() -> GlmStorageEnvelopeRequest {
    GlmStorageEnvelopeRequest {
        schema_version: GLM_STORAGE_ENVELOPE_REQUEST_SCHEMA_VERSION,
        study_id: "glm-storage-envelope-test".into(),
        model: glm_5_2_bf16_reference(),
        residency: MemoryResidencyAssumptions {
            checkpoint_replication_factor: 1,
            concurrent_sequences: 2,
            reserved_tokens_per_sequence: 10,
            cache_replication_factor: 1,
            extra_cache_bytes_per_token: ByteBounds::new(10, 20),
            indexer_cache_bytes_per_token: ByteBounds::new(0, 30),
            fixed_runtime_bytes: 1_000,
            fragmentation_overhead_basis_points: 1_000,
            source_artifact_id: "test-residency-assumptions".into(),
            basis: "test-only cache, runtime, and fragmentation assumptions".into(),
        },
        variants: vec![
            variant_request(
                "glm-5.2-bf16",
                "zai-org/GLM-5.2",
                "b4734de4facf877f85769a911abafc5283eab3d9",
                BF16_PAYLOAD,
                RoutedExpertStorageEvidence::ModelSpecExact {
                    source_artifact_id: "glm-bf16-index".into(),
                },
                ByteBounds::new(0, BF16_PAYLOAD),
            ),
            variant_request(
                "glm-5.2-fp8",
                "zai-org/GLM-5.2-FP8",
                "ba978f7d347eaf65d22f1a86833408afdb953541",
                FP8_PAYLOAD,
                RoutedExpertStorageEvidence::OpaqueAggregateBounds {
                    bytes: ByteBounds::new(724_775_731_200, FP8_PAYLOAD),
                    source_artifact_id: "glm-fp8-index".into(),
                    lower_bound_basis: "one byte per logical routed parameter".into(),
                    upper_bound_basis: "entire exact checkpoint payload".into(),
                },
                ByteBounds::new(0, FP8_PAYLOAD),
            ),
            variant_request(
                "glm-5.2-nvfp4",
                "nvidia/GLM-5.2-NVFP4",
                "aec724e8c7b8ee9db3b48c01c320f63f9cdaf8aa",
                NVFP4_PAYLOAD,
                RoutedExpertStorageEvidence::OpaqueAggregateBounds {
                    bytes: ByteBounds::new(362_387_865_600, NVFP4_PAYLOAD),
                    source_artifact_id: "glm-nvfp4-index".into(),
                    lower_bound_basis: "four packed bits per logical routed parameter".into(),
                    upper_bound_basis: "entire exact checkpoint payload".into(),
                },
                ByteBounds::new(0, NVFP4_PAYLOAD),
            ),
        ],
        hardware: vec![HardwareEnvelopeAssumption {
            hardware_id: "test-100gb-18x".into(),
            deployment_device_count: 18,
            device_memory_bytes: 100_000_000_000,
            reserved_device_memory_bytes: 0,
            memory_source_artifact_id: "test-memory".into(),
            bandwidth: MemoryBandwidthAssumption {
                peak_bytes_per_second_per_device: 1_000_000_000_000,
                efficiency_basis_points: 8_000,
                evidence: EnvelopeEvidence {
                    kind: EnvelopeEvidenceKind::PublishedSpecification,
                    source_artifact_id: "test-bandwidth".into(),
                },
            },
            cost: DeviceCostAssumption {
                usd_per_device_hour: 7.0,
                source_artifact_id: "test-cost".into(),
            },
        }],
        break_even: Some(BreakEvenThroughputAssumption {
            required_billable_tokens_per_second_per_usd_of_hourly_system_cost:
                2_409.558_640_979_693_3,
            source_artifact_id: "provider-economics#break_even_case".into(),
        }),
        measured_serving_evidence: Vec::new(),
    }
}

fn variant_request(
    variant_id: &str,
    model_id: &str,
    checkpoint_revision: &str,
    payload_bytes: u64,
    routed_expert_storage: RoutedExpertStorageEvidence,
    routed_traffic: ByteBounds,
) -> GlmCheckpointVariant {
    GlmCheckpointVariant {
        variant_id: variant_id.into(),
        checkpoint: CheckpointPayloadEvidence {
            model_id: model_id.into(),
            checkpoint_revision: checkpoint_revision.into(),
            payload_bytes,
            source_artifact_id: format!("{variant_id}-tensor-index"),
        },
        routed_expert_storage,
        active_traffic: Some(ActiveTrafficEnvelope {
            routed_expert_weight_bytes_per_output_token: routed_traffic,
            non_routed_weight_bytes_per_output_token: ByteBounds::new(0, payload_bytes),
            indexer_bytes_per_output_token: ByteBounds::new(0, 1_000_000),
            evidence: EnvelopeEvidence {
                kind: EnvelopeEvidenceKind::ModeledAssumption,
                source_artifact_id: format!("{variant_id}-traffic-assumption"),
            },
            basis: "single-pass conservative envelope; route locality is unknown".into(),
        }),
    }
}

fn variant<'a>(
    variants: &'a [foundry_core::glm_storage::GlmVariantEnvelopeReport],
    variant_id: &str,
) -> &'a foundry_core::glm_storage::GlmVariantEnvelopeReport {
    variants
        .iter()
        .find(|variant| variant.variant_id == variant_id)
        .unwrap()
}
