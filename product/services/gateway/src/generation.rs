use std::collections::HashSet;

use chrono::{DateTime, Utc};
use serde::Serialize;
use thiserror::Error;
use uuid::Uuid;

use crate::{InputPriceType, InputTokenPrice, OutputPriceType, OutputTokenPrice, ServiceTier};

const MAX_JSON_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, PartialEq)]
pub struct CapturedPricing {
    prompt: u64,
    cached_prompt: u64,
    cache_write: Option<u64>,
    completion: u64,
    internal_reasoning: Option<u64>,
}

impl CapturedPricing {
    pub fn new(
        input: &[InputTokenPrice],
        output: &[OutputTokenPrice],
    ) -> Result<Self, CapturedPricingError> {
        Self::for_service_tier(input, output, ServiceTier::Default)
    }

    pub fn for_service_tier(
        input: &[InputTokenPrice],
        output: &[OutputTokenPrice],
        service_tier: ServiceTier,
    ) -> Result<Self, CapturedPricingError> {
        if !distinct(input.iter().map(InputTokenPrice::kind))
            || !distinct(output.iter().map(OutputTokenPrice::kind))
        {
            return Err(CapturedPricingError::DuplicateComponent);
        }

        if input
            .iter()
            .map(InputTokenPrice::cost)
            .chain(output.iter().map(OutputTokenPrice::cost))
            .any(|cost| cost > MAX_JSON_SAFE_INTEGER)
        {
            return Err(CapturedPricingError::UnsafeInteger);
        }

        Ok(Self {
            prompt: tier_price(input_price(input, InputPriceType::Prompt)?, service_tier)?,
            cached_prompt: tier_price(
                input_price(input, InputPriceType::CachedPrompt)?,
                service_tier,
            )?,
            cache_write: optional_input_price(input, InputPriceType::CacheWrite)
                .map(|price| tier_price(price, service_tier))
                .transpose()?,
            completion: tier_price(
                output_price(output, OutputPriceType::Completion)?,
                service_tier,
            )?,
            internal_reasoning: optional_output_price(output, OutputPriceType::InternalReasoning)
                .map(|price| tier_price(price, service_tier))
                .transpose()?,
        })
    }

    pub fn prompt(&self) -> u64 {
        self.prompt
    }

    pub fn cached_prompt(&self) -> u64 {
        self.cached_prompt
    }

    pub fn cache_write(&self) -> Option<u64> {
        self.cache_write
    }

    pub fn completion(&self) -> u64 {
        self.completion
    }

    pub fn internal_reasoning(&self) -> Option<u64> {
        self.internal_reasoning
    }

    /// Each billed token category with its quantity and unit price. Cache writes
    /// and reasoning are billed on their own only when they carry a price;
    /// otherwise reasoning is billed as output.
    fn billed_quantities(&self, usage: NormalizedUsage) -> Vec<(GenerationPriceUnit, u64, u64)> {
        let mut billed = vec![
            (
                GenerationPriceUnit::Input,
                usage.input_tokens - usage.cached_input_tokens,
                self.prompt,
            ),
            (
                GenerationPriceUnit::CachedInput,
                usage.cached_input_tokens,
                self.cached_prompt,
            ),
        ];

        if let Some(unit_price) = self.cache_write {
            billed.push((
                GenerationPriceUnit::CacheWrite,
                usage.cache_write_tokens,
                unit_price,
            ));
        }

        match self.internal_reasoning {
            Some(unit_price) => {
                billed.push((
                    GenerationPriceUnit::Output,
                    usage.output_tokens - usage.reasoning_tokens,
                    self.completion,
                ));
                billed.push((
                    GenerationPriceUnit::Reasoning,
                    usage.reasoning_tokens,
                    unit_price,
                ));
            }
            None => billed.push((
                GenerationPriceUnit::Output,
                usage.output_tokens,
                self.completion,
            )),
        }

        billed
    }
}

fn distinct<K: Eq + std::hash::Hash>(kinds: impl ExactSizeIterator<Item = K>) -> bool {
    let count = kinds.len();

    kinds.collect::<HashSet<_>>().len() == count
}

