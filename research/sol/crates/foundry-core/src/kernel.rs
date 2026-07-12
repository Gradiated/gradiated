use crate::artifact::ArtifactId;
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScalarType {
    Int2,
    Int3,
    Int4,
    Int8,
    Fp4,
    Fp8,
    Bf16,
    Fp16,
    Fp32,
}

impl ScalarType {
    pub fn bits(self) -> u8 {
        match self {
            Self::Int2 => 2,
            Self::Int3 => 3,
            Self::Int4 | Self::Fp4 => 4,
            Self::Int8 | Self::Fp8 => 8,
            Self::Bf16 | Self::Fp16 => 16,
            Self::Fp32 => 32,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum KernelOperation {
    Gemm,
    BatchedGemm,
    Attention,
    RmsNorm,
    RotaryEmbedding,
    Activation,
    Quantize,
    Dequantize,
    Collective,
    Custom(String),
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TensorLayout {
    RowMajor,
    ColumnMajor,
    Blocked { rows: u32, columns: u32 },
    Interleaved { group: u32 },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct KernelProblem {
    pub operation: KernelOperation,
    pub m: u64,
    pub n: u64,
    pub k: u64,
    pub batch: u32,
    pub sequence_length: u32,
    pub heads: u32,
    pub input_type: ScalarType,
    pub weight_type: ScalarType,
    pub output_type: ScalarType,
    pub accumulator_type: ScalarType,
    pub layout: TensorLayout,
}

impl KernelProblem {
    pub fn operations(&self) -> u128 {
        2 * u128::from(self.m) * u128::from(self.n) * u128::from(self.k) * u128::from(self.batch)
    }

    pub fn validate(&self) -> Result<(), KernelError> {
        if self.m == 0 || self.n == 0 || self.k == 0 || self.batch == 0 {
            return Err(KernelError::EmptyProblem);
        }
        match self.layout {
            TensorLayout::Blocked { rows, columns } if rows == 0 || columns == 0 => {
                Err(KernelError::InvalidLayout)
            }
            TensorLayout::Interleaved { group: 0 } => Err(KernelError::InvalidLayout),
            _ => Ok(()),
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum KernelLanguage {
    RustCuda,
    CudaCpp,
    Cutlass,
    Triton,
    TileLang,
    Rtl,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct KernelCandidate {
    pub name: String,
    pub language: KernelLanguage,
    pub source_artifact: ArtifactId,
    pub entrypoint: String,
    pub compiler_flags: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct KernelMeasurement {
    pub candidate: String,
    pub latency_ns: f64,
    pub energy_joules: f64,
    pub bytes_read: u64,
    pub bytes_written: u64,
    pub max_absolute_error: f64,
    pub max_relative_error: f64,
    pub backend: String,
    pub backend_version: String,
}

impl KernelMeasurement {
    pub fn validate(&self) -> Result<(), KernelError> {
        let finite = self.latency_ns.is_finite()
            && self.energy_joules.is_finite()
            && self.max_absolute_error.is_finite()
            && self.max_relative_error.is_finite();
        if !finite
            || self.latency_ns <= 0.0
            || self.energy_joules < 0.0
            || self.max_absolute_error < 0.0
            || self.max_relative_error < 0.0
        {
            return Err(KernelError::InvalidMeasurement);
        }
        if self.backend.trim().is_empty() || self.backend_version.trim().is_empty() {
            return Err(KernelError::MissingProvenance);
        }
        Ok(())
    }

    pub fn speedup_over(&self, baseline: &Self) -> Result<f64, KernelError> {
        self.validate()?;
        baseline.validate()?;
        Ok(baseline.latency_ns / self.latency_ns)
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct CorrectnessTolerance {
    pub max_absolute_error: f64,
    pub max_relative_error: f64,
}

impl CorrectnessTolerance {
    pub fn accepts(self, measurement: &KernelMeasurement) -> bool {
        measurement.validate().is_ok()
            && measurement.max_absolute_error <= self.max_absolute_error
            && measurement.max_relative_error <= self.max_relative_error
    }
}

pub trait KernelOracle {
    fn measure(
        &self,
        problem: &KernelProblem,
        candidate: &KernelCandidate,
        hardware: &ArtifactId,
    ) -> Result<KernelMeasurement, KernelError>;
}

#[derive(Debug, Error)]
pub enum KernelError {
    #[error("kernel problem dimensions must be non-zero")]
    EmptyProblem,
    #[error("kernel tensor layout is invalid")]
    InvalidLayout,
    #[error("kernel measurement contains an invalid value")]
    InvalidMeasurement,
    #[error("kernel measurement is missing backend provenance")]
    MissingProvenance,
    #[error("kernel backend failed: {0}")]
    Backend(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn measurement(latency_ns: f64) -> KernelMeasurement {
        KernelMeasurement {
            candidate: "candidate".into(),
            latency_ns,
            energy_joules: 0.001,
            bytes_read: 1024,
            bytes_written: 512,
            max_absolute_error: 0.001,
            max_relative_error: 0.002,
            backend: "cuda-benchmark".into(),
            backend_version: "1".into(),
        }
    }

    #[test]
    fn operation_count_includes_batch_and_fma() {
        let problem = KernelProblem {
            operation: KernelOperation::Gemm,
            m: 4,
            n: 8,
            k: 16,
            batch: 2,
            sequence_length: 0,
            heads: 0,
            input_type: ScalarType::Fp8,
            weight_type: ScalarType::Int4,
            output_type: ScalarType::Bf16,
            accumulator_type: ScalarType::Fp32,
            layout: TensorLayout::RowMajor,
        };

        assert_eq!(problem.operations(), 2048);
        assert_eq!(problem.weight_type.bits(), 4);
        assert!(problem.validate().is_ok());
    }

    #[test]
    fn correctness_and_speedup_require_valid_measurements() {
        let baseline = measurement(100.0);
        let candidate = measurement(40.0);
        let tolerance = CorrectnessTolerance {
            max_absolute_error: 0.01,
            max_relative_error: 0.01,
        };

        assert!(tolerance.accepts(&candidate));
        assert_eq!(candidate.speedup_over(&baseline).unwrap(), 2.5);
    }

    #[test]
    fn invalid_measurement_cannot_win() {
        let invalid = measurement(0.0);
        let baseline = measurement(100.0);

        assert!(matches!(
            invalid.speedup_over(&baseline),
            Err(KernelError::InvalidMeasurement)
        ));
    }
}
