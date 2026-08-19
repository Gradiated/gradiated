use std::collections::{HashMap, HashSet};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use validator::Validate;

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
#[serde(deny_unknown_fields)]
pub struct GatewayModelProperties {
    #[validate(range(min = 1, max = 1))]
    pub schema_version: u16,
    #[validate(length(max = 2_000))]
    pub description: String,
    pub released_at: Option<DateTime<Utc>>,
    #[validate(length(max = 300))]
    pub hugging_face_id: Option<String>,
    pub quantization: Option<ModelQuantization>,
    #[validate(length(max = 100))]
    pub tokenizer: Option<String>,
    pub input_modalities: [TextInputModality; 1],
    pub output_modalities: [TextOutputModality; 1],
    pub passthrough_parameters: HashMap<String, ModelParameterDescriptor>,
    pub deprecation_date: Option<DateTime<Utc>>,
}

impl GatewayModelProperties {
    pub fn validate_for_serving(&self) -> Result<(), ModelPropertiesError> {
        <Self as Validate>::validate(self)
            .map_err(|error| ModelPropertiesError::Invalid(error.to_string()))?;
        self.text_input().validate_semantics()?;
        self.text_output().validate_semantics()?;
        validate_parameter_map(&self.passthrough_parameters)?;
        Ok(())
    }

    pub fn text_input(&self) -> &TextInputModality {
        &self.input_modalities[0]
    }

    pub fn text_output(&self) -> &TextOutputModality {
        &self.output_modalities[0]
    }