fn tier_price(default_price: u64, service_tier: ServiceTier) -> Result<u64, CapturedPricingError> {
    let (numerator, denominator) = service_tier.price_ratio();
    let adjusted = u128::from(default_price)
        .checked_mul(u128::from(numerator))
        .ok_or(CapturedPricingError::UnsafeInteger)?
        / u128::from(denominator);

    u64::try_from(adjusted)
        .ok()
        .filter(|price| *price <= MAX_JSON_SAFE_INTEGER)
        .ok_or(CapturedPricingError::UnsafeInteger)
}

fn input_price(
    prices: &[InputTokenPrice],
    kind: InputPriceType,
) -> Result<u64, CapturedPricingError> {
    optional_input_price(prices, kind).ok_or(CapturedPricingError::MissingRequiredComponent)
}

fn optional_input_price(prices: &[InputTokenPrice], kind: InputPriceType) -> Option<u64> {
    prices
        .iter()
        .find(|price| price.kind() == kind)
        .map(InputTokenPrice::cost)
}

fn output_price(
    prices: &[OutputTokenPrice],
    kind: OutputPriceType,
) -> Result<u64, CapturedPricingError> {
    optional_output_price(prices, kind).ok_or(CapturedPricingError::MissingRequiredComponent)
}

fn optional_output_price(prices: &[OutputTokenPrice], kind: OutputPriceType) -> Option<u64> {
    prices
        .iter()
        .find(|price| price.kind() == kind)
        .map(OutputTokenPrice::cost)
}

#[derive(Debug, Error)]
pub enum CapturedPricingError {
    #[error("captured pricing contains a duplicate component")]
    DuplicateComponent,
    #[error("captured pricing is missing a required component")]
    MissingRequiredComponent,
    #[error("captured pricing exceeds the supported integer range")]
    UnsafeInteger,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct NormalizedUsage {
    input_tokens: u64,
    cached_input_tokens: u64,
    cache_write_tokens: u64,
    output_tokens: u64,
    reasoning_tokens: u64,
}

impl NormalizedUsage {
    pub fn new(
        input_tokens: u64,
        cached_input_tokens: u64,
        cache_write_tokens: u64,
        output_tokens: u64,
        reasoning_tokens: u64,
    ) -> Result<Self, UsageError> {
        if cached_input_tokens > input_tokens {
            return Err(UsageError::CachedInputExceedsInput);
        }
        if reasoning_tokens > output_tokens {
            return Err(UsageError::ReasoningExceedsOutput);
        }
        if [
            input_tokens,
            cached_input_tokens,
            cache_write_tokens,
            output_tokens,
            reasoning_tokens,
        ]
        .into_iter()
        .any(|quantity| quantity > MAX_JSON_SAFE_INTEGER)
        {
            return Err(UsageError::UnsafeInteger);
        }

        Ok(Self {
            input_tokens,
            cached_input_tokens,
            cache_write_tokens,
            output_tokens,
            reasoning_tokens,
        })
    }

    pub fn zero() -> Self {
        Self {
            input_tokens: 0,
            cached_input_tokens: 0,
            cache_write_tokens: 0,
            output_tokens: 0,
            reasoning_tokens: 0,
        }
    }

    pub fn input_tokens(self) -> u64 {
        self.input_tokens
    }

    pub fn cached_input_tokens(self) -> u64 {
        self.cached_input_tokens
    }

    pub fn cache_write_tokens(self) -> u64 {
        self.cache_write_tokens
    }

    pub fn output_tokens(self) -> u64 {
        self.output_tokens
    }

