use std::collections::{HashMap, HashSet};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use validator::{Validate, ValidationErrors};

use crate::deployment::{DeploymentError, DeploymentStatus, GatewayModelDeployment};

/// The largest integer that JSON numbers and Lua doubles hold exactly.
pub(crate) const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct GatewayModel {
    pub id: String,
    pub name: String,
    pub status: ModelStatus,
    pub properties: GatewayModelProperties,
    pub deployments: Vec<GatewayModelDeployment>,
    #[serde(default)]
    pub openrouter_model_id: Option<String>,
    /// The tokenizer to count with when no deployment supplies one.
    #[serde(default)]
    pub tokenizer: Option<PinnedTokenizer>,
}

/// A Hugging Face tokenizer at an immutable revision.
#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
pub struct PinnedTokenizer {
    pub path: String,
    pub revision: String,
}

impl PinnedTokenizer {
    /// A malformed pin is ignored rather than trusted, like the OpenRouter mapping.
    pub fn valid(&self) -> bool {
        let bounded = |value: &str| !value.is_empty() && value.len() <= 300;
        bounded(&self.path)
            && self.revision.len() == 40
            && self.revision.bytes().all(|byte| byte.is_ascii_hexdigit())
    }
}

impl GatewayModel {
    /// The exact OpenRouter model that can serve this one. A malformed mapping is
    /// ignored rather than trusted, so it can never route to a different variant.
    pub fn openrouter_model(&self) -> Option<&str> {
        let id = self.openrouter_model_id.as_deref()?;
        if valid_openrouter_model_id(id) {
            return Some(id);
        }

        crate::diagnostics::limited_warn!(model_id = %self.id,
            error_code = "invalid_openrouter_model_id", "model's OpenRouter mapping is ignored");
        None
    }

    pub fn serving_deployment(&self) -> Result<ServingDeployment<'_>, ServingDeploymentError> {
        let deployment = self
            .deployments
            .iter()
            .find(|deployment| deployment.status == DeploymentStatus::Available)
            .ok_or(ServingDeploymentError::Missing)?;

        deployment.validate()?;
        let release_digest = deployment
            .served_release_digest()
            .map_err(|_| ServingDeploymentError::ReleaseDigest)?;

        Ok(ServingDeployment {
            deployment,
            release_digest,
        })
    }
}

/// `author/slug` without a `:variant` suffix or a `~` moving alias: both name a
/// different routing variant or a model that can change underneath the mapping.
pub(crate) fn valid_openrouter_model_id(id: &str) -> bool {
    let segment = |value: &str| {
        !value.is_empty()
            && value
                .bytes()
                .next()
                .is_some_and(|first| first.is_ascii_lowercase() || first.is_ascii_digit())
            && value.bytes().all(|byte| {
                byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"._-".contains(&byte)
            })
    };

    id.len() <= 200
        && id
            .split_once('/')
            .is_some_and(|(author, slug)| segment(author) && segment(slug))
}

#[derive(Debug, PartialEq)]
pub struct ServingDeployment<'a> {
    pub deployment: &'a GatewayModelDeployment,
    pub release_digest: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ModelStatus {
    Available,
    Unavailable,
    Retired,
}

#[derive(Debug, Error, PartialEq)]
pub enum ServingDeploymentError {
    #[error("model has no available deployment")]
    Missing,
    #[error("model's first available deployment is invalid: {0}")]
    Invalid(#[from] DeploymentError),
    #[error("model's serving release cannot be encoded")]
    ReleaseDigest,
}

impl ServingDeploymentError {
    pub fn diagnostic_code(&self) -> &'static str {
        match self {
            Self::Missing => "no_serving_deployment",
            Self::Invalid(_) => "invalid_deployment",
            Self::ReleaseDigest => "release_digest",
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
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
        <Self as Validate>::validate(self)?;
        self.text_input().validate_semantics()?;
        self.text_output().validate_semantics()?;

        validate_parameter_map(&self.passthrough_parameters)
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
        <Self as Validate>::validate(self)?;

        if self.supported_inputs.max_prompt_length.value
            > self.supported_inputs.max_context_length.value
        {
            return Err(ModelPropertiesError::PromptExceedsContext);
        }

        require_safe_costs(self.pricing.iter().map(InputTokenPrice::cost))?;

        require_unique_prices(
            self.pricing.iter().map(InputTokenPrice::kind),
            [InputPriceType::Prompt, InputPriceType::CachedPrompt],
        )
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize, Validate)]
pub struct SupportedTextInputs {
    #[validate(nested)]
    pub max_context_length: TokenMeasure,
    #[validate(nested)]
    pub max_prompt_length: TokenMeasure,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
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
        <Self as Validate>::validate(self)?;