    pub fn parameter(&self, name: &str) -> Option<&ModelParameterDescriptor> {
        self.text_output()
            .supported_parameters
            .get(name)
            .or_else(|| self.passthrough_parameters.get(name))
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelQuantization {
    Int4,
    Int8,
    Fp4,
    Mxfp4,
    Nvfp4,
    Fp6,
    Fp8,
    Mxfp8,
    Fp16,
    Bf16,
    Fp32,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
#[serde(deny_unknown_fields)]
pub struct TextInputModality {
    #[serde(rename = "type")]
    pub kind: TextModalityKind,
    #[validate(nested)]
    pub supported_inputs: SupportedTextInputs,
    #[validate(length(min = 2, max = 3))]
    pub pricing: Vec<InputTokenPrice>,
}

impl TextInputModality {
    fn validate_semantics(&self) -> Result<(), ModelPropertiesError> {
        <Self as Validate>::validate(self)
            .map_err(|error| ModelPropertiesError::Invalid(error.to_string()))?;
        if self.supported_inputs.max_prompt_length.value
            > self.supported_inputs.max_context_length.value
        {
            return Err(ModelPropertiesError::Invalid(
                "max_prompt_length cannot exceed max_context_length".to_owned(),
            ));
        }
        require_unique_prices(
            self.pricing.iter().map(InputTokenPrice::kind),
            [InputPriceType::Prompt, InputPriceType::CachedPrompt],
        )?;
        Ok(())
    }

    pub fn price(&self, price_type: InputPriceType) -> Option<u64> {
        self.pricing
            .iter()
            .find(|price| price.kind() == price_type)
            .map(InputTokenPrice::cost)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Validate)]
#[serde(deny_unknown_fields)]
pub struct SupportedTextInputs {
    #[validate(nested)]
    pub max_context_length: TokenMeasure,
    #[validate(nested)]
    pub max_prompt_length: TokenMeasure,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
#[serde(deny_unknown_fields)]
pub struct TextOutputModality {
    #[serde(rename = "type")]
    pub kind: TextModalityKind,
    #[validate(nested)]
    pub max_length: TokenMeasure,
    #[validate(nested)]
    pub default_length: TokenMeasure,
    pub streaming: bool,
    pub supported_parameters: HashMap<String, ModelParameterDescriptor>,
    #[validate(length(min = 1, max = 2))]
    pub pricing: Vec<OutputTokenPrice>,
}

impl TextOutputModality {
    fn validate_semantics(&self) -> Result<(), ModelPropertiesError> {
        <Self as Validate>::validate(self)
            .map_err(|error| ModelPropertiesError::Invalid(error.to_string()))?;
        if self.default_length.value > self.max_length.value {
            return Err(ModelPropertiesError::Invalid(
                "default_length cannot exceed max_length".to_owned(),
            ));
        }
        validate_parameter_map(&self.supported_parameters)?;
        require_unique_prices(
            self.pricing.iter().map(OutputTokenPrice::kind),
            [OutputPriceType::Completion],
        )?;
        if self.supported_parameters.contains_key("reasoning")
            && self.price(OutputPriceType::InternalReasoning).is_none()
        {
            return Err(ModelPropertiesError::Invalid(
                "internal_reasoning pricing is required when reasoning is supported".to_owned(),
            ));
        }
        Ok(())
    }

    pub fn price(&self, price_type: OutputPriceType) -> Option<u64> {
        self.pricing
            .iter()
            .find(|price| price.kind() == price_type)
            .map(OutputTokenPrice::cost)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Validate)]
#[serde(deny_unknown_fields)]
pub struct TokenMeasure {
    #[validate(range(min = 1))]
    pub value: u64,
    pub unit: TokenUnit,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TokenUnit {
    Token,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum TextModalityKind {
    Text,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum InputTokenPrice {
    Prompt { unit: TokenUnit, cost: u64 },
    CachedPrompt { unit: TokenUnit, cost: u64 },
    CacheWrite { unit: TokenUnit, cost: u64 },
}

impl InputTokenPrice {
    pub fn kind(&self) -> InputPriceType {
        match self {
            Self::Prompt { .. } => InputPriceType::Prompt,
            Self::CachedPrompt { .. } => InputPriceType::CachedPrompt,
            Self::CacheWrite { .. } => InputPriceType::CacheWrite,
        }
    }

    pub fn cost(&self) -> u64 {
        match self {
            Self::Prompt { cost, .. }
            | Self::CachedPrompt { cost, .. }
            | Self::CacheWrite { cost, .. } => *cost,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum InputPriceType {
    Prompt,
    CachedPrompt,
    CacheWrite,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum OutputTokenPrice {
    Completion { unit: TokenUnit, cost: u64 },
    InternalReasoning { unit: TokenUnit, cost: u64 },
}

impl OutputTokenPrice {
    pub fn kind(&self) -> OutputPriceType {
        match self {
            Self::Completion { .. } => OutputPriceType::Completion,
            Self::InternalReasoning { .. } => OutputPriceType::InternalReasoning,
        }
    }

    pub fn cost(&self) -> u64 {
        match self {
            Self::Completion { cost, .. } | Self::InternalReasoning { cost, .. } => *cost,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum OutputPriceType {
    Completion,
    InternalReasoning,
}

fn require_unique_prices<T: Copy + Eq + std::hash::Hash, const N: usize>(
    mut prices: impl Iterator<Item = T>,
    required: [T; N],
) -> Result<(), ModelPropertiesError> {
    let mut kinds = HashSet::new();
    if prices.any(|kind| !kinds.insert(kind)) {
        return Err(ModelPropertiesError::Invalid(
            "pricing types must be unique".to_owned(),
        ));
    }
    if required.iter().any(|kind| !kinds.contains(kind)) {
        return Err(ModelPropertiesError::Invalid(
            "required pricing type is missing".to_owned(),
        ));
    }
    Ok(())
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum ModelParameterDescriptor {
    Range {
        min: f64,
        max: f64,
    },
    Integer {
        min: i64,
        max: i64,
        unit: Option<TokenUnit>,
    },
    Boolean,
    Enum {
        values: Vec<ParameterValue>,
    },
    Unknown,
}

impl ModelParameterDescriptor {
    pub fn accepts(&self, value: &Value) -> bool {
        match self {
            Self::Range { min, max } => value
                .as_f64()
                .is_some_and(|value| value >= *min && value <= *max),
            Self::Integer { min, max, .. } => value
                .as_i64()
                .is_some_and(|value| value >= *min && value <= *max),
            Self::Boolean => value.is_boolean(),
            Self::Enum { values } => {
                ParameterValue::from_json(value).is_some_and(|value| values.contains(&value))
            }
            Self::Unknown => true,
        }
    }

    fn validate_for_serving(&self) -> Result<(), ModelPropertiesError> {
        match self {
            Self::Range { min, max } if !min.is_finite() || !max.is_finite() || min > max => Err(
                ModelPropertiesError::Invalid("range parameter min cannot exceed max".to_owned()),
            ),
            Self::Integer { min, max, .. } if min > max => Err(ModelPropertiesError::Invalid(
                "integer parameter min cannot exceed max".to_owned(),
            )),
            Self::Enum { values } if values.is_empty() => Err(ModelPropertiesError::Invalid(
                "enum parameters require at least one value".to_owned(),
            )),
            _ => Ok(()),
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(untagged)]
pub enum ParameterValue {
    String(String),
    Number(serde_json::Number),
    Boolean(bool),
}

impl ParameterValue {
    fn from_json(value: &Value) -> Option<Self> {
        match value {
            Value::String(value) => Some(Self::String(value.clone())),
            Value::Number(value) => Some(Self::Number(value.clone())),
            Value::Bool(value) => Some(Self::Boolean(*value)),
            _ => None,
        }
    }
}

fn validate_parameter_map(
    parameters: &HashMap<String, ModelParameterDescriptor>,
) -> Result<(), ModelPropertiesError> {
    for (name, descriptor) in parameters {
        if name.is_empty() || name.chars().count() > 100 {
            return Err(ModelPropertiesError::Invalid(
                "parameter names must contain 1 to 100 characters".to_owned(),
            ));
        }
        descriptor.validate_for_serving()?;
    }
    Ok(())
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum ModelPropertiesError {
    #[error("{0}")]
    Invalid(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn properties() -> GatewayModelProperties {
        serde_json::from_value(serde_json::json!({
            "schema_version": 1,
            "description": "Local model",
            "released_at": null,
            "hugging_face_id": "mlx-community/Qwen3-0.6B-4bit",
            "quantization": "int4",
            "tokenizer": "Qwen3",
            "input_modalities": [{
                "type": "text",
                "supported_inputs": {
                    "max_context_length": {"value": 32768, "unit": "token"},
                    "max_prompt_length": {"value": 32768, "unit": "token"}
                },
                "pricing": [
                    {"type": "prompt", "unit": "token", "cost": 0},
                    {"type": "cached_prompt", "unit": "token", "cost": 0}
                ]
            }],
            "output_modalities": [{
                "type": "text",
                "max_length": {"value": 4096, "unit": "token"},
                "default_length": {"value": 1024, "unit": "token"},
                "streaming": true,
                "supported_parameters": {
                    "max_tokens": {"type": "integer", "min": 1, "max": 4096, "unit": "token"},
                    "temperature": {"type": "range", "min": 0, "max": 2}
                },
                "pricing": [{"type": "completion", "unit": "token", "cost": 0}]
            }],
            "passthrough_parameters": {
                "seed": {"type": "integer", "min": 0, "max": 100},
                "response_format": {"type": "enum", "values": ["text", "json"]}
            },
            "deprecation_date": null
        }))
        .expect("normalized properties should deserialize")
    }

    #[test]
    fn validates_the_normalized_model_contract() {
        let mut properties = properties();
        properties
            .validate_for_serving()
            .expect("properties should validate");
        assert_eq!(
            properties
                .text_input()
                .supported_inputs
                .max_context_length
                .value,
            32_768
        );
        assert_eq!(properties.text_output().max_length.value, 4_096);
        assert_eq!(properties.text_output().default_length.value, 1_024);
        assert_eq!(
            properties.text_input().price(InputPriceType::CachedPrompt),
            Some(0)
        );

        properties.output_modalities[0].default_length.value = 4_097;
        assert!(properties.validate_for_serving().is_err());
    }

    #[test]
    fn rejects_a_non_normalized_projection() {
        let value = serde_json::json!({
            "schema_version": 1,
            "description": "Missing defaults",
            "input_modalities": [],
            "output_modalities": [],
            "passthrough_parameters": {}
        });
        assert!(serde_json::from_value::<GatewayModelProperties>(value).is_err());
    }

    #[test]
    fn parameter_descriptors_apply_types_bounds_and_enums() {
        let properties = properties();
        let temperature = properties.parameter("temperature").unwrap();
        let seed = properties.parameter("seed").unwrap();
        let response_format = properties.parameter("response_format").unwrap();

        assert!(temperature.accepts(&serde_json::json!(0.5)));
        assert!(!temperature.accepts(&serde_json::json!(3)));
        assert!(seed.accepts(&serde_json::json!(7)));
        assert!(!seed.accepts(&serde_json::json!(101)));
        assert!(response_format.accepts(&serde_json::json!("json")));
        assert!(!response_format.accepts(&serde_json::json!("xml")));
    }
}
