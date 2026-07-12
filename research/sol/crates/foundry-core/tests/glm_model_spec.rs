use foundry_core::model::{ModelLoweringError, ModelProgram};
use foundry_core::sizing::{HardwareSizer, HardwareSizingConstraints, SizingError};
use foundry_core::spec::{
    ActiveParameterCount, HybridMoeMlaDsaSpec, ModelArchitecture, ModelSpec, Precision,
    QuantizedWeightStorageSpec, glm_5_2_bf16_reference,
};

#[test]
fn pinned_glm_fixture_separates_resident_and_approximate_active_parameters() {
    let model = glm_5_2_bf16_reference();

    assert!(model.validate().is_ok());
    assert_eq!(model.parameter_count, 753_329_940_480);
    assert_eq!(model.reported_active_parameter_count(), 40_000_000_000);
    assert_eq!(model.exact_active_parameter_count(), None);
    assert_eq!(model.weight_bytes(), Some(1_506_659_919_872));
    assert_eq!(model.active_weight_bytes(), None);
    assert_eq!(model.semantic_kv_bytes_per_token(), Some(89_856));
    assert_eq!(model.kv_bytes_per_token(), None);
    assert!(!model.has_complete_kv_cache_accounting());
}

#[test]
fn glm_feed_forward_and_indexer_ledgers_use_exact_checked_arithmetic() {
    let model = glm_5_2_bf16_reference();

    assert_eq!(model.routed_expert_parameter_count(), Some(724_775_731_200));
    assert_eq!(
        model.active_routed_expert_parameter_count(),
        Some(22_649_241_600)
    );
    assert_eq!(model.shared_expert_parameter_count(), Some(2_831_155_200));
    assert_eq!(model.dense_mlp_parameter_count(), Some(679_477_248));
    assert_eq!(
        model.stored_feed_forward_parameter_count(),
        Some(728_286_363_648)
    );
    assert_eq!(
        model.active_feed_forward_parameter_count_per_token(),
        Some(26_159_874_048)
    );
    assert_eq!(
        model.active_feed_forward_flops_per_token(),
        Some(52_319_748_096)
    );
    assert_eq!(
        model.dsa_indexer_parameters_per_full_layer(),
        Some(9_371_904)
    );
    assert_eq!(model.dsa_indexer_parameter_count(), Some(196_809_984));
}

#[test]
fn routed_expert_storage_can_differ_from_non_expert_storage() {
    let mut model = glm_5_2_bf16_reference();
    let hybrid = hybrid_mut(&mut model);
    hybrid.moe.routed_expert_weight_precision = Precision::Int4;
    hybrid.moe.routed_expert_quantized_weight_storage =
        Some(QuantizedWeightStorageSpec::grouped_all(128, 4, 16, 16, 0));
    let routed = 724_775_731_200_u128;
    let non_routed = u128::from(model.parameter_count) - routed;
    let expected_bits = non_routed * 16 + routed * 4 + routed.div_ceil(128) * 16 + 38_912 * 8;

    assert!(model.validate().is_ok());
    assert_eq!(model.weight_storage_bits(), Some(expected_bits));
    assert_eq!(model.weight_bytes(), u64::try_from(expected_bits / 8).ok());
}

#[test]
fn hybrid_validation_rejects_inconsistent_layer_routing_attention_and_indexing_geometry() {
    let mut layers = glm_5_2_bf16_reference();
    hybrid_mut(&mut layers).moe_layer_count = 74;
    assert!(
        layers
            .validate()
            .unwrap_err()
            .has_field("model.architecture.layer_counts")
    );

    let mut routing = glm_5_2_bf16_reference();
    hybrid_mut(&mut routing).moe.routed_experts_per_token = 257;
    assert!(
        routing
            .validate()
            .unwrap_err()
            .has_field("model.architecture.moe.routed_experts_per_token")
    );

    let mut attention = glm_5_2_bf16_reference();
    hybrid_mut(&mut attention).mla.rotary_kv_dimension = 63;
    assert!(
        attention
            .validate()
            .unwrap_err()
            .has_field("model.head_dimension")
    );

    let mut indexers = glm_5_2_bf16_reference();
    hybrid_mut(&mut indexers).dsa_indexer.shared_layer_count = 56;
    assert!(
        indexers
            .validate()
            .unwrap_err()
            .has_field("model.architecture.dsa_indexer.layer_counts")
    );
}