        if self.default_length.value > self.max_length.value {
            return Err(ModelPropertiesError::DefaultExceedsMax);
        }

        validate_parameter_map(&self.supported_parameters)?;
        require_safe_costs(self.pricing.iter().map(OutputTokenPrice::cost))?;
        require_unique_prices(
            self.pricing.iter().map(OutputTokenPrice::kind),
            [OutputPriceType::Completion],
        )?;

        if self.supported_parameters.contains_key("reasoning")
            && self.price(OutputPriceType::InternalReasoning).is_none()
        {
            return Err(ModelPropertiesError::ReasoningUnpriced);
        }

        Ok(())
    }

    fn price(&self, price_type: OutputPriceType) -> Option<u64> {
        self.pricing
            .iter()
            .find(|price| price.kind() == price_type)
            .map(OutputTokenPrice::cost)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize, Validate)]
pub struct TokenMeasure {
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    pub value: u64,
    pub unit: TokenUnit,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TokenUnit {
    Token,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TextModalityKind {
    Text,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
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

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InputPriceType {
    Prompt,
    CachedPrompt,
    CacheWrite,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
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

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
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
        return Err(ModelPropertiesError::DuplicatePrice);
    }

    if required.iter().any(|kind| !kinds.contains(kind)) {
        return Err(ModelPropertiesError::MissingPrice);
    }

    Ok(())
}

fn require_safe_costs(mut costs: impl Iterator<Item = u64>) -> Result<(), ModelPropertiesError> {
    if costs.any(|cost| cost > MAX_SAFE_INTEGER) {
        return Err(ModelPropertiesError::UnsafePrice);
    }

    Ok(())
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
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
            Self::Range { min, max } if !min.is_finite() || !max.is_finite() || min > max => {
                Err(ModelPropertiesError::ParameterBounds)
            }
            Self::Integer { min, max, .. } if min > max => {
                Err(ModelPropertiesError::ParameterBounds)
            }
            Self::Enum { values } if values.is_empty() => Err(ModelPropertiesError::EmptyEnum),
            _ => Ok(()),
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
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
            return Err(ModelPropertiesError::ParameterName);
        }

        descriptor.validate_for_serving()?;
    }

    Ok(())
}

#[derive(Debug, Error, PartialEq)]
pub enum ModelPropertiesError {
    #[error("model properties do not match their schema: {0}")]
    Schema(#[from] ValidationErrors),
    #[error("max_prompt_length exceeds max_context_length")]
    PromptExceedsContext,
    #[error("default_length exceeds max_length")]
    DefaultExceedsMax,
    #[error("a pricing type appears more than once")]
    DuplicatePrice,
    #[error("a required pricing type is missing")]
    MissingPrice,
    #[error("reasoning is supported without an internal_reasoning price")]
    ReasoningUnpriced,
    #[error("a price exceeds the largest exact JSON integer")]
    UnsafePrice,
    #[error("a parameter name is empty or longer than 100 characters")]
    ParameterName,
    #[error("a parameter bound is not finite or its minimum exceeds its maximum")]
    ParameterBounds,
    #[error("an enum parameter has no values")]
    EmptyEnum,
}

#[cfg(test)]
mod tests {
    use std::mem::discriminant;

    use uuid::Uuid;

    use super::*;
    use crate::test_support;

    type Change = fn(&mut GatewayModelProperties);

    fn properties() -> GatewayModelProperties {
        test_support::model(true).properties
    }

    fn input(properties: &mut GatewayModelProperties) -> &mut TextInputModality {
        &mut properties.input_modalities[0]
    }

