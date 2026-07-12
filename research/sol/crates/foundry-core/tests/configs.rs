use foundry_core::codesign::{ModelChange, ModelVariant, QualityEvidence};
use foundry_core::spec::ExperimentSpec;
use std::fs;
use std::path::{Path, PathBuf};

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("core crate must be inside the workspace")
        .to_path_buf()
}

fn load(name: &str) -> ExperimentSpec {
    let path = workspace_root().join("configs").join(name);
    let bytes = fs::read(path).expect("configuration must be readable");
    serde_json::from_slice(&bytes).expect("configuration must match the experiment schema")
}

fn load_variant(name: &str) -> ModelVariant {
    let path = workspace_root().join("configs/variants").join(name);
    let bytes = fs::read(path).expect("variant configuration must be readable");
    serde_json::from_slice(&bytes).expect("configuration must match the model variant schema")
}

#[test]
fn checked_in_experiments_parse_and_validate() {
    for name in [
        "qwen3-8b-agentic-h100.json",
        "qwen3-8b-agentic-custom-asic.json",
    ] {
        let spec = load(name);
        spec.validate()
            .unwrap_or_else(|errors| panic!("{name} failed validation: {:?}", errors.errors));
    }
}

#[test]
fn baseline_and_custom_hardware_share_the_comparison_contract() {
    let baseline = load("qwen3-8b-agentic-h100.json");
    let custom = load("qwen3-8b-agentic-custom-asic.json");

    assert_eq!(baseline.model.model_id, custom.model.model_id);
    assert_eq!(baseline.model.model_revision, custom.model.model_revision);
    assert_eq!(baseline.model.architecture, custom.model.architecture);
    assert_eq!(baseline.model.parameter_count, custom.model.parameter_count);
    assert_eq!(baseline.workload, custom.workload);
    assert_eq!(baseline.quality_constraints, custom.quality_constraints);
    assert_eq!(baseline.quality_suite_id, custom.quality_suite_id);
    assert_eq!(
        baseline.serving.ttft_slo_milliseconds,
        custom.serving.ttft_slo_milliseconds
    );
    assert_eq!(
        baseline.serving.tpot_slo_milliseconds,
        custom.serving.tpot_slo_milliseconds
    );
}

#[test]
fn qwen_w4_configs_declare_group_128_fp16_scale_storage_without_quality_claims() {
    let baseline = load("qwen3-8b-agentic-h100.json");
    for name in [
        "qwen3-8b-w4.json",
        "qwen3-8b-w4-kv8.json",
        "qwen3-8b-paired-v0.json",
    ] {
        let variant = load_variant(name);
        let storage = variant
            .changes
            .iter()
            .find_map(|change| match change {
                ModelChange::WeightPrecision {
                    quantized_storage, ..
                } => quantized_storage.as_ref(),
                _ => None,
            })
            .expect("W4 change must declare storage");

        assert_eq!(storage.group_size, 128);
        assert_eq!(storage.code_bits, 4);
        assert_eq!(storage.scale_bits, 16);
        assert_eq!(storage.payload_bits_per_quantized_weight(), Some(4.125));
        assert_eq!(variant.quality, QualityEvidence::Unvalidated);
        let effective = variant.apply(&baseline.model).unwrap();
        assert!(effective.model.weight_bytes().unwrap() > effective.model.parameter_count / 2);
    }

    let custom = load("qwen3-8b-agentic-custom-asic.json");
    assert_eq!(custom.model.weight_bytes(), Some(4_228_125_000));
}
