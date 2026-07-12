use crate::kernel::{KernelOperation, KernelProblem, ScalarType, TensorLayout};
use crate::performance::PhaseWork;
use crate::spec::{ModelArchitecture, ModelSpec, Precision};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OperatorKind {
    Embedding,
    QkvProjection,
    Attention,
    OutputProjection,
    GateUpProjection,
    Activation,
    DownProjection,
    Normalization,
    LanguageModelHead,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct KernelInvocation {
    pub name: String,
    pub kind: OperatorKind,
    pub repetitions: u32,
    pub problem: KernelProblem,
    pub operations: u128,
    pub weight_bytes: u64,
    pub activation_read_bytes: u64,
    pub activation_write_bytes: u64,
    pub kv_read_bytes: u64,
    pub kv_write_bytes: u64,
}

impl KernelInvocation {
    pub fn total_bytes(&self) -> u64 {
        self.weight_bytes
            .saturating_add(self.activation_read_bytes)
            .saturating_add(self.activation_write_bytes)
            .saturating_add(self.kv_read_bytes)
            .saturating_add(self.kv_write_bytes)
    }
}

#[derive(Clone, Debug)]
pub struct ModelProgram {
    model: ModelSpec,
    raw_weight_elements: u128,
}

impl ModelProgram {
    pub fn new(model: &ModelSpec) -> Result<Self, ModelLoweringError> {
        if !matches!(model.architecture, ModelArchitecture::DenseDecoder) {
            return Err(ModelLoweringError::UnsupportedArchitecture);
        }
        if model.parameter_count == 0
            || model.layer_count == 0
            || model.hidden_size == 0
            || model.intermediate_size == 0
        {
            return Err(ModelLoweringError::InvalidModel);
        }
        let raw_weight_elements = raw_weight_elements(model)?;
        Ok(Self {
            model: model.clone(),
            raw_weight_elements,
        })
    }

    pub fn lower(&self, work: &PhaseWork) -> Result<Vec<KernelInvocation>, ModelLoweringError> {
        if work.batch_size == 0 || work.new_tokens == 0 {
            return Err(ModelLoweringError::EmptyWork);
        }

        let mut invocations = self.linear_invocations(work)?;
        invocations.insert(1, self.attention_invocation(work)?);
        invocations.push(self.activation_invocation(work)?);
        invocations.push(self.normalization_invocation(work)?);
        self.normalize_weight_bytes(&mut invocations)?;
        Ok(invocations)
    }

    fn linear_invocations(
        &self,
        work: &PhaseWork,
    ) -> Result<Vec<KernelInvocation>, ModelLoweringError> {
        let model = &self.model;
        let hidden = u64::from(model.hidden_size);
        let qkv_width = u64::from(
            model
                .attention_head_count
                .checked_add(model.kv_head_count.saturating_mul(2))
                .and_then(|heads| heads.checked_mul(model.head_dimension))
                .ok_or(ModelLoweringError::Overflow)?,
        );
        let intermediate = u64::from(model.intermediate_size);
        let vocabulary = u64::from(model.vocabulary_size);
        let layers = model.layer_count;

        Ok(vec![
            self.linear(
                "embedding",
                OperatorKind::Embedding,
                work,
                hidden,
                vocabulary,
                1,
            )?,
            self.linear(
                "qkv_projection",
                OperatorKind::QkvProjection,
                work,
                qkv_width,
                hidden,
                layers,
            )?,
            self.linear(
                "output_projection",
                OperatorKind::OutputProjection,
                work,
                hidden,
                hidden,
                layers,
            )?,
            self.linear(
                "gate_up_projection",
                OperatorKind::GateUpProjection,
                work,
                intermediate.saturating_mul(2),
                hidden,
                layers,
            )?,
            self.linear(
                "down_projection",
                OperatorKind::DownProjection,
                work,
                hidden,
                intermediate,
                layers,
            )?,
            self.linear(
                "language_model_head",
                OperatorKind::LanguageModelHead,
                work,
                vocabulary,
                hidden,
                1,
            )?,
        ])
    }

    fn linear(
        &self,
        name: &str,
        kind: OperatorKind,
        work: &PhaseWork,
        n: u64,
        k: u64,
        repetitions: u32,
    ) -> Result<KernelInvocation, ModelLoweringError> {
        let m = work.new_tokens;
        let problem = KernelProblem {
            operation: KernelOperation::Gemm,
            m,
            n,
            k,
            batch: 1,
            sequence_length: 0,
            heads: 0,
            input_type: ScalarType::Bf16,
            weight_type: scalar_type(self.model.weight_precision),
            output_type: ScalarType::Bf16,
            accumulator_type: ScalarType::Fp32,
            layout: TensorLayout::RowMajor,
        };
        let operations = problem
            .operations()
            .checked_mul(u128::from(repetitions))
            .ok_or(ModelLoweringError::Overflow)?;
        let activation_bytes = packed_bytes(
            u128::from(m)
                .checked_mul(u128::from(k))
                .ok_or(ModelLoweringError::Overflow)?,
            Precision::Bf16,
        )?;
        let output_bytes = packed_bytes(
            u128::from(m)
                .checked_mul(u128::from(n))
                .ok_or(ModelLoweringError::Overflow)?,
            Precision::Bf16,
        )?;
        let raw_elements = u128::from(n)
            .checked_mul(u128::from(k))
            .and_then(|value| value.checked_mul(u128::from(repetitions)))
            .ok_or(ModelLoweringError::Overflow)?;
        let weight_bytes = self.scaled_weight_bytes(raw_elements)?;

        Ok(KernelInvocation {
            name: name.into(),
            kind,
            repetitions,
            problem,
            operations,
            weight_bytes,
            activation_read_bytes: activation_bytes,
            activation_write_bytes: output_bytes,
            kv_read_bytes: 0,
            kv_write_bytes: 0,
        })
    }

    fn attention_invocation(
        &self,
        work: &PhaseWork,
    ) -> Result<KernelInvocation, ModelLoweringError> {
        let model = &self.model;
        let operations = u128::from(4_u8)
            .checked_mul(u128::from(model.layer_count))
            .and_then(|value| value.checked_mul(u128::from(model.hidden_size)))
            .and_then(|value| value.checked_mul(u128::from(work.attention_token_pairs)))
            .ok_or(ModelLoweringError::Overflow)?;
        let kv_per_token = model
            .kv_bytes_per_token()
            .ok_or(ModelLoweringError::Overflow)?;
        let kv_read_bytes = kv_per_token
            .checked_mul(work.attention_token_pairs)
            .ok_or(ModelLoweringError::Overflow)?;
        let kv_write_bytes = kv_per_token
            .checked_mul(work.new_tokens)
            .ok_or(ModelLoweringError::Overflow)?;
        let average_context = work
            .attention_token_pairs
            .checked_div(work.new_tokens)
            .unwrap_or_default();
        let sequence_length = u32::try_from(average_context).unwrap_or(u32::MAX);

        Ok(KernelInvocation {
            name: "attention".into(),
            kind: OperatorKind::Attention,
            repetitions: model.layer_count,
            problem: KernelProblem {
                operation: KernelOperation::Attention,
                m: work.new_tokens,
                n: average_context.max(1),
                k: u64::from(model.head_dimension),
                batch: work.batch_size,
                sequence_length,
                heads: model.attention_head_count,
                input_type: ScalarType::Bf16,
                weight_type: scalar_type(model.kv_precision),
                output_type: ScalarType::Bf16,
                accumulator_type: ScalarType::Fp32,
                layout: TensorLayout::Blocked {
                    rows: 16,
                    columns: 16,
                },
            },
            operations,
            weight_bytes: 0,
            activation_read_bytes: 0,
            activation_write_bytes: 0,
            kv_read_bytes,
            kv_write_bytes,
        })
    }

    fn activation_invocation(
        &self,
        work: &PhaseWork,
    ) -> Result<KernelInvocation, ModelLoweringError> {
        let elements = u128::from(work.new_tokens)
            .checked_mul(u128::from(self.model.intermediate_size))
            .and_then(|value| value.checked_mul(u128::from(self.model.layer_count)))
            .ok_or(ModelLoweringError::Overflow)?;
        let bytes = packed_bytes(elements, Precision::Bf16)?;
        Ok(KernelInvocation {
            name: "silu_multiply".into(),
            kind: OperatorKind::Activation,
            repetitions: self.model.layer_count,
            problem: KernelProblem {
                operation: KernelOperation::Activation,
                m: work.new_tokens,
                n: u64::from(self.model.intermediate_size),
                k: 1,
                batch: 1,
                sequence_length: 0,
                heads: 0,
                input_type: ScalarType::Bf16,
                weight_type: ScalarType::Bf16,
                output_type: ScalarType::Bf16,
                accumulator_type: ScalarType::Fp32,
                layout: TensorLayout::RowMajor,
            },
            operations: elements.saturating_mul(2),
            weight_bytes: 0,
            activation_read_bytes: bytes.saturating_mul(2),
            activation_write_bytes: bytes,
            kv_read_bytes: 0,
            kv_write_bytes: 0,
        })
    }

    fn normalization_invocation(
        &self,
        work: &PhaseWork,
    ) -> Result<KernelInvocation, ModelLoweringError> {
        let elements = u128::from(work.new_tokens)
            .checked_mul(u128::from(self.model.hidden_size))
            .and_then(|value| value.checked_mul(u128::from(self.model.layer_count)))
            .and_then(|value| value.checked_mul(2))
            .ok_or(ModelLoweringError::Overflow)?;
        let bytes = packed_bytes(elements, Precision::Bf16)?;
        Ok(KernelInvocation {
            name: "rms_norm".into(),
            kind: OperatorKind::Normalization,
            repetitions: self.model.layer_count.saturating_mul(2),
            problem: KernelProblem {
                operation: KernelOperation::RmsNorm,
                m: work.new_tokens,
                n: u64::from(self.model.hidden_size),
                k: 1,
                batch: 1,
                sequence_length: 0,
                heads: 0,
                input_type: ScalarType::Bf16,
                weight_type: ScalarType::Bf16,
                output_type: ScalarType::Bf16,
                accumulator_type: ScalarType::Fp32,
                layout: TensorLayout::RowMajor,
            },
            operations: elements.saturating_mul(5),
            weight_bytes: 0,
            activation_read_bytes: bytes,
            activation_write_bytes: bytes,
            kv_read_bytes: 0,
            kv_write_bytes: 0,
        })
    }

    fn scaled_weight_bytes(&self, raw_elements: u128) -> Result<u64, ModelLoweringError> {
        let total_weight_bytes = self
            .model
            .weight_bytes()
            .ok_or(ModelLoweringError::Overflow)?;
        let scaled = raw_elements
            .checked_mul(u128::from(total_weight_bytes))
            .ok_or(ModelLoweringError::Overflow)?
            .checked_div(self.raw_weight_elements)
            .ok_or(ModelLoweringError::InvalidModel)?;
        u64::try_from(scaled).map_err(|_| ModelLoweringError::Overflow)
    }

    fn normalize_weight_bytes(
        &self,
        invocations: &mut [KernelInvocation],
    ) -> Result<(), ModelLoweringError> {
        let expected = self
            .model
            .weight_bytes()
            .ok_or(ModelLoweringError::Overflow)?;
        let actual = invocations.iter().try_fold(0_u64, |sum, invocation| {
            sum.checked_add(invocation.weight_bytes)
                .ok_or(ModelLoweringError::Overflow)
        })?;
        let head = invocations
            .iter_mut()
            .find(|invocation| invocation.kind == OperatorKind::LanguageModelHead)
            .ok_or(ModelLoweringError::InvalidModel)?;
        if actual <= expected {
            head.weight_bytes = head
                .weight_bytes
                .checked_add(expected - actual)
                .ok_or(ModelLoweringError::Overflow)?;
        } else {
            head.weight_bytes = head
                .weight_bytes
                .checked_sub(actual - expected)
                .ok_or(ModelLoweringError::InvalidModel)?;
        }
        Ok(())
    }
}

fn raw_weight_elements(model: &ModelSpec) -> Result<u128, ModelLoweringError> {
    let hidden = u128::from(model.hidden_size);
    let qkv_width = u128::from(
        model
            .attention_head_count
            .checked_add(model.kv_head_count.saturating_mul(2))
            .and_then(|heads| heads.checked_mul(model.head_dimension))
            .ok_or(ModelLoweringError::Overflow)?,
    );
    let intermediate = u128::from(model.intermediate_size);
    let vocabulary = u128::from(model.vocabulary_size);
    let per_layer = hidden
        .checked_mul(qkv_width)
        .and_then(|value| value.checked_add(hidden.checked_mul(hidden)?))
        .and_then(|value| value.checked_add(hidden.checked_mul(intermediate)?.checked_mul(2)?))
        .and_then(|value| value.checked_add(intermediate.checked_mul(hidden)?))
        .ok_or(ModelLoweringError::Overflow)?;
    per_layer
        .checked_mul(u128::from(model.layer_count))
        .and_then(|value| value.checked_add(vocabulary.checked_mul(hidden)?.checked_mul(2)?))
        .ok_or(ModelLoweringError::Overflow)
}

fn packed_bytes(elements: u128, precision: Precision) -> Result<u64, ModelLoweringError> {
    let bits = elements
        .checked_mul(u128::from(precision.bits()))
        .ok_or(ModelLoweringError::Overflow)?;
    u64::try_from(bits.saturating_add(7) / 8).map_err(|_| ModelLoweringError::Overflow)
}

fn scalar_type(precision: Precision) -> ScalarType {
    match precision {
        Precision::Fp32 => ScalarType::Fp32,
        Precision::Bf16 => ScalarType::Bf16,
        Precision::Fp16 => ScalarType::Fp16,
        Precision::Fp8 => ScalarType::Fp8,
        Precision::Int8 => ScalarType::Int8,
        Precision::Int4 => ScalarType::Int4,
        Precision::Int3 => ScalarType::Int3,
        Precision::Int2 => ScalarType::Int2,
    }
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum ModelLoweringError {
    #[error("model architecture does not have an executable lowering")]
    UnsupportedArchitecture,
    #[error("model specification is invalid")]
    InvalidModel,
    #[error("phase work is empty")]
    EmptyWork,
    #[error("model lowering exceeded numeric limits")]
    Overflow,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::{ModelArchitecture, Precision};

    fn qwen(weight_precision: Precision) -> ModelSpec {
        ModelSpec {
            model_id: "Qwen/Qwen3-8B".into(),
            model_revision: "reference-fixture-v1".into(),
            architecture: ModelArchitecture::DenseDecoder,
            parameter_count: 8_200_000_000,
            layer_count: 36,
            hidden_size: 4_096,
            intermediate_size: 12_288,
            attention_head_count: 32,
            kv_head_count: 8,
            head_dimension: 128,
            vocabulary_size: 151_936,
            max_sequence_length: 32_768,
            weight_precision,
            quantized_weight_storage: (weight_precision.bits() < 8)
                .then(|| crate::spec::QuantizedWeightStorageSpec::grouped_all(128, 4, 16, 16, 0)),
            kv_precision: Precision::Fp16,
        }
    }

    #[test]
    fn lowering_preserves_checkpoint_weight_traffic() {
        let model = qwen(Precision::Int4);
        let program = ModelProgram::new(&model).unwrap();
        let invocations = program.lower(&PhaseWork::prefill(4, 512, 262_144)).unwrap();
        let weight_bytes: u64 = invocations.iter().map(|item| item.weight_bytes).sum();

        assert_eq!(weight_bytes, model.weight_bytes().unwrap());
        assert!(weight_bytes > model.parameter_count / 2);
        assert!(
            invocations
                .iter()
                .any(|item| { item.kind == OperatorKind::QkvProjection && item.repetitions == 36 })
        );
        assert!(
            invocations
                .iter()
                .any(|item| item.kind == OperatorKind::Attention)
        );
    }

    #[test]
    fn decode_kv_traffic_grows_with_context_without_rereading_more_weights() {
        let program = ModelProgram::new(&qwen(Precision::Int4)).unwrap();
        let short = program.lower(&PhaseWork::decode(8, 8 * 1_024)).unwrap();
        let long = program.lower(&PhaseWork::decode(8, 8 * 8_192)).unwrap();
        let sum = |items: &[KernelInvocation], select: fn(&KernelInvocation) -> u64| {
            items.iter().map(select).sum::<u64>()
        };

        assert_eq!(
            sum(&short, |item| item.weight_bytes),
            sum(&long, |item| item.weight_bytes)
        );
        assert_eq!(
            sum(&long, |item| item.kv_read_bytes),
            sum(&short, |item| item.kv_read_bytes) * 8
        );
    }

    #[test]
    fn lower_precision_reduces_weight_traffic() {
        let bf16 = ModelProgram::new(&qwen(Precision::Bf16))
            .unwrap()
            .lower(&PhaseWork::decode(1, 2_048))
            .unwrap();
        let int4 = ModelProgram::new(&qwen(Precision::Int4))
            .unwrap()
            .lower(&PhaseWork::decode(1, 2_048))
            .unwrap();
        let total =
            |items: &[KernelInvocation]| items.iter().map(|item| item.weight_bytes).sum::<u64>();

        assert_eq!(total(&int4), 4_228_125_000);
        assert_eq!(total(&bf16), 16_400_000_000);
        assert!(total(&int4) < total(&bf16));
    }

    #[test]
    fn phase_kind_does_not_change_static_program() {
        let program = ModelProgram::new(&qwen(Precision::Int4)).unwrap();
        let prefill = program.lower(&PhaseWork::prefill(1, 128, 16_384)).unwrap();
        let decode = program.lower(&PhaseWork::decode(1, 128)).unwrap();

        assert_eq!(prefill.len(), decode.len());
        assert_eq!(
            crate::performance::InferencePhase::Prefill,
            PhaseWork::prefill(1, 128, 16_384).phase
        );
    }
}
