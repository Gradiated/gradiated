use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::kernel::{KernelError, KernelOperation, KernelProblem, ScalarType, TensorLayout};

pub const TIMELOOP_EXPORT_SCHEMA_VERSION: u32 = 1;
pub const TIMELOOP_PROBLEM_SCHEMA_VERSION: &str = "0.4";
pub const TIMELOOP_EXPORTER_ID: &str = "foundry-core/timeloop-problem-export";
pub const TIMELOOP_EXPORTER_VERSION: &str = "1";
pub const TIMELOOP_PROBLEM_SCHEMA_URL: &str =
    "https://timeloop.csail.mit.edu/v4/input-formats/problem";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TimeloopProblemDimensions {
    pub batch: u32,
    pub m: u64,
    pub n: u64,
    pub k: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TimeloopTensorTypes {
    pub input: ScalarType,
    pub weight: ScalarType,
    pub output: ScalarType,
    pub accumulator: ScalarType,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TimeloopProblemAccounting {
    pub multiply_accumulates: u128,
    pub flops: u128,
    pub input_elements: u128,
    pub weight_elements: u128,
    pub output_elements: u128,
    pub input_bytes: u128,
    pub weight_bytes: u128,
    pub output_bytes: u128,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TimeloopProblemClaimGate {
    pub problem_contract_permitted: bool,
    pub backend_parse_verified: bool,
    pub mapping_claim_permitted: bool,
    pub cycle_claim_permitted: bool,
    pub utilization_claim_permitted: bool,
    pub energy_claim_permitted: bool,
    pub area_claim_permitted: bool,
    pub cost_claim_permitted: bool,
    pub blockers: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TimeloopProblemExport {
    pub schema_version: u32,
    pub content_id: String,
    pub exporter_id: String,
    pub exporter_version: String,
    pub timeloop_problem_schema_version: String,
    pub timeloop_problem_schema_url: String,
    pub source_problem: KernelProblem,
    pub problem_dimensions: TimeloopProblemDimensions,
    pub tensor_types: TimeloopTensorTypes,
    pub accounting: TimeloopProblemAccounting,
    pub problem_yaml: String,
    pub backend_parse_verified: bool,
    pub claims: TimeloopProblemClaimGate,
}

impl TimeloopProblemExport {
    pub fn verify_content_id(&self) -> Result<bool, TimeloopExportError> {
        Ok(self.content_id == content_id(self)?)
    }
}

pub struct TimeloopProblemExporter;

impl TimeloopProblemExporter {
    pub fn export(problem: &KernelProblem) -> Result<TimeloopProblemExport, TimeloopExportError> {
        problem
            .validate()
            .map_err(TimeloopExportError::InvalidKernelProblem)?;
        if !matches!(
            problem.operation,
            KernelOperation::Gemm | KernelOperation::BatchedGemm
        ) {
            return Err(TimeloopExportError::UnsupportedOperation);
        }
        if problem.layout != TensorLayout::RowMajor {
            return Err(TimeloopExportError::UnsupportedLayout);
        }
        if [
            problem.input_type,
            problem.weight_type,
            problem.output_type,
            problem.accumulator_type,
        ]
        .into_iter()
        .any(|scalar_type| {
            !matches!(
                scalar_type,
                ScalarType::Bf16 | ScalarType::Fp16 | ScalarType::Fp32
            )
        }) {
            return Err(TimeloopExportError::QuantizationMetadataMissing);
        }
        let dimensions = TimeloopProblemDimensions {
            batch: problem.batch,
            m: problem.m,
            n: problem.n,
            k: problem.k,
        };
        let input_elements = checked_product(&[
            u128::from(problem.batch),
            u128::from(problem.m),
            u128::from(problem.k),
        ])?;
        let weight_elements = checked_product(&[u128::from(problem.n), u128::from(problem.k)])?;
        let output_elements = checked_product(&[
            u128::from(problem.batch),
            u128::from(problem.m),
            u128::from(problem.n),
        ])?;
        let multiply_accumulates = checked_product(&[
            u128::from(problem.batch),
            u128::from(problem.m),
            u128::from(problem.n),
            u128::from(problem.k),
        ])?;
        let flops = multiply_accumulates
            .checked_mul(2)
            .ok_or(TimeloopExportError::AccountingOverflow)?;
        if flops != problem.operations() {
            return Err(TimeloopExportError::OperationCountMismatch);
        }
        let accounting = TimeloopProblemAccounting {
            multiply_accumulates,
            flops,
            input_elements,
            weight_elements,
            output_elements,
            input_bytes: packed_bytes(input_elements, problem.input_type)?,
            weight_bytes: packed_bytes(weight_elements, problem.weight_type)?,
            output_bytes: packed_bytes(output_elements, problem.output_type)?,
        };
        let problem_yaml = problem_yaml(dimensions);
        let mut export = TimeloopProblemExport {
            schema_version: TIMELOOP_EXPORT_SCHEMA_VERSION,
            content_id: String::new(),
            exporter_id: TIMELOOP_EXPORTER_ID.into(),
            exporter_version: TIMELOOP_EXPORTER_VERSION.into(),
            timeloop_problem_schema_version: TIMELOOP_PROBLEM_SCHEMA_VERSION.into(),
            timeloop_problem_schema_url: TIMELOOP_PROBLEM_SCHEMA_URL.into(),
            source_problem: problem.clone(),
            problem_dimensions: dimensions,
            tensor_types: TimeloopTensorTypes {
                input: problem.input_type,
                weight: problem.weight_type,
                output: problem.output_type,
                accumulator: problem.accumulator_type,
            },
            accounting,
            problem_yaml,
            backend_parse_verified: false,
            claims: claim_gate(),
        };
        export.content_id = content_id(&export)?;
        Ok(export)
    }
}

fn checked_product(values: &[u128]) -> Result<u128, TimeloopExportError> {
    values.iter().try_fold(1_u128, |product, value| {
        product
            .checked_mul(*value)
            .ok_or(TimeloopExportError::AccountingOverflow)
    })
}

fn packed_bytes(elements: u128, scalar_type: ScalarType) -> Result<u128, TimeloopExportError> {
    elements
        .checked_mul(u128::from(scalar_type.bits()))
        .and_then(|bits| bits.checked_add(7))
        .map(|bits| bits / 8)
        .ok_or(TimeloopExportError::AccountingOverflow)
}

fn problem_yaml(dimensions: TimeloopProblemDimensions) -> String {
    format!(
        "problem:\n  version: 0.4\n  shape:\n    name: FoundryGemmBMNK\n    dimensions: [B, M, N, K]\n    data_spaces:\n      - name: Inputs\n        projection:\n          - [[B]]\n          - [[M]]\n          - [[K]]\n      - name: Weights\n        projection:\n          - [[N]]\n          - [[K]]\n      - name: Outputs\n        projection:\n          - [[B]]\n          - [[M]]\n          - [[N]]\n        read_write: true\n  instance:\n    B: {}\n    M: {}\n    N: {}\n    K: {}\n",
        dimensions.batch, dimensions.m, dimensions.n, dimensions.k
    )
}

fn claim_gate() -> TimeloopProblemClaimGate {
    TimeloopProblemClaimGate {
        problem_contract_permitted: true,
        backend_parse_verified: false,
        mapping_claim_permitted: false,
        cycle_claim_permitted: false,
        utilization_claim_permitted: false,
        energy_claim_permitted: false,
        area_claim_permitted: false,
        cost_claim_permitted: false,
        blockers: vec![
            "timeloop_backend_not_invoked".into(),
            "architecture_mapping_and_mapper_inputs_missing".into(),
            "tensor_bit_widths_are_manifest_metadata_not_bound_to_architecture".into(),
            "backend_output_normalization_and_calibration_missing".into(),
        ],
    }
}

fn content_id(export: &TimeloopProblemExport) -> Result<String, TimeloopExportError> {
    let document = (
        export.schema_version,
        export.exporter_id.as_str(),
        export.exporter_version.as_str(),
        export.timeloop_problem_schema_version.as_str(),
        export.timeloop_problem_schema_url.as_str(),
        &export.source_problem,
        export.problem_dimensions,
        export.tensor_types,
        export.accounting,
        export.problem_yaml.as_str(),
        export.backend_parse_verified,
        &export.claims,
    );
    Ok(blake3::hash(&serde_json::to_vec(&document)?)
        .to_hex()
        .to_string())
}

#[derive(Debug, Error)]
pub enum TimeloopExportError {
    #[error("invalid kernel problem: {0}")]
    InvalidKernelProblem(#[source] KernelError),
    #[error("only GEMM and batched GEMM can be lowered to this Timeloop adapter")]
    UnsupportedOperation,
    #[error("only row-major kernel layouts are supported by this Timeloop adapter")]
    UnsupportedLayout,
    #[error("quantized tensor export requires explicit code, scale, and metadata storage")]
    QuantizationMetadataMissing,
    #[error("kernel operations do not reconcile with the Timeloop GEMM dimensions")]
    OperationCountMismatch,
    #[error("Timeloop problem accounting overflowed")]
    AccountingOverflow,
    #[error("Timeloop export content serialization failed: {0}")]
    ContentSerialization(#[from] serde_json::Error),
}
