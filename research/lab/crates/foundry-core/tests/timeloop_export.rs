use std::fs;
use std::path::Path;

use foundry_core::kernel::{KernelOperation, KernelProblem, ScalarType, TensorLayout};
use foundry_core::timeloop_export::{
    TimeloopExportError, TimeloopProblemExport, TimeloopProblemExporter,
};

fn gemm() -> KernelProblem {
    KernelProblem {
        operation: KernelOperation::Gemm,
        m: 2,
        n: 3,
        k: 4,
        batch: 5,
        sequence_length: 0,
        heads: 0,
        input_type: ScalarType::Bf16,
        weight_type: ScalarType::Bf16,
        output_type: ScalarType::Bf16,
        accumulator_type: ScalarType::Fp32,
        layout: TensorLayout::RowMajor,
    }
}

#[test]
fn exports_exact_batched_gemm_shape_and_accounting() {
    let export = TimeloopProblemExporter::export(&gemm()).unwrap();

    assert_eq!(export.accounting.multiply_accumulates, 120);
    assert_eq!(export.accounting.flops, 240);
    assert_eq!(export.accounting.input_elements, 40);
    assert_eq!(export.accounting.weight_elements, 12);
    assert_eq!(export.accounting.output_elements, 30);
    assert_eq!(export.accounting.input_bytes, 80);
    assert_eq!(export.accounting.weight_bytes, 24);
    assert_eq!(export.accounting.output_bytes, 60);
    assert_eq!(export.problem_dimensions.batch, 5);
    assert_eq!(export.problem_dimensions.m, 2);
    assert_eq!(export.problem_dimensions.n, 3);
    assert_eq!(export.problem_dimensions.k, 4);
    assert!(export.verify_content_id().unwrap());
    assert!(!export.backend_parse_verified);
}

#[test]
fn emits_deterministic_timeloop_v4_problem_yaml() {
    let first = TimeloopProblemExporter::export(&gemm()).unwrap();
    let second = TimeloopProblemExporter::export(&gemm()).unwrap();

    assert_eq!(first.content_id, second.content_id);
    assert_eq!(first.problem_yaml, second.problem_yaml);
    assert!(first.problem_yaml.starts_with("problem:\n  version: 0.4\n"));
    assert!(first.problem_yaml.contains("dimensions: [B, M, N, K]"));
    assert!(first.problem_yaml.contains(
        "- name: Inputs\n        projection:\n          - [[B]]\n          - [[M]]\n          - [[K]]"
    ));
    assert!(
        first
            .problem_yaml
            .contains("- name: Weights\n        projection:\n          - [[N]]\n          - [[K]]")
    );
    assert!(first.problem_yaml.contains(
        "- name: Outputs\n        projection:\n          - [[B]]\n          - [[M]]\n          - [[N]]"
    ));
    assert!(first.problem_yaml.contains("read_write: true"));
    assert!(first.problem_yaml.contains("B: 5"));
    assert!(first.problem_yaml.contains("M: 2"));
    assert!(first.problem_yaml.contains("N: 3"));
    assert!(first.problem_yaml.contains("K: 4"));
}

#[test]
fn unsupported_operation_and_layout_fail_closed() {
    let mut attention = gemm();
    attention.operation = KernelOperation::Attention;
    assert!(matches!(
        TimeloopProblemExporter::export(&attention),
        Err(TimeloopExportError::UnsupportedOperation)
    ));

    let mut column_major = gemm();
    column_major.layout = TensorLayout::ColumnMajor;
    assert!(matches!(
        TimeloopProblemExporter::export(&column_major),
        Err(TimeloopExportError::UnsupportedLayout)
    ));
}

#[test]
fn quantized_types_without_scale_metadata_fail_closed() {
    let mut quantized = gemm();
    quantized.weight_type = ScalarType::Int4;

    assert!(matches!(
        TimeloopProblemExporter::export(&quantized),
        Err(TimeloopExportError::QuantizationMetadataMissing)
    ));
}

#[test]
fn invalid_kernel_problem_is_rejected_before_export() {
    let mut empty = gemm();
    empty.m = 0;

    assert!(matches!(
        TimeloopProblemExporter::export(&empty),
        Err(TimeloopExportError::InvalidKernelProblem(_))
    ));
}

#[test]
fn checked_qwen_o_projection_problem_round_trips_exactly() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let problem: KernelProblem = serde_json::from_slice(
        &fs::read(root.join("configs/timeloop/qwen3-0.6b-o-proj-bf16-decode-b1-v1.json")).unwrap(),
    )
    .unwrap();
    let stored: TimeloopProblemExport = serde_json::from_slice(
        &fs::read(root.join("experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.json"))
            .unwrap(),
    )
    .unwrap();
    let stored_yaml = fs::read_to_string(
        root.join("experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.yaml"),
    )
    .unwrap();

    let generated = TimeloopProblemExporter::export(&problem).unwrap();

    assert_eq!(generated, stored);
    assert_eq!(generated.problem_yaml, stored_yaml);
    assert_eq!(generated.source_problem.operations(), 4_194_304);
    assert!(generated.verify_content_id().unwrap());
}
