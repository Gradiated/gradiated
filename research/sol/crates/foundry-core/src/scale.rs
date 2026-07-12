use crate::spec::{Precision, QuantizedWeightStorageSpec, stored_weight_bytes};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ModelScaleContract {
    pub model_id: String,
    pub model_revision: String,
    pub tokenizer_id: String,
    pub quality_contract_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ArchitectureDimensions {
    pub layer_count: u32,
    pub hidden_size: u32,
    pub intermediate_size: u32,
    pub attention_head_count: u32,
    pub kv_head_count: u32,
    pub head_dimension: u32,
    pub vocabulary_size: u32,
    pub total_parameter_count: u64,
    pub active_parameter_count: u64,
    pub feed_forward: FeedForwardArchitecture,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "architecture", rename_all = "snake_case")]
pub enum FeedForwardArchitecture {
    Dense,
    MixtureOfExperts {
        expert_count: u32,
        active_experts_per_token: u32,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "evidence", rename_all = "snake_case")]
pub enum ScaleLabel {
    ReferenceFixture { name: String },
    SyntheticProjection { name: String, derived_from: String },
}

impl ScaleLabel {
    pub fn display_name(&self) -> &str {
        match self {
            Self::ReferenceFixture { name } | Self::SyntheticProjection { name, .. } => name,
        }
    }

