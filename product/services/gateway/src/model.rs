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
    #[validate(length(max = 100))]
    pub quantization: Option<String>,
    #[validate(length(max = 100))]
    pub tokenizer: Option<String>,
    #[validate(length(min = 1))]
    pub input_modalities: Vec<TextModality>,
    #[validate(length(min = 1))]
    pub output_modalities: Vec<TextModality>,
    #[validate(length(min = 1))]
    pub pricing: Vec<ModelPricingEntry>,
    #[validate(length(min = 1))]
    pub capacity: Vec<ModelCapacityEntry>,
    pub passthrough_parameters: HashMap<String, ModelParameterDescriptor>,
    pub deprecation_at: Option<DateTime<Utc>>,
    pub is_free: bool,
    pub discount_to_user: f64,
    #[validate(nested)]
    pub openrouter: Option<OpenRouterModelProperties>,
}

impl GatewayModelProperties {
    pub fn validate_for_serving(&self) -> Result<(), ModelPropertiesError> {
        <Self as Validate>::validate(self)
            .map_err(|error| ModelPropertiesError::Invalid(error.to_string()))?;
        self.validate_discount()?;
        self.validate_pricing()?;
        self.validate_capacity()?;
        self.validate_parameters()?;
        Ok(())
    }

    pub fn capacity_value(&self, metric: ModelCapacityMetric) -> Option<u64> {
        self.capacity
            .iter()
            .find(|entry| entry.metric == metric)
            .map(|entry| entry.value)
    }

    fn validate_discount(&self) -> Result<(), ModelPropertiesError> {
        if !self.discount_to_user.is_finite()
            || self.discount_to_user < 0.0
            || self.discount_to_user >= 1.0
        {
            return Err(ModelPropertiesError::Invalid(
                "discount_to_user must be at least zero and less than one".to_owned(),
            ));
        }
        Ok(())
    }

    fn validate_pricing(&self) -> Result<(), ModelPropertiesError> {
        let mut units = HashSet::new();
        if self.pricing.iter().any(|entry| !units.insert(entry.unit)) {
            return Err(ModelPropertiesError::Invalid(
                "pricing units must be unique".to_owned(),
            ));
        }
        Ok(())
    }

    fn validate_capacity(&self) -> Result<(), ModelPropertiesError> {
        let mut metrics = HashSet::new();
        if self
            .capacity
            .iter()
            .any(|entry| entry.value == 0 || !metrics.insert(entry.metric))
        {
            return Err(ModelPropertiesError::Invalid(
                "capacity metrics must be positive and unique".to_owned(),
            ));
        }
        if !metrics.contains(&ModelCapacityMetric::ContextTokens)
            || !metrics.contains(&ModelCapacityMetric::MaxOutputTokens)
        {
            return Err(ModelPropertiesError::Invalid(
                "context_tokens and max_output_tokens capacity are required".to_owned(),
            ));
        }
        Ok(())
    }