    pub fn reasoning_tokens(self) -> u64 {
        self.reasoning_tokens
    }
}

#[derive(Debug, Error)]
pub enum UsageError {
    #[error("cached input tokens cannot exceed input tokens")]
    CachedInputExceedsInput,
    #[error("reasoning tokens cannot exceed output tokens")]
    ReasoningExceedsOutput,
    #[error("token usage exceeds the supported integer range")]
    UnsafeInteger,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PricedUsage {
    pricing: GenerationPricing,
    usage: GenerationUsage,
}

impl PricedUsage {
    pub fn calculate(
        prices: &CapturedPricing,
        usage: NormalizedUsage,
    ) -> Result<Self, PricingError> {
        let components = prices
            .billed_quantities(usage)
            .into_iter()
            .map(|(unit, quantity, unit_price)| price_component(unit, quantity, unit_price))
            .collect::<Result<Vec<_>, _>>()?;
        let charge = components.iter().try_fold(0_u64, |total, component| {
            total
                .checked_add(component.amount)
                .filter(|total| *total <= MAX_JSON_SAFE_INTEGER)
                .ok_or(PricingError::ArithmeticOverflow)
        })?;

        Ok(Self::from_parts(components, charge, usage))
    }

    pub fn charge(&self) -> u64 {
        self.usage.charge
    }

    /// Nothing billed, with the same components a priced generation would carry.
    pub(crate) fn zero(prices: &CapturedPricing) -> Self {
        let usage = NormalizedUsage::zero();
        let components = prices
            .billed_quantities(usage)
            .into_iter()
            .map(|(unit, quantity, unit_price)| GenerationPriceComponent {
                unit,
                quantity,
                unit_price,
                amount: 0,
            })
            .collect();

        Self::from_parts(components, 0, usage)
    }