    fn output(properties: &mut GatewayModelProperties) -> &mut TextOutputModality {
        &mut properties.output_modalities[0]
    }

    fn token_price(cost: u64) -> InputTokenPrice {
        InputTokenPrice::Prompt {
            unit: TokenUnit::Token,
            cost,
        }
    }

    fn range(min: f64, max: f64) -> ModelParameterDescriptor {
        ModelParameterDescriptor::Range { min, max }
    }

    #[test]
    fn an_openrouter_mapping_names_one_exact_model() {
        for valid in [
            "z-ai/glm-5.3-flash",
            "deepseek/deepseek-v4.1-flash",
            "deepseek/deepseek-v4.1-flash-1017",
            "meta-llama/llama_4.1",
        ] {
            assert!(valid_openrouter_model_id(valid), "{valid}");
        }

        for invalid in [
            "",
            "z-ai",
            "z-ai/",
            "/glm-5.3-flash",
            "z-ai/glm-5.3-flash:free",
            "z-ai/glm-5.3-flash:nitro",
            "~z-ai/glm-latest",
            "Z-AI/GLM-5.3-Flash",
            "z-ai/glm/5.3",
            "z-ai/-glm",
            "z-ai/glm 5.3",
            &format!("z-ai/{}", "a".repeat(200)),
        ] {
            assert!(!valid_openrouter_model_id(invalid), "{invalid}");
        }
    }

    #[test]
    fn a_malformed_mapping_is_absent_rather_than_trusted() {
        let mut model = test_support::model(true);
        assert_eq!(model.openrouter_model(), None);

        model.openrouter_model_id = Some("z-ai/glm-5.3-flash".to_owned());
        assert_eq!(model.openrouter_model(), Some("z-ai/glm-5.3-flash"));

        model.openrouter_model_id = Some("z-ai/glm-5.3-flash:free".to_owned());
        assert_eq!(model.openrouter_model(), None);
    }

    #[test]
    fn validates_the_normalized_model_contract() {
        let properties = properties();

        properties
            .validate_for_serving()
            .expect("properties should validate");
        assert_eq!(
            properties
                .text_input()
                .supported_inputs
                .max_context_length
                .value,
            8_192
        );
        assert_eq!(properties.text_output().max_length.value, 4_096);
        assert_eq!(properties.text_output().default_length.value, 1_024);
        assert!(properties
            .text_input()
            .pricing
            .contains(&InputTokenPrice::CachedPrompt {
                unit: TokenUnit::Token,
                cost: 50,
            }));
    }