    fn validate(&self) -> Result<(), ScaleError> {
        if self.display_name().trim().is_empty() {
            return Err(ScaleError::InvalidLabel("name"));
        }
        if let Self::SyntheticProjection { derived_from, .. } = self {
            if derived_from.trim().is_empty() {
                return Err(ScaleError::InvalidLabel("derived_from"));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ScaleScenario {
    pub label: ScaleLabel,
    pub contract: ModelScaleContract,
    pub architecture: ArchitectureDimensions,
}

impl ScaleScenario {
    pub fn display_name(&self) -> &str {
        self.label.display_name()
    }

    pub fn validate(&self) -> Result<(), ScaleError> {
        self.label.validate()?;
        self.contract.validate()?;
        self.architecture.validate()
    }

    pub fn project(
        &self,
        architecture: ArchitectureDimensions,
        name: impl Into<String>,
    ) -> Result<Self, ScaleError> {
        self.validate()?;
        architecture.validate()?;
        let projected = Self {
            label: ScaleLabel::SyntheticProjection {
                name: name.into(),
                derived_from: self.display_name().into(),
            },
            contract: self.contract.clone(),
            architecture,
        };
        projected.validate()?;
        Ok(projected)
    }

    pub fn resource_envelope(
        &self,
        request: EnvelopeRequest,
    ) -> Result<ResourceEnvelope, ScaleError> {
        self.validate()?;
        request.validate()?;
        let total_weight_bytes = stored_weight_bytes(
            self.architecture.total_parameter_count,
            request.weight_precision,
            request.quantized_weight_storage.as_ref(),
        )
        .ok_or(ScaleError::ArithmeticOverflow)?;
        let active_weight_bytes = stored_weight_bytes(
            self.architecture.active_parameter_count,
            request.weight_precision,
            request.quantized_weight_storage.as_ref(),
        )
        .ok_or(ScaleError::ArithmeticOverflow)?;
        let kv_bytes_per_token = kv_bytes_per_token(&self.architecture, request.kv_precision)?;
        let resident_tokens = product(&[
            u128::from(request.batch_size),
            u128::from(request.context_tokens)
                .checked_add(u128::from(request.output_tokens))
                .ok_or(ScaleError::ArithmeticOverflow)?,
        ])?;
        let kv_cache_bytes = u64::try_from(
            resident_tokens
                .checked_mul(u128::from(kv_bytes_per_token))
                .ok_or(ScaleError::ArithmeticOverflow)?,
        )
        .map_err(|_| ScaleError::ArithmeticOverflow)?;
        let prefill_attention_token_pairs = prefill_attention_pairs(&request)?;
        let decode_attention_token_pairs = decode_attention_pairs(&request)?;
        let linear_operations = linear_operations_per_token(&self.architecture)?;
        let prefill_tokens = product(&[
            u128::from(request.batch_size),
            u128::from(request.context_tokens),
        ])?;
        let decode_tokens = product(&[
            u128::from(request.batch_size),
            u128::from(request.output_tokens),
        ])?;
        let prefill_attention_operations =
            attention_operations(&self.architecture, prefill_attention_token_pairs)?;
        let decode_attention_operations =
            attention_operations(&self.architecture, decode_attention_token_pairs)?;
        let lm_head_operations = language_model_head_operations(&self.architecture, decode_tokens)?;
        let prefill_compute_operations = linear_operations
            .checked_mul(prefill_tokens)
            .and_then(|operations| operations.checked_add(prefill_attention_operations))
            .ok_or(ScaleError::ArithmeticOverflow)?;
        let decode_compute_operations = linear_operations
            .checked_mul(decode_tokens)
            .and_then(|operations| operations.checked_add(decode_attention_operations))
            .and_then(|operations| operations.checked_add(lm_head_operations))
            .ok_or(ScaleError::ArithmeticOverflow)?;

        Ok(ResourceEnvelope {
            label: self.label.clone(),
            contract: self.contract.clone(),
            architecture: self.architecture.clone(),
            request,
            total_weight_bytes,
            active_weight_bytes,
            kv_bytes_per_token,
            kv_cache_bytes,
            prefill_attention_token_pairs,
            decode_attention_token_pairs,
            prefill_compute_operations,
            decode_compute_operations,
        })
    }
}

impl ModelScaleContract {
    pub fn validate(&self) -> Result<(), ScaleError> {
        for (field, value) in [
            ("contract.model_id", self.model_id.as_str()),
            ("contract.model_revision", self.model_revision.as_str()),
            ("contract.tokenizer_id", self.tokenizer_id.as_str()),
            (
                "contract.quality_contract_id",
                self.quality_contract_id.as_str(),
            ),
        ] {
            if value.trim().is_empty() {
                return Err(ScaleError::InvalidContract(field));
            }
        }
        Ok(())
    }
}

impl ArchitectureDimensions {
    pub fn validate(&self) -> Result<(), ScaleError> {
        for (field, value) in [
            ("layer_count", self.layer_count),
            ("hidden_size", self.hidden_size),
            ("intermediate_size", self.intermediate_size),
            ("attention_head_count", self.attention_head_count),
            ("kv_head_count", self.kv_head_count),
            ("head_dimension", self.head_dimension),
            ("vocabulary_size", self.vocabulary_size),
        ] {
            if value == 0 {
                return Err(ScaleError::InvalidArchitecture(field));
            }
        }
        if self.total_parameter_count == 0 {
            return Err(ScaleError::InvalidArchitecture("total_parameter_count"));
        }
        if self.active_parameter_count == 0
            || self.active_parameter_count > self.total_parameter_count
        {
            return Err(ScaleError::InvalidArchitecture("active_parameter_count"));
        }
        if self.attention_head_count.checked_mul(self.head_dimension) != Some(self.hidden_size) {
            return Err(ScaleError::InvalidArchitecture("hidden_size"));
        }
        if self.kv_head_count > self.attention_head_count
            || self.attention_head_count.checked_rem(self.kv_head_count) != Some(0)
        {
            return Err(ScaleError::InvalidArchitecture("kv_head_count"));
        }
        match self.feed_forward {
            FeedForwardArchitecture::Dense => {
                if self.active_parameter_count != self.total_parameter_count {
                    return Err(ScaleError::InvalidArchitecture("active_parameter_count"));
                }
            }
            FeedForwardArchitecture::MixtureOfExperts {
                expert_count,
                active_experts_per_token,
            } => {
                if expert_count == 0 {
                    return Err(ScaleError::InvalidArchitecture("feed_forward.expert_count"));
                }
                if active_experts_per_token == 0 || active_experts_per_token > expert_count {
                    return Err(ScaleError::InvalidArchitecture(
                        "feed_forward.active_experts_per_token",
                    ));
                }
            }
        }
        Ok(())
    }

    pub const fn expert_count(&self) -> Option<u32> {
        match self.feed_forward {
            FeedForwardArchitecture::Dense => None,
            FeedForwardArchitecture::MixtureOfExperts { expert_count, .. } => Some(expert_count),
        }
    }

    pub const fn active_experts_per_token(&self) -> Option<u32> {
        match self.feed_forward {
            FeedForwardArchitecture::Dense => None,
            FeedForwardArchitecture::MixtureOfExperts {
                active_experts_per_token,
                ..
            } => Some(active_experts_per_token),
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct EnvelopeRequest {
    pub batch_size: u32,
    pub context_tokens: u32,
    pub output_tokens: u32,
    pub weight_precision: Precision,
    #[serde(default)]
    pub quantized_weight_storage: Option<QuantizedWeightStorageSpec>,
    pub kv_precision: Precision,
}

impl EnvelopeRequest {
    pub fn validate(&self) -> Result<(), ScaleError> {
        for (field, value) in [
            ("batch_size", self.batch_size),
            ("context_tokens", self.context_tokens),
            ("output_tokens", self.output_tokens),
        ] {
            if value == 0 {
                return Err(ScaleError::InvalidEnvelopeRequest(field));
            }
        }
        if self.weight_precision.bits() < 8 && self.quantized_weight_storage.is_none() {
            return Err(ScaleError::InvalidEnvelopeRequest(
                "quantized_weight_storage",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ResourceEnvelope {
    pub label: ScaleLabel,
    pub contract: ModelScaleContract,
    pub architecture: ArchitectureDimensions,
    pub request: EnvelopeRequest,
    pub total_weight_bytes: u64,
    pub active_weight_bytes: u64,
    pub kv_bytes_per_token: u64,
    pub kv_cache_bytes: u64,
    pub prefill_attention_token_pairs: u128,
    pub decode_attention_token_pairs: u128,
    pub prefill_compute_operations: u128,
    pub decode_compute_operations: u128,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ResourceEnvelopeComparison {
    pub baseline_label: ScaleLabel,
    pub candidate_label: ScaleLabel,
    pub total_weight_ratio: f64,
    pub active_weight_ratio: f64,
    pub kv_bytes_per_token_ratio: f64,
    pub kv_cache_ratio: f64,
    pub prefill_compute_ratio: f64,
    pub decode_compute_ratio: f64,
}

pub fn compare_envelopes(
    baseline: &ResourceEnvelope,
    candidate: &ResourceEnvelope,
) -> Result<ResourceEnvelopeComparison, ScaleError> {
    if baseline.contract != candidate.contract {
        return Err(ScaleError::ModelContractMismatch);
    }
    if baseline.request != candidate.request {
        return Err(ScaleError::EnvelopeRequestMismatch);
    }
    Ok(ResourceEnvelopeComparison {
        baseline_label: baseline.label.clone(),
        candidate_label: candidate.label.clone(),
        total_weight_ratio: ratio_u64(candidate.total_weight_bytes, baseline.total_weight_bytes),
        active_weight_ratio: ratio_u64(candidate.active_weight_bytes, baseline.active_weight_bytes),
        kv_bytes_per_token_ratio: ratio_u64(
            candidate.kv_bytes_per_token,
            baseline.kv_bytes_per_token,
        ),
        kv_cache_ratio: ratio_u64(candidate.kv_cache_bytes, baseline.kv_cache_bytes),
        prefill_compute_ratio: ratio_u128(
            candidate.prefill_compute_operations,
            baseline.prefill_compute_operations,
        ),
        decode_compute_ratio: ratio_u128(
            candidate.decode_compute_operations,
            baseline.decode_compute_operations,
        ),
    })
}

pub fn qwen3_8b_reference() -> ScaleScenario {
    ScaleScenario {
        label: ScaleLabel::ReferenceFixture {
            name: "Qwen3-8B reference".into(),
        },
        contract: ModelScaleContract {
            model_id: "Qwen/Qwen3-8B".into(),
            model_revision: "b968826d9c46dd6066d109eabc6255188de91218".into(),
            tokenizer_id: "Qwen/Qwen3-8B".into(),
            quality_contract_id: "agentic-v1".into(),
        },
        architecture: ArchitectureDimensions {
            layer_count: 36,
            hidden_size: 4_096,
            intermediate_size: 12_288,
            attention_head_count: 32,
            kv_head_count: 8,
            head_dimension: 128,
            vocabulary_size: 151_936,
            total_parameter_count: 8_200_000_000,
            active_parameter_count: 8_200_000_000,
            feed_forward: FeedForwardArchitecture::Dense,
        },
    }
}

pub fn synthetic_glm_class_projection(source: &ScaleScenario) -> Result<ScaleScenario, ScaleError> {
    source.project(
        ArchitectureDimensions {
            layer_count: 80,
            hidden_size: 8_192,
            intermediate_size: 4_096,
            attention_head_count: 64,
            kv_head_count: 8,
            head_dimension: 128,
            vocabulary_size: 200_000,
            total_parameter_count: 1_000_000_000_000,
            active_parameter_count: 32_000_000_000,
            feed_forward: FeedForwardArchitecture::MixtureOfExperts {
                expert_count: 128,
                active_experts_per_token: 2,
            },
        },
        "Synthetic GLM-class MoE",
    )
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum ScaleError {
    #[error("invalid scale label field {0}")]
    InvalidLabel(&'static str),
    #[error("invalid model scale contract field {0}")]
    InvalidContract(&'static str),
    #[error("invalid architecture field {0}")]
    InvalidArchitecture(&'static str),
    #[error("invalid resource envelope request field {0}")]
    InvalidEnvelopeRequest(&'static str),
    #[error("resource envelope arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("resource envelopes use different model contracts")]
    ModelContractMismatch,
    #[error("resource envelopes use different workload requests")]
    EnvelopeRequestMismatch,
}

fn kv_bytes_per_token(
    architecture: &ArchitectureDimensions,
    precision: Precision,
) -> Result<u64, ScaleError> {
    let elements = product(&[
        u128::from(architecture.layer_count),
        u128::from(architecture.kv_head_count),
        u128::from(architecture.head_dimension),
        2,
    ])?;
    packed_bytes(elements, precision)
}

fn linear_operations_per_token(architecture: &ArchitectureDimensions) -> Result<u128, ScaleError> {
    let hidden = u128::from(architecture.hidden_size);
    let kv_width = product(&[
        u128::from(architecture.kv_head_count),
        u128::from(architecture.head_dimension),
    ])?;
    let active_experts = u128::from(architecture.active_experts_per_token().unwrap_or(1));
    let attention_projection_macs = product(&[2, hidden, hidden])?
        .checked_add(product(&[2, hidden, kv_width])?)
        .ok_or(ScaleError::ArithmeticOverflow)?;
    let feed_forward_macs = product(&[
        3,
        hidden,
        u128::from(architecture.intermediate_size),
        active_experts,
    ])?;
    attention_projection_macs
        .checked_add(feed_forward_macs)
        .and_then(|macs| macs.checked_mul(2))
        .and_then(|operations| operations.checked_mul(u128::from(architecture.layer_count)))
        .ok_or(ScaleError::ArithmeticOverflow)
}

fn attention_operations(
    architecture: &ArchitectureDimensions,
    token_pairs: u128,
) -> Result<u128, ScaleError> {
    product(&[
        4,
        u128::from(architecture.layer_count),
        u128::from(architecture.hidden_size),
        token_pairs,
    ])
}

fn language_model_head_operations(
    architecture: &ArchitectureDimensions,
    tokens: u128,
) -> Result<u128, ScaleError> {
    product(&[
        2,
        u128::from(architecture.hidden_size),
        u128::from(architecture.vocabulary_size),
        tokens,
    ])
}

fn prefill_attention_pairs(request: &EnvelopeRequest) -> Result<u128, ScaleError> {
    let context = u128::from(request.context_tokens);
    context
        .checked_mul(
            context
                .checked_add(1)
                .ok_or(ScaleError::ArithmeticOverflow)?,
        )
        .and_then(|pairs| pairs.checked_div(2))
        .and_then(|pairs| pairs.checked_mul(u128::from(request.batch_size)))
        .ok_or(ScaleError::ArithmeticOverflow)
}

fn decode_attention_pairs(request: &EnvelopeRequest) -> Result<u128, ScaleError> {
    let output = u128::from(request.output_tokens);
    let context = u128::from(request.context_tokens);
    output
        .checked_mul(context)
        .and_then(|pairs| {
            output
                .checked_mul(output.checked_sub(1)?)
                .and_then(|triangle| triangle.checked_div(2))
                .and_then(|triangle| pairs.checked_add(triangle))
        })
        .and_then(|pairs| pairs.checked_mul(u128::from(request.batch_size)))
        .ok_or(ScaleError::ArithmeticOverflow)
}

fn packed_bytes(elements: u128, precision: Precision) -> Result<u64, ScaleError> {
    let bits = elements
        .checked_mul(u128::from(precision.bits()))
        .ok_or(ScaleError::ArithmeticOverflow)?;
    let bytes = bits
        .checked_add(7)
        .and_then(|value| value.checked_div(8))
        .ok_or(ScaleError::ArithmeticOverflow)?;
    u64::try_from(bytes).map_err(|_| ScaleError::ArithmeticOverflow)
}

fn product(values: &[u128]) -> Result<u128, ScaleError> {
    values.iter().try_fold(1_u128, |product, value| {
        product
            .checked_mul(*value)
            .ok_or(ScaleError::ArithmeticOverflow)
    })
}

fn ratio_u64(candidate: u64, baseline: u64) -> f64 {
    candidate as f64 / baseline as f64
}

fn ratio_u128(candidate: u128, baseline: u128) -> f64 {
    candidate as f64 / baseline as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn qwen3_8b_fixture_derives_dense_weight_and_kv_resources() {
        let scenario = qwen3_8b_reference();
        let envelope = scenario.resource_envelope(request()).unwrap();

        assert_eq!(scenario.display_name(), "Qwen3-8B reference");
        assert!(matches!(
            scenario.label,
            ScaleLabel::ReferenceFixture { .. }
        ));
        assert_eq!(scenario.architecture.layer_count, 36);
        assert_eq!(scenario.architecture.attention_head_count, 32);
        assert_eq!(scenario.architecture.kv_head_count, 8);
        assert_eq!(envelope.total_weight_bytes, 16_400_000_000);
        assert_eq!(envelope.active_weight_bytes, 16_400_000_000);
        assert_eq!(envelope.kv_bytes_per_token, 147_456);
        assert!(envelope.prefill_compute_operations > 0);
        assert!(envelope.decode_compute_operations > 0);
    }

    #[test]
    fn scale_envelope_uses_explicit_groupwise_weight_storage() {
        let mut request = request();
        request.weight_precision = Precision::Int4;
        request.quantized_weight_storage =
            Some(QuantizedWeightStorageSpec::grouped_all(128, 4, 16, 16, 0));

        let envelope = qwen3_8b_reference().resource_envelope(request).unwrap();

        assert_eq!(envelope.total_weight_bytes, 4_228_125_000);
        assert!(envelope.total_weight_bytes > 4_100_000_000);
    }

    #[test]
    fn glm_class_example_is_explicitly_synthetic_and_moe_aware() {
        let source = qwen3_8b_reference();
        let target = synthetic_glm_class_projection(&source).unwrap();
        let envelope = target.resource_envelope(request()).unwrap();

        assert_eq!(target.display_name(), "Synthetic GLM-class MoE");
        assert!(matches!(
            target.label,
            ScaleLabel::SyntheticProjection { .. }
        ));
        assert_eq!(target.contract, source.contract);
        assert_eq!(target.architecture.total_parameter_count, 1_000_000_000_000);
        assert_eq!(target.architecture.active_parameter_count, 32_000_000_000);
        assert_eq!(
            target.architecture.feed_forward,
            FeedForwardArchitecture::MixtureOfExperts {
                expert_count: 128,
                active_experts_per_token: 2,
            }
        );
        assert_eq!(envelope.total_weight_bytes, 2_000_000_000_000);
        assert_eq!(envelope.active_weight_bytes, 64_000_000_000);
    }

    #[test]
    fn projection_comparison_preserves_contract_and_reports_scale_ratios() {
        let source = qwen3_8b_reference();
        let target = synthetic_glm_class_projection(&source).unwrap();
        let source_envelope = source.resource_envelope(request()).unwrap();
        let target_envelope = target.resource_envelope(request()).unwrap();

        let comparison = compare_envelopes(&source_envelope, &target_envelope).unwrap();

        assert_eq!(comparison.baseline_label, source.label);
        assert_eq!(comparison.candidate_label, target.label);
        assert!(comparison.total_weight_ratio > 100.0);
        assert!(comparison.active_weight_ratio > 3.0);
        assert!(comparison.kv_cache_ratio > 2.0);
        assert!(comparison.prefill_compute_ratio > 1.0);
        assert!(comparison.decode_compute_ratio > 1.0);
    }

    #[test]
    fn comparison_rejects_different_model_contracts_or_workloads() {
        let source = qwen3_8b_reference();
        let source_envelope = source.resource_envelope(request()).unwrap();

        let mut different_contract = source.clone();
        different_contract.contract.model_revision = "different".into();
        let different_contract = different_contract.resource_envelope(request()).unwrap();
        assert_eq!(
            compare_envelopes(&source_envelope, &different_contract),
            Err(ScaleError::ModelContractMismatch)
        );

        let mut different_request = request();
        different_request.context_tokens *= 2;
        let different_request = source.resource_envelope(different_request).unwrap();
        assert_eq!(
            compare_envelopes(&source_envelope, &different_request),
            Err(ScaleError::EnvelopeRequestMismatch)
        );
    }

    #[test]
    fn invalid_geometry_routing_and_zero_work_are_rejected() {
        let mut scenario = qwen3_8b_reference();
        scenario.architecture.hidden_size = 4_000;
        assert_eq!(
            scenario.resource_envelope(request()),
            Err(ScaleError::InvalidArchitecture("hidden_size"))
        );

        let mut scenario = synthetic_glm_class_projection(&qwen3_8b_reference()).unwrap();
        scenario.architecture.feed_forward = FeedForwardArchitecture::MixtureOfExperts {
            expert_count: 8,
            active_experts_per_token: 9,
        };
        assert_eq!(
            scenario.resource_envelope(request()),
            Err(ScaleError::InvalidArchitecture(
                "feed_forward.active_experts_per_token"
            ))
        );

        let mut empty_request = request();
        empty_request.batch_size = 0;
        assert_eq!(
            qwen3_8b_reference().resource_envelope(empty_request),
            Err(ScaleError::InvalidEnvelopeRequest("batch_size"))
        );
    }

    fn request() -> EnvelopeRequest {
        EnvelopeRequest {
            batch_size: 1,
            context_tokens: 4_096,
            output_tokens: 256,
            weight_precision: Precision::Bf16,
            quantized_weight_storage: None,
            kv_precision: Precision::Fp16,
        }
    }
}
