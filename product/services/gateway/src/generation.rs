use std::collections::HashSet;

use chrono::{DateTime, Utc};
use serde::Serialize;
use thiserror::Error;
use uuid::Uuid;

use crate::{CapturedPricing, InputPriceType, OutputPriceType};

const MAX_JSON_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct NormalizedUsage {
    pub input_tokens: u64,
    pub cached_input_tokens: u64,
    pub cache_write_tokens: u64,
    pub output_tokens: u64,
    pub reasoning_tokens: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PricedUsage {
    pub pricing: GenerationPricing,
    pub usage: GenerationUsage,
}

impl PricedUsage {
    pub fn calculate(
        prices: &CapturedPricing,
        usage: NormalizedUsage,
    ) -> Result<Self, PricingError> {
        if usage.cached_input_tokens > usage.input_tokens {
            return Err(PricingError::CachedInputExceedsInput);
        }
        if usage.reasoning_tokens > usage.output_tokens {
            return Err(PricingError::ReasoningExceedsOutput);
        }
        if [
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.cache_write_tokens,
            usage.output_tokens,
            usage.reasoning_tokens,
        ]
        .into_iter()
        .any(|quantity| quantity > MAX_JSON_SAFE_INTEGER)
        {
            return Err(PricingError::ArithmeticOverflow);
        }

        let mut components = Vec::with_capacity(prices.input.len() + prices.output.len());
        add_component(
            &mut components,
            GenerationPriceUnit::InputToken,
            usage.input_tokens - usage.cached_input_tokens,
            input_price(prices, InputPriceType::Prompt)?,
        )?;
        add_component(
            &mut components,
            GenerationPriceUnit::CachedInputToken,
            usage.cached_input_tokens,
            input_price(prices, InputPriceType::CachedPrompt)?,
        )?;
        if let Some(unit_price) = optional_input_price(prices, InputPriceType::CacheWrite) {
            add_component(
                &mut components,
                GenerationPriceUnit::CacheWriteToken,
                usage.cache_write_tokens,
                unit_price,
            )?;
        }

        let reasoning_price = optional_output_price(prices, OutputPriceType::InternalReasoning);
        let visible_output_tokens = if reasoning_price.is_some() {
            usage.output_tokens - usage.reasoning_tokens
        } else {
            usage.output_tokens
        };
        add_component(
            &mut components,
            GenerationPriceUnit::OutputToken,
            visible_output_tokens,
            output_price(prices, OutputPriceType::Completion)?,
        )?;
        if let Some(unit_price) = reasoning_price {
            add_component(
                &mut components,
                GenerationPriceUnit::ReasoningToken,
                usage.reasoning_tokens,
                unit_price,
            )?;
        }

        let charge = components.iter().try_fold(0_u64, |total, component| {
            total
                .checked_add(component.amount)
                .filter(|total| *total <= MAX_JSON_SAFE_INTEGER)
                .ok_or(PricingError::ArithmeticOverflow)
        })?;

        Ok(Self {
            pricing: GenerationPricing {
                schema_version: 1,
                components,
            },
            usage: GenerationUsage {
                charge,
                input_tokens: usage.input_tokens,
                cached_input_tokens: usage.cached_input_tokens,
                cache_write_tokens: usage.cache_write_tokens,
                output_tokens: usage.output_tokens,
                reasoning_tokens: usage.reasoning_tokens,
            },
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationPricing {
    pub schema_version: u16,
    pub components: Vec<GenerationPriceComponent>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationPriceComponent {
    pub unit: GenerationPriceUnit,
    pub quantity: u64,
    pub unit_price: u64,
    pub amount: u64,
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GenerationPriceUnit {
    InputToken,
    CachedInputToken,
    CacheWriteToken,
    OutputToken,
    ReasoningToken,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationUsage {
    pub charge: u64,
    pub input_tokens: u64,
    pub cached_input_tokens: u64,
    pub cache_write_tokens: u64,
    pub output_tokens: u64,
    pub reasoning_tokens: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationProperties {
    pub event_schema_version: u16,
    pub external_id: Option<String>,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub api_key_id: Uuid,
    pub model_id: String,
    pub served_release_digest: String,
    pub status: GenerationStatus,
    pub streamed: bool,
    pub pricing: GenerationPricing,
    pub usage: GenerationUsage,
    pub outcome: GenerationOutcome,
    pub timing: GenerationTiming,
}

impl GenerationProperties {
    pub fn validate(&self) -> Result<(), GenerationPropertiesError> {
        if self.event_schema_version != 1 || self.pricing.schema_version != 1 {
            return Err(GenerationPropertiesError::UnsupportedSchemaVersion);
        }
        if self
            .external_id
            .as_ref()
            .is_some_and(|id| id.chars().count() > 300)
            || self.model_id.is_empty()
            || self.model_id.chars().count() > 200
            || !valid_release_digest(&self.served_release_digest)
            || self
                .outcome
                .finish_reason
                .as_ref()
                .is_some_and(|reason| reason.chars().count() > 100)
            || self
                .outcome
                .error_code
                .as_ref()
                .is_some_and(|code| code.chars().count() > 100)
        {
            return Err(GenerationPropertiesError::InvalidBoundedField);
        }
        validate_timing(&self.timing)?;
        validate_pricing(&self.pricing, &self.usage)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GenerationStatus {
    Succeeded,
    Failed,
    Cancelled,
    Abandoned,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationOutcome {
    pub finish_reason: Option<String>,
    pub error_code: Option<String>,
    pub usable_output_delivered: bool,
    pub cancellation_owner: Option<CancellationOwner>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CancellationOwner {
    Client,
    Server,
    Runtime,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationTiming {
    pub received_at: DateTime<Utc>,
    pub started_at: Option<DateTime<Utc>>,
    pub first_token_at: Option<DateTime<Utc>>,
    pub completed_at: DateTime<Utc>,
}

fn add_component(
    components: &mut Vec<GenerationPriceComponent>,
    unit: GenerationPriceUnit,
    quantity: u64,
    unit_price: u64,
) -> Result<(), PricingError> {
    if quantity > MAX_JSON_SAFE_INTEGER || unit_price > MAX_JSON_SAFE_INTEGER {
        return Err(PricingError::ArithmeticOverflow);
    }
    let amount = quantity
        .checked_mul(unit_price)
        .filter(|amount| *amount <= MAX_JSON_SAFE_INTEGER)
        .ok_or(PricingError::ArithmeticOverflow)?;
    components.push(GenerationPriceComponent {
        unit,
        quantity,
        unit_price,
        amount,
    });
    Ok(())
}

fn input_price(prices: &CapturedPricing, kind: InputPriceType) -> Result<u64, PricingError> {
    optional_input_price(prices, kind).ok_or(PricingError::MissingRequiredPrice)
}

fn optional_input_price(prices: &CapturedPricing, kind: InputPriceType) -> Option<u64> {
    prices
        .input
        .iter()
        .find(|price| price.kind() == kind)
        .map(|price| price.cost())
}

fn output_price(prices: &CapturedPricing, kind: OutputPriceType) -> Result<u64, PricingError> {
    optional_output_price(prices, kind).ok_or(PricingError::MissingRequiredPrice)
}

fn optional_output_price(prices: &CapturedPricing, kind: OutputPriceType) -> Option<u64> {
    prices
        .output
        .iter()
        .find(|price| price.kind() == kind)
        .map(|price| price.cost())
}

#[derive(Debug, Error)]
pub enum PricingError {
    #[error("cached input tokens cannot exceed input tokens")]
    CachedInputExceedsInput,
    #[error("reasoning tokens cannot exceed output tokens")]
    ReasoningExceedsOutput,
    #[error("captured pricing is missing a required component")]
    MissingRequiredPrice,
    #[error("generation pricing exceeds the supported integer range")]
    ArithmeticOverflow,
}

#[derive(Debug, Error)]
pub enum GenerationPropertiesError {
    #[error("generation properties use an unsupported schema version")]
    UnsupportedSchemaVersion,
    #[error("generation properties contain an invalid bounded field")]
    InvalidBoundedField,
    #[error("generation timing is inconsistent")]
    InvalidTiming,
    #[error("generation pricing components are inconsistent with usage")]
    InconsistentPricing,
    #[error("generation properties exceed the supported integer range")]
    ArithmeticOverflow,
}

fn valid_release_digest(digest: &str) -> bool {
    digest.len() == 71
        && digest.starts_with("sha256:")
        && digest[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_timing(timing: &GenerationTiming) -> Result<(), GenerationPropertiesError> {
    if timing.completed_at < timing.received_at {
        return Err(GenerationPropertiesError::InvalidTiming);
    }
    if timing.started_at.is_some_and(|started_at| {
        started_at < timing.received_at || started_at > timing.completed_at
    }) {
        return Err(GenerationPropertiesError::InvalidTiming);
    }
    if timing.first_token_at.is_some_and(|first_token_at| {
        timing
            .started_at
            .is_none_or(|started_at| first_token_at < started_at)
            || first_token_at > timing.completed_at
    }) {
        return Err(GenerationPropertiesError::InvalidTiming);
    }
    Ok(())
}

fn validate_pricing(
    pricing: &GenerationPricing,
    usage: &GenerationUsage,
) -> Result<(), GenerationPropertiesError> {
    let values = [
        usage.charge,
        usage.input_tokens,
        usage.cached_input_tokens,
        usage.cache_write_tokens,
        usage.output_tokens,
        usage.reasoning_tokens,
    ];
    if values
        .into_iter()
        .any(|value| value > MAX_JSON_SAFE_INTEGER)
    {
        return Err(GenerationPropertiesError::ArithmeticOverflow);
    }
    if usage.cached_input_tokens > usage.input_tokens
        || usage.reasoning_tokens > usage.output_tokens
    {
        return Err(GenerationPropertiesError::InconsistentPricing);
    }

    let mut units = HashSet::new();
    let mut charge = 0_u64;
    for component in &pricing.components {
        if !units.insert(component.unit)
            || component.quantity > MAX_JSON_SAFE_INTEGER
            || component.unit_price > MAX_JSON_SAFE_INTEGER
        {
            return Err(GenerationPropertiesError::InconsistentPricing);
        }
        let amount = component
            .quantity
            .checked_mul(component.unit_price)
            .filter(|amount| *amount <= MAX_JSON_SAFE_INTEGER)
            .ok_or(GenerationPropertiesError::ArithmeticOverflow)?;
        if amount != component.amount {
            return Err(GenerationPropertiesError::InconsistentPricing);
        }
        charge = charge
            .checked_add(amount)
            .filter(|charge| *charge <= MAX_JSON_SAFE_INTEGER)
            .ok_or(GenerationPropertiesError::ArithmeticOverflow)?;
    }
    if charge != usage.charge
        || component_quantity(pricing, GenerationPriceUnit::InputToken)
            != Some(usage.input_tokens - usage.cached_input_tokens)
        || component_quantity(pricing, GenerationPriceUnit::CachedInputToken)
            != Some(usage.cached_input_tokens)
        || component_quantity(pricing, GenerationPriceUnit::CacheWriteToken)
            .is_some_and(|quantity| quantity != usage.cache_write_tokens)
        || component_quantity(pricing, GenerationPriceUnit::ReasoningToken)
            .is_some_and(|quantity| quantity != usage.reasoning_tokens)
    {
        return Err(GenerationPropertiesError::InconsistentPricing);
    }
    let expected_output = if units.contains(&GenerationPriceUnit::ReasoningToken) {
        usage.output_tokens - usage.reasoning_tokens
    } else {
        usage.output_tokens
    };
    if component_quantity(pricing, GenerationPriceUnit::OutputToken) != Some(expected_output) {
        return Err(GenerationPropertiesError::InconsistentPricing);
    }
    Ok(())
}

fn component_quantity(pricing: &GenerationPricing, unit: GenerationPriceUnit) -> Option<u64> {
    pricing
        .components
        .iter()
        .find(|component| component.unit == unit)
        .map(|component| component.quantity)
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;
    use serde_json::Value;

    use super::*;
    use crate::{InputTokenPrice, OutputTokenPrice, TokenUnit};

    fn prices() -> CapturedPricing {
        CapturedPricing {
            input: vec![
                InputTokenPrice::Prompt {
                    unit: TokenUnit::Token,
                    cost: 10,
                },
                InputTokenPrice::CachedPrompt {
                    unit: TokenUnit::Token,
                    cost: 2,
                },
                InputTokenPrice::CacheWrite {
                    unit: TokenUnit::Token,
                    cost: 4,
                },
            ],
            output: vec![
                OutputTokenPrice::Completion {
                    unit: TokenUnit::Token,
                    cost: 20,
                },
                OutputTokenPrice::InternalReasoning {
                    unit: TokenUnit::Token,
                    cost: 5,
                },
            ],
        }
    }

    #[test]
    fn calculates_every_configured_component_in_canonical_order() {
        let priced = PricedUsage::calculate(
            &prices(),
            NormalizedUsage {
                input_tokens: 100,
                cached_input_tokens: 25,
                cache_write_tokens: 10,
                output_tokens: 40,
                reasoning_tokens: 10,
            },
        )
        .unwrap();

        assert_eq!(
            priced.pricing.components,
            vec![
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::InputToken,
                    quantity: 75,
                    unit_price: 10,
                    amount: 750,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::CachedInputToken,
                    quantity: 25,
                    unit_price: 2,
                    amount: 50,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::CacheWriteToken,
                    quantity: 10,
                    unit_price: 4,
                    amount: 40,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::OutputToken,
                    quantity: 30,
                    unit_price: 20,
                    amount: 600,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::ReasoningToken,
                    quantity: 10,
                    unit_price: 5,
                    amount: 50,
                },
            ]
        );
        assert_eq!(priced.usage.charge, 1_490);
    }

    #[test]
    fn rejects_inconsistent_usage_and_unsafe_money() {
        assert!(matches!(
            PricedUsage::calculate(
                &prices(),
                NormalizedUsage {
                    input_tokens: 1,
                    cached_input_tokens: 2,
                    ..NormalizedUsage::default()
                },
            ),
            Err(PricingError::CachedInputExceedsInput)
        ));

        let mut prices = prices();
        prices.input[0] = InputTokenPrice::Prompt {
            unit: TokenUnit::Token,
            cost: MAX_JSON_SAFE_INTEGER,
        };
        assert!(matches!(
            PricedUsage::calculate(
                &prices,
                NormalizedUsage {
                    input_tokens: 2,
                    ..NormalizedUsage::default()
                },
            ),
            Err(PricingError::ArithmeticOverflow)
        ));
    }

    #[test]
    fn serializes_the_closed_generation_properties_shape() {
        let priced = PricedUsage::calculate(&prices(), NormalizedUsage::default()).unwrap();
        let properties = GenerationProperties {
            event_schema_version: 1,
            external_id: None,
            organization_id: Uuid::nil(),
            workspace_id: Uuid::nil(),
            api_key_id: Uuid::nil(),
            model_id: "model-a".to_owned(),
            served_release_digest: format!("sha256:{}", "a".repeat(64)),
            status: GenerationStatus::Succeeded,
            streamed: false,
            pricing: priced.pricing,
            usage: priced.usage,
            outcome: GenerationOutcome {
                finish_reason: Some("stop".to_owned()),
                error_code: None,
                usable_output_delivered: true,
                cancellation_owner: None,
            },
            timing: GenerationTiming {
                received_at: Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap(),
                started_at: None,
                first_token_at: None,
                completed_at: Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 1).unwrap(),
            },
        };

        properties.validate().unwrap();
        let value = serde_json::to_value(properties).unwrap();
        assert_eq!(value["event_schema_version"], 1);
        assert_eq!(value["status"], "succeeded");
        assert_eq!(value["pricing"]["schema_version"], 1);
        assert_eq!(value["outcome"]["cancellation_owner"], Value::Null);
        assert!(value.get("settlement").is_none());
        assert_eq!(value.as_object().unwrap().len(), 13);
    }

    #[test]
    fn rejects_properties_when_charge_does_not_match_components() {
        let priced = PricedUsage::calculate(&prices(), NormalizedUsage::default()).unwrap();
        let mut usage = priced.usage;
        usage.charge = 1;
        let properties = GenerationProperties {
            event_schema_version: 1,
            external_id: None,
            organization_id: Uuid::nil(),
            workspace_id: Uuid::nil(),
            api_key_id: Uuid::nil(),
            model_id: "model-a".to_owned(),
            served_release_digest: format!("sha256:{}", "a".repeat(64)),
            status: GenerationStatus::Failed,
            streamed: false,
            pricing: priced.pricing,
            usage,
            outcome: GenerationOutcome {
                finish_reason: None,
                error_code: Some("runtime_error".to_owned()),
                usable_output_delivered: false,
                cancellation_owner: None,
            },
            timing: GenerationTiming {
                received_at: Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap(),
                started_at: None,
                first_token_at: None,
                completed_at: Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 1).unwrap(),
            },
        };

        assert!(matches!(
            properties.validate(),
            Err(GenerationPropertiesError::InconsistentPricing)
        ));
    }
}