    fn validate_parameters(&self) -> Result<(), ModelPropertiesError> {
        for (name, descriptor) in &self.passthrough_parameters {
            if name.is_empty() || name.chars().count() > 100 {
                return Err(ModelPropertiesError::Invalid(
                    "passthrough parameter names must contain 1 to 100 characters".to_owned(),
                ));
            }
            descriptor.validate_for_serving()?;
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TextModality {
    #[serde(rename = "type")]
    pub kind: TextModalityKind,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TextModalityKind {
    Text,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelPricingEntry {
    pub unit: ModelPriceUnit,
    pub cost: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelPriceUnit {
    InputToken,
    OutputToken,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelCapacityEntry {
    pub metric: ModelCapacityMetric,
    pub value: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelCapacityMetric {
    ContextTokens,
    MaxOutputTokens,
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ModelParameterDescriptor {
    #[serde(rename = "type")]
    pub kind: ModelParameterType,
    pub minimum: Option<f64>,
    pub maximum: Option<f64>,
}

impl ModelParameterDescriptor {
    pub fn accepts(&self, value: &Value) -> bool {
        let measured = match self.kind {
            ModelParameterType::Boolean => return value.is_boolean(),
            ModelParameterType::Integer => value.as_f64().filter(|number| number.fract() == 0.0),
            ModelParameterType::Number => value.as_f64(),
            ModelParameterType::String => value.as_str().map(|text| text.chars().count() as f64),
        };
        measured.is_some_and(|number| {
            self.minimum.is_none_or(|minimum| number >= minimum)
                && self.maximum.is_none_or(|maximum| number <= maximum)
        })
    }

    fn validate_for_serving(&self) -> Result<(), ModelPropertiesError> {
        if self
            .minimum
            .zip(self.maximum)
            .is_some_and(|(minimum, maximum)| minimum > maximum)
        {
            return Err(ModelPropertiesError::Invalid(
                "parameter minimum cannot exceed maximum".to_owned(),
            ));
        }
        match self.kind {
            ModelParameterType::Boolean if self.minimum.is_some() || self.maximum.is_some() => {
                Err(ModelPropertiesError::Invalid(
                    "boolean parameters cannot have numeric bounds".to_owned(),
                ))
            }
            ModelParameterType::Integer
                if !integer_bounds(self.minimum) || !integer_bounds(self.maximum) =>
            {
                Err(ModelPropertiesError::Invalid(
                    "integer parameter bounds must be integers".to_owned(),
                ))
            }
            ModelParameterType::String
                if !string_bounds(self.minimum) || !string_bounds(self.maximum) =>
            {
                Err(ModelPropertiesError::Invalid(
                    "string parameter bounds must be nonnegative integers".to_owned(),
                ))
            }
            _ => Ok(()),
        }
    }
}

fn integer_bounds(bound: Option<f64>) -> bool {
    bound.is_none_or(|value| value.is_finite() && value.fract() == 0.0)
}

fn string_bounds(bound: Option<f64>) -> bool {
    bound.is_none_or(|value| value.is_finite() && value >= 0.0 && value.fract() == 0.0)
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ModelParameterType {
    Boolean,
    Integer,
    Number,
    String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Validate)]
#[serde(deny_unknown_fields)]
pub struct OpenRouterModelProperties {
    #[validate(length(min = 1, max = 300))]
    pub slug: String,
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
            "quantization": "4-bit",
            "tokenizer": "Qwen3",
            "input_modalities": [{"type": "text"}],
            "output_modalities": [{"type": "text"}],
            "pricing": [
                {"unit": "input_token", "cost": 0},
                {"unit": "output_token", "cost": 0}
            ],
            "capacity": [
                {"metric": "context_tokens", "value": 32768},
                {"metric": "max_output_tokens", "value": 4096}
            ],
            "passthrough_parameters": {
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "seed": {"type": "integer"},
                "user": {"type": "string", "maximum": 100}
            },
            "deprecation_at": null,
            "is_free": true,
            "discount_to_user": 0,
            "openrouter": null
        }))
        .expect("properties should deserialize")
    }

    #[test]
    fn validates_closed_model_policy_and_required_capacity() {
        let properties = properties();
        properties
            .validate_for_serving()
            .expect("properties should validate");
        assert_eq!(
            properties.capacity_value(ModelCapacityMetric::MaxOutputTokens),
            Some(4_096)
        );

        let mut missing_context = properties;
        missing_context
            .capacity
            .retain(|entry| entry.metric != ModelCapacityMetric::ContextTokens);
        assert!(missing_context.validate_for_serving().is_err());
    }

    #[test]
    fn parameter_descriptors_apply_outer_type_and_bounds() {
        let properties = properties();
        let temperature = &properties.passthrough_parameters["temperature"];
        let seed = &properties.passthrough_parameters["seed"];
        let user = &properties.passthrough_parameters["user"];

        assert!(temperature.accepts(&serde_json::json!(0.5)));
        assert!(!temperature.accepts(&serde_json::json!(3)));
        assert!(seed.accepts(&serde_json::json!(7)));
        assert!(!seed.accepts(&serde_json::json!(7.5)));
        assert!(user.accepts(&serde_json::json!("client-a")));
        assert!(!user.accepts(&serde_json::json!(false)));
    }
}