    fn from_parts(
        components: Vec<GenerationPriceComponent>,
        charge: u64,
        usage: NormalizedUsage,
    ) -> Self {
        Self {
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
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct GenerationPricing {
    schema_version: u16,
    components: Vec<GenerationPriceComponent>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct GenerationPriceComponent {
    unit: GenerationPriceUnit,
    quantity: u64,
    unit_price: u64,
    amount: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum GenerationPriceUnit {
    #[serde(rename = "input_token")]
    Input,
    #[serde(rename = "cached_input_token")]
    CachedInput,
    #[serde(rename = "cache_write_token")]
    CacheWrite,
    #[serde(rename = "output_token")]
    Output,
    #[serde(rename = "reasoning_token")]
    Reasoning,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct GenerationUsage {
    charge: u64,
    input_tokens: u64,
    cached_input_tokens: u64,
    cache_write_tokens: u64,
    output_tokens: u64,
    reasoning_tokens: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationIdentity {
    external_id: Option<String>,
    organization_id: Uuid,
    workspace_id: Uuid,
    api_key_id: Uuid,
    model_id: String,
    served_release_digest: String,
}

impl GenerationIdentity {
    pub fn new(
        external_id: Option<String>,
        organization_id: Uuid,
        workspace_id: Uuid,
        api_key_id: Uuid,
        model_id: String,
        served_release_digest: String,
    ) -> Result<Self, GenerationIdentityError> {
        if external_id
            .as_ref()
            .is_some_and(|id| id.chars().count() > 300)
        {
            return Err(GenerationIdentityError::InvalidExternalId);
        }
        if model_id.is_empty() || model_id.chars().count() > 200 {
            return Err(GenerationIdentityError::InvalidModelId);
        }
        if !valid_release_digest(&served_release_digest) {
            return Err(GenerationIdentityError::InvalidReleaseDigest);
        }

        Ok(Self {
            external_id,
            organization_id,
            workspace_id,
            api_key_id,
            model_id,
            served_release_digest,
        })
    }
}

#[derive(Debug, Error)]
pub enum GenerationIdentityError {
    #[error("external generation ID exceeds 300 characters")]
    InvalidExternalId,
    #[error("model ID must contain between 1 and 200 characters")]
    InvalidModelId,
    #[error("served release digest must be a lowercase SHA-256 digest")]
    InvalidReleaseDigest,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GenerationStatus {
    Succeeded,
    Failed,
    Cancelled,
    Abandoned,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TerminalOutcome {
    status: GenerationStatus,
    outcome: GenerationOutcome,
}

impl TerminalOutcome {
    pub fn new(
        status: GenerationStatus,
        finish_reason: Option<String>,
        error_code: Option<String>,
        usable_output_delivered: bool,
        cancellation_owner: Option<CancellationOwner>,
    ) -> Result<Self, TerminalOutcomeError> {
        if finish_reason
            .as_ref()
            .is_some_and(|reason| reason.chars().count() > 100)
        {
            return Err(TerminalOutcomeError::InvalidFinishReason);
        }
        if error_code
            .as_ref()
            .is_some_and(|code| code.chars().count() > 100)
        {
            return Err(TerminalOutcomeError::InvalidErrorCode);
        }
        let cancellation_expected = matches!(
            status,
            GenerationStatus::Cancelled | GenerationStatus::Abandoned
        );
        if cancellation_expected != cancellation_owner.is_some() {
            return Err(TerminalOutcomeError::InvalidCancellationOwner);
        }

        Ok(Self {
            status,
            outcome: GenerationOutcome {
                finish_reason,
                error_code,
                usable_output_delivered,
                cancellation_owner,
            },
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct GenerationOutcome {
    finish_reason: Option<String>,
    error_code: Option<String>,
    usable_output_delivered: bool,
    cancellation_owner: Option<CancellationOwner>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CancellationOwner {
    Client,
    Server,
    Runtime,
}

impl CancellationOwner {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Client => "client",
            Self::Server => "server",
            Self::Runtime => "runtime",
        }
    }
}

#[derive(Debug, Error)]
pub enum TerminalOutcomeError {
    #[error("finish reason exceeds 100 characters")]
    InvalidFinishReason,
    #[error("error code exceeds 100 characters")]
    InvalidErrorCode,
    #[error("cancellation owner is inconsistent with generation status")]
    InvalidCancellationOwner,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationTiming {
    received_at: DateTime<Utc>,
    started_at: Option<DateTime<Utc>>,
    first_token_at: Option<DateTime<Utc>>,
    completed_at: DateTime<Utc>,
}

impl GenerationTiming {
    pub fn new(
        received_at: DateTime<Utc>,
        started_at: Option<DateTime<Utc>>,
        first_token_at: Option<DateTime<Utc>>,
        completed_at: DateTime<Utc>,
    ) -> Result<Self, GenerationTimingError> {
        if completed_at < received_at
            || started_at
                .is_some_and(|started_at| started_at < received_at || started_at > completed_at)
            || first_token_at.is_some_and(|first_token_at| {
                started_at.is_none_or(|started_at| first_token_at < started_at)
                    || first_token_at > completed_at
            })
        {
            return Err(GenerationTimingError::Inconsistent);
        }

        Ok(Self {
            received_at,
            started_at,
            first_token_at,
            completed_at,
        })
    }
}

#[derive(Debug, Error)]
pub enum GenerationTimingError {
    #[error("generation timing is inconsistent")]
    Inconsistent,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GenerationProperties {
    event_schema_version: u16,
    service_tier: ServiceTier,
    #[serde(flatten)]
    identity: GenerationIdentity,
    status: GenerationStatus,
    streamed: bool,
    pricing: GenerationPricing,
    usage: GenerationUsage,
    outcome: GenerationOutcome,
    timing: GenerationTiming,
}

impl GenerationProperties {
    pub fn new(
        identity: GenerationIdentity,
        service_tier: ServiceTier,
        streamed: bool,
        priced_usage: PricedUsage,
        terminal: TerminalOutcome,
        timing: GenerationTiming,
    ) -> Self {
        Self {
            event_schema_version: 2,
            service_tier,
            identity,
            status: terminal.status,
            streamed,
            pricing: priced_usage.pricing,
            usage: priced_usage.usage,
            outcome: terminal.outcome,
            timing,
        }
    }

    pub fn organization_id(&self) -> Uuid {
        self.identity.organization_id
    }

    pub fn charge(&self) -> u64 {
        self.usage.charge
    }
}

fn price_component(
    unit: GenerationPriceUnit,
    quantity: u64,
    unit_price: u64,
) -> Result<GenerationPriceComponent, PricingError> {
    if unit_price > MAX_JSON_SAFE_INTEGER {
        return Err(PricingError::ArithmeticOverflow);
    }

    let amount = quantity
        .checked_mul(unit_price)
        .filter(|amount| *amount <= MAX_JSON_SAFE_INTEGER)
        .ok_or(PricingError::ArithmeticOverflow)?;

    Ok(GenerationPriceComponent {
        unit,
        quantity,
        unit_price,
        amount,
    })
}

fn valid_release_digest(digest: &str) -> bool {
    digest.len() == 71
        && digest.starts_with("sha256:")
        && digest[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[derive(Debug, Error)]
pub enum PricingError {
    #[error("generation pricing exceeds the supported integer range")]
    ArithmeticOverflow,
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;
    use serde_json::Value;

    use super::*;
    use crate::{InputTokenPrice, OutputTokenPrice, TokenUnit};

    fn prices() -> CapturedPricing {
        CapturedPricing::new(
            &[
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
            &[
                OutputTokenPrice::Completion {
                    unit: TokenUnit::Token,
                    cost: 20,
                },
                OutputTokenPrice::InternalReasoning {
                    unit: TokenUnit::Token,
                    cost: 5,
                },
            ],
        )
        .unwrap()
    }

    fn identity() -> GenerationIdentity {
        GenerationIdentity::new(
            None,
            Uuid::nil(),
            Uuid::nil(),
            Uuid::nil(),
            "model-a".to_owned(),
            format!("sha256:{}", "a".repeat(64)),
        )
        .unwrap()
    }

    fn timing() -> GenerationTiming {
        GenerationTiming::new(
            Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap(),
            None,
            None,
            Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 1).unwrap(),
        )
        .unwrap()
    }

    #[test]
    fn normalized_usage_rejects_invalid_state_at_construction() {
        assert!(matches!(
            NormalizedUsage::new(1, 2, 0, 0, 0),
            Err(UsageError::CachedInputExceedsInput)
        ));
        assert!(matches!(
            NormalizedUsage::new(0, 0, 0, 1, 2),
            Err(UsageError::ReasoningExceedsOutput)
        ));
        assert!(matches!(
            NormalizedUsage::new(MAX_JSON_SAFE_INTEGER + 1, 0, 0, 0, 0),
            Err(UsageError::UnsafeInteger)
        ));
    }

    #[test]
    fn captured_pricing_rejects_invalid_state_at_construction() {
        assert!(matches!(
            CapturedPricing::new(
                &[InputTokenPrice::Prompt {
                    unit: TokenUnit::Token,
                    cost: 1,
                }],
                &[OutputTokenPrice::Completion {
                    unit: TokenUnit::Token,
                    cost: 1,
                }],
            ),
            Err(CapturedPricingError::MissingRequiredComponent)
        ));
        assert!(matches!(
            CapturedPricing::new(
                &[
                    InputTokenPrice::Prompt {
                        unit: TokenUnit::Token,
                        cost: 1,
                    },
                    InputTokenPrice::Prompt {
                        unit: TokenUnit::Token,
                        cost: 1,
                    },
                ],
                &[OutputTokenPrice::Completion {
                    unit: TokenUnit::Token,
                    cost: 1,
                }],
            ),
            Err(CapturedPricingError::DuplicateComponent)
        ));
    }

    #[test]
    fn captured_pricing_applies_each_tier_ratio_with_floor_rounding() {
        let input = [
            InputTokenPrice::Prompt {
                unit: TokenUnit::Token,
                cost: 11,
            },
            InputTokenPrice::CachedPrompt {
                unit: TokenUnit::Token,
                cost: 1,
            },
        ];
        let output = [OutputTokenPrice::Completion {
            unit: TokenUnit::Token,
            cost: 11,
        }];

        let flex = CapturedPricing::for_service_tier(&input, &output, ServiceTier::Flex).unwrap();
        assert_eq!(flex.prompt(), 7);
        assert_eq!(flex.cached_prompt(), 0);
        assert_eq!(flex.completion(), 7);

        let default =
            CapturedPricing::for_service_tier(&input, &output, ServiceTier::Default).unwrap();
        assert_eq!(default.prompt(), 11);
        assert_eq!(default.cached_prompt(), 1);
        assert_eq!(default.completion(), 11);

        let fast = CapturedPricing::for_service_tier(&input, &output, ServiceTier::Fast).unwrap();
        assert_eq!(fast.prompt(), 16);
        assert_eq!(fast.cached_prompt(), 1);
        assert_eq!(fast.completion(), 16);
    }

    #[test]
    fn calculates_every_configured_component_in_canonical_order() {
        let priced = PricedUsage::calculate(
            &prices(),
            NormalizedUsage::new(100, 25, 10, 40, 10).unwrap(),
        )
        .unwrap();

        assert_eq!(
            priced.pricing.components,
            vec![
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::Input,
                    quantity: 75,
                    unit_price: 10,
                    amount: 750,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::CachedInput,
                    quantity: 25,
                    unit_price: 2,
                    amount: 50,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::CacheWrite,
                    quantity: 10,
                    unit_price: 4,
                    amount: 40,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::Output,
                    quantity: 30,
                    unit_price: 20,
                    amount: 600,
                },
                GenerationPriceComponent {
                    unit: GenerationPriceUnit::Reasoning,
                    quantity: 10,
                    unit_price: 5,
                    amount: 50,
                },
            ]
        );
        assert_eq!(priced.charge(), 1_490);
    }

    #[test]
    fn zero_usage_preserves_every_captured_price_component() {
        let priced = PricedUsage::zero(&prices());

        assert_eq!(priced.charge(), 0);
        assert_eq!(priced.pricing.components.len(), 5);
        assert!(priced
            .pricing
            .components
            .iter()
            .all(|component| component.quantity == 0 && component.amount == 0));
    }

    #[test]
    fn pricing_rejects_unsafe_money() {
        let prices = CapturedPricing::new(
            &[
                InputTokenPrice::Prompt {
                    unit: TokenUnit::Token,
                    cost: MAX_JSON_SAFE_INTEGER,
                },
                InputTokenPrice::CachedPrompt {
                    unit: TokenUnit::Token,
                    cost: 0,
                },
            ],
            &[OutputTokenPrice::Completion {
                unit: TokenUnit::Token,
                cost: 0,
            }],
        )
        .unwrap();
        assert!(matches!(
            PricedUsage::calculate(&prices, NormalizedUsage::new(2, 0, 0, 0, 0).unwrap(),),
            Err(PricingError::ArithmeticOverflow)
        ));
    }

    #[test]
    fn identity_outcome_and_timing_reject_invalid_state_at_construction() {
        assert!(matches!(
            GenerationIdentity::new(
                None,
                Uuid::nil(),
                Uuid::nil(),
                Uuid::nil(),
                String::new(),
                format!("sha256:{}", "a".repeat(64)),
            ),
            Err(GenerationIdentityError::InvalidModelId)
        ));
        assert!(matches!(
            TerminalOutcome::new(GenerationStatus::Cancelled, None, None, false, None,),
            Err(TerminalOutcomeError::InvalidCancellationOwner)
        ));
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 1).unwrap();
        assert!(matches!(
            GenerationTiming::new(
                received_at,
                None,
                None,
                received_at - chrono::TimeDelta::seconds(1),
            ),
            Err(GenerationTimingError::Inconsistent)
        ));
    }

    #[test]
    fn serializes_the_closed_generation_properties_shape() {
        let priced = PricedUsage::calculate(&prices(), NormalizedUsage::zero()).unwrap();
        let terminal = TerminalOutcome::new(
            GenerationStatus::Succeeded,
            Some("stop".to_owned()),
            None,
            true,
            None,
        )
        .unwrap();
        let properties = GenerationProperties::new(
            identity(),
            ServiceTier::Fast,
            false,
            priced,
            terminal,
            timing(),
        );

        let value = serde_json::to_value(properties).unwrap();
        assert_eq!(value["event_schema_version"], 2);
        assert_eq!(value["service_tier"], "fast");
        assert_eq!(value["status"], "succeeded");
        assert_eq!(value["pricing"]["schema_version"], 1);
        assert_eq!(value["outcome"]["cancellation_owner"], Value::Null);
        assert!(value.get("settlement").is_none());
        assert_eq!(value.as_object().unwrap().len(), 14);
    }
}