    #[test]
    fn each_serving_rule_rejects_with_its_own_error() {
        let schema = || ModelPropertiesError::Schema(ValidationErrors::new());
        let cases: Vec<(&str, Change, ModelPropertiesError)> = vec![
            (
                "prompt exceeds context",
                |properties| input(properties).supported_inputs.max_prompt_length.value = 8_193,
                ModelPropertiesError::PromptExceedsContext,
            ),
            (
                "default exceeds max",
                |properties| output(properties).default_length.value = 4_097,
                ModelPropertiesError::DefaultExceedsMax,
            ),
            (
                "duplicate prompt price",
                |properties| input(properties).pricing = vec![token_price(1), token_price(2)],
                ModelPropertiesError::DuplicatePrice,
            ),
            (
                "missing cached prompt price",
                |properties| {
                    input(properties).pricing[1] = InputTokenPrice::CacheWrite {
                        unit: TokenUnit::Token,
                        cost: 1,
                    }
                },
                ModelPropertiesError::MissingPrice,
            ),
            (
                "missing completion price",
                |properties| {
                    output(properties).pricing = vec![OutputTokenPrice::InternalReasoning {
                        unit: TokenUnit::Token,
                        cost: 1,
                    }]
                },
                ModelPropertiesError::MissingPrice,
            ),
            (
                "reasoning without a price",
                |properties| {
                    output(properties)
                        .supported_parameters
                        .insert("reasoning".to_owned(), ModelParameterDescriptor::Boolean);
                },
                ModelPropertiesError::ReasoningUnpriced,
            ),
            (
                "unsafe input cost",
                |properties| input(properties).pricing[0] = token_price(MAX_SAFE_INTEGER + 1),
                ModelPropertiesError::UnsafePrice,
            ),
            (
                "unsafe output cost",
                |properties| {
                    output(properties).pricing[0] = OutputTokenPrice::Completion {
                        unit: TokenUnit::Token,
                        cost: MAX_SAFE_INTEGER + 1,
                    }
                },
                ModelPropertiesError::UnsafePrice,
            ),
            (
                "unsafe token measure",
                |properties| output(properties).max_length.value = MAX_SAFE_INTEGER + 1,
                schema(),
            ),
            (
                "range minimum above maximum",
                |properties| {
                    output(properties)
                        .supported_parameters
                        .insert("temperature".to_owned(), range(2.0, 1.0));
                },
                ModelPropertiesError::ParameterBounds,
            ),
            (
                "non-finite range",
                |properties| {
                    output(properties)
                        .supported_parameters
                        .insert("temperature".to_owned(), range(0.0, f64::INFINITY));
                },
                ModelPropertiesError::ParameterBounds,
            ),
            (
                "integer minimum above maximum",
                |properties| {
                    properties.passthrough_parameters.insert(
                        "seed".to_owned(),
                        ModelParameterDescriptor::Integer {
                            min: 2,
                            max: 1,
                            unit: None,
                        },
                    );
                },
                ModelPropertiesError::ParameterBounds,
            ),
            (
                "empty enum",
                |properties| {
                    properties.passthrough_parameters.insert(
                        "response_format".to_owned(),
                        ModelParameterDescriptor::Enum { values: Vec::new() },
                    );
                },
                ModelPropertiesError::EmptyEnum,
            ),
            (
                "empty supported parameter name",
                |properties| {
                    output(properties)
                        .supported_parameters
                        .insert(String::new(), ModelParameterDescriptor::Boolean);
                },
                ModelPropertiesError::ParameterName,
            ),
            (
                "long supported parameter name",
                |properties| {
                    output(properties)
                        .supported_parameters
                        .insert("p".repeat(101), ModelParameterDescriptor::Boolean);
                },
                ModelPropertiesError::ParameterName,
            ),
            (
                "empty passthrough parameter name",
                |properties| {
                    properties
                        .passthrough_parameters
                        .insert(String::new(), ModelParameterDescriptor::Boolean);
                },
                ModelPropertiesError::ParameterName,
            ),
            (
                "long passthrough parameter name",
                |properties| {
                    properties
                        .passthrough_parameters
                        .insert("p".repeat(101), ModelParameterDescriptor::Boolean);
                },
                ModelPropertiesError::ParameterName,
            ),
            (
                "schema version",
                |properties| properties.schema_version = 2,
                schema(),
            ),
            (
                "long description",
                |properties| properties.description = "d".repeat(2_001),
                schema(),
            ),
            (
                "one input price",
                |properties| input(properties).pricing.truncate(1),
                schema(),
            ),
            (
                "four input prices",
                |properties| {
                    let pricing = &mut input(properties).pricing;
                    pricing.extend(pricing.clone());
                },
                schema(),
            ),
        ];

        for (name, change, expected) in cases {
            let mut properties = properties();
            change(&mut properties);
            let error = properties
                .validate_for_serving()
                .expect_err("the change breaks a rule");

            assert_eq!(
                discriminant(&error),
                discriminant(&expected),
                "{name}: {error}"
            );
        }
    }

    #[test]
    fn a_price_at_the_safe_integer_limit_is_accepted() {
        let mut properties = properties();
        input(&mut properties).pricing[0] = token_price(MAX_SAFE_INTEGER);
        output(&mut properties).max_length.value = MAX_SAFE_INTEGER;

        assert_eq!(properties.validate_for_serving(), Ok(()));
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
        let mut properties = properties();
        properties.passthrough_parameters.insert(
            "seed".to_owned(),
            ModelParameterDescriptor::Integer {
                min: 0,
                max: 100,
                unit: None,
            },
        );
        let temperature = properties.parameter("temperature").unwrap();
        let seed = properties.parameter("seed").unwrap();
        let response_format = properties.parameter("response_format").unwrap();

        assert!(temperature.accepts(&serde_json::json!(0.5)));
        assert!(!temperature.accepts(&serde_json::json!(3)));
        assert!(seed.accepts(&serde_json::json!(7)));
        assert!(!seed.accepts(&serde_json::json!(101)));
        assert!(!seed.accepts(&serde_json::json!(7.5)));
        assert!(response_format.accepts(&serde_json::json!("json")));
        assert!(!response_format.accepts(&serde_json::json!("xml")));
        assert_eq!(properties.parameter("tools"), None);
    }