#[test]
fn tensor_inventory_cannot_be_replaced_by_the_active_release_label() {
    let mut model = glm_5_2_bf16_reference();
    model.parameter_count = 40_000_000_000;

    assert!(
        model
            .validate()
            .unwrap_err()
            .has_field("model.parameter_count")
    );
}

#[test]
fn hybrid_parameter_arithmetic_fails_closed_on_overflow() {
    let mut model = glm_5_2_bf16_reference();
    model.hidden_size = u32::MAX;
    hybrid_mut(&mut model).moe.expert_intermediate_size = u32::MAX;

    assert_eq!(model.routed_expert_parameter_count(), None);
    assert_eq!(model.weight_storage_bits(), None);
    assert!(
        model
            .validate()
            .unwrap_err()
            .has_field("model.parameter_count")
    );
}

#[test]
fn dense_decoder_serialization_and_accounting_remain_compatible() {
    let model = dense_model();
    let json = serde_json::to_value(&model).unwrap();
    let round_trip = serde_json::from_value::<ModelSpec>(json.clone()).unwrap();

    assert_eq!(json["architecture"], "dense_decoder");
    assert_eq!(round_trip, model);
    assert_eq!(
        model.reported_active_parameter_count(),
        model.parameter_count
    );
    assert_eq!(
        model.exact_active_parameter_count(),
        Some(model.parameter_count)
    );
    assert_eq!(model.active_weight_bytes(), model.weight_bytes());
    assert_eq!(model.kv_bytes_per_token(), Some(256));
}

#[test]
fn model_and_hybrid_schemas_reject_unknown_fields() {
    let model = glm_5_2_bf16_reference();
    let mut model_json = serde_json::to_value(&model).unwrap();
    model_json["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<ModelSpec>(model_json).is_err());

    let mut hybrid_json = serde_json::to_value(model.architecture).unwrap();
    hybrid_json["hybrid_moe_mla_dsa"]["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<ModelArchitecture>(hybrid_json).is_err());
}

#[test]
fn unsupported_hybrid_performance_paths_fail_instead_of_using_all_resident_parameters() {
    let model = glm_5_2_bf16_reference();

    assert!(matches!(
        ModelProgram::new(&model),
        Err(ModelLoweringError::UnsupportedArchitecture)
    ));
    assert!(matches!(
        HardwareSizer.synthesize(&model, &HardwareSizingConstraints::default()),
        Err(SizingError::UnsupportedModelArchitecture)
    ));
}

fn hybrid_mut(model: &mut ModelSpec) -> &mut HybridMoeMlaDsaSpec {
    match &mut model.architecture {
        ModelArchitecture::HybridMoeMlaDsa(hybrid) => hybrid,
        ModelArchitecture::DenseDecoder => panic!("expected hybrid architecture"),
    }
}

fn dense_model() -> ModelSpec {
    ModelSpec {
        model_id: "dense/reference".into(),
        model_revision: "dense-revision".into(),
        architecture: ModelArchitecture::DenseDecoder,
        parameter_count: 1_000_000,
        layer_count: 2,
        hidden_size: 64,
        intermediate_size: 128,
        attention_head_count: 4,
        kv_head_count: 2,
        head_dimension: 16,
        vocabulary_size: 1_000,
        max_sequence_length: 4_096,
        weight_precision: Precision::Bf16,
        quantized_weight_storage: None,
        kv_precision: Precision::Bf16,
    }
}

#[test]
fn active_parameter_evidence_remains_explicitly_approximate() {
    let model = glm_5_2_bf16_reference();
    let ModelArchitecture::HybridMoeMlaDsa(hybrid) = model.architecture else {
        panic!("expected hybrid architecture")
    };

    assert_eq!(
        hybrid.active_parameter_count,
        ActiveParameterCount::Approximate {
            parameters: 40_000_000_000
        }
    );
}