    #[test]
    fn a_supported_parameter_shadows_a_passthrough_one() {
        let mut properties = properties();
        properties
            .passthrough_parameters
            .insert("temperature".to_owned(), ModelParameterDescriptor::Boolean);

        assert_eq!(properties.parameter("temperature"), Some(&range(0.0, 2.0)));
    }

    #[test]
    fn each_price_kind_has_the_wire_name_of_its_price() {
        let unit = TokenUnit::Token;
        let input = [
            InputTokenPrice::Prompt { unit, cost: 1 },
            InputTokenPrice::CachedPrompt { unit, cost: 1 },
            InputTokenPrice::CacheWrite { unit, cost: 1 },
        ];
        let output = [
            OutputTokenPrice::Completion { unit, cost: 1 },
            OutputTokenPrice::InternalReasoning { unit, cost: 1 },
        ];

        for price in input {
            let wire = serde_json::to_value(&price).unwrap();
            assert_eq!(wire["type"], serde_json::to_value(price.kind()).unwrap());
        }

        for price in output {
            let wire = serde_json::to_value(&price).unwrap();
            assert_eq!(wire["type"], serde_json::to_value(price.kind()).unwrap());
        }
    }

    fn model_with(statuses: &[DeploymentStatus]) -> GatewayModel {
        let mut model = test_support::model(true);
        let template = model.deployments[0].clone();
        model.deployments = statuses
            .iter()
            .zip(1..)
            .map(|(status, id)| GatewayModelDeployment {
                id: Uuid::from_u128(id),
                status: *status,
                ..template.clone()
            })
            .collect();

        model
    }

    #[test]
    fn the_serving_deployment_is_the_first_available_one() {
        let model = model_with(&[
            DeploymentStatus::Unavailable,
            DeploymentStatus::Available,
            DeploymentStatus::Available,
        ]);

        let serving = model.serving_deployment().expect("a deployment serves");
        assert_eq!(serving.deployment.id, Uuid::from_u128(2));
        assert_eq!(
            serving.release_digest,
            serving.deployment.served_release_digest().unwrap()
        );
    }

    #[test]
    fn a_model_without_an_available_deployment_has_none_to_serve() {
        for statuses in [
            &[][..],
            &[DeploymentStatus::Unavailable, DeploymentStatus::Draining][..],
        ] {
            let error = model_with(statuses).serving_deployment().unwrap_err();

            assert_eq!(error, ServingDeploymentError::Missing, "{statuses:?}");
            assert_eq!(error.diagnostic_code(), "no_serving_deployment");
        }
    }

    #[test]
    fn an_invalid_first_available_deployment_is_not_skipped() {
        let mut model = model_with(&[DeploymentStatus::Available, DeploymentStatus::Available]);
        model.deployments[0].service_url = "ftp://runtime.internal".to_owned();

        let error = model.serving_deployment().unwrap_err();
        assert_eq!(
            error,
            ServingDeploymentError::Invalid(DeploymentError::ServiceUrl)
        );
        assert_eq!(error.diagnostic_code(), "invalid_deployment");
    }

    #[test]
    fn the_serving_deployment_does_not_depend_on_the_model_status() {
        for status in [
            ModelStatus::Available,
            ModelStatus::Unavailable,
            ModelStatus::Retired,
        ] {
            let mut model = model_with(&[DeploymentStatus::Available]);
            model.status = status;

            assert_eq!(
                model
                    .serving_deployment()
                    .map(|serving| serving.deployment.id),
                Ok(Uuid::from_u128(1)),
                "{status:?}"
            );
        }
    }
}
