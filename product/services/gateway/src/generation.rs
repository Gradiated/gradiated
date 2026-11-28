use std::collections::HashSet;

use chrono::{DateTime, Utc};
use serde::Serialize;
use thiserror::Error;
use uuid::Uuid;

use crate::{
    auth::AuthenticatedIdentity, GatewayError, InputPriceType, InputTokenPrice, OutputPriceType,
    OutputTokenPrice, ServiceTier,
};

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
    #[cfg(test)]
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

    /// OpenRouter bills reasoning as completion, so the cap is the lower of the two.
    pub(crate) fn price_cap(&self) -> crate::PriceCap {
        crate::PriceCap {
            prompt: self.prompt,
            completion: self
                .internal_reasoning
                .map_or(self.completion, |reasoning| reasoning.min(self.completion)),
        }
    }

    #[cfg(test)]
    pub fn prompt(&self) -> u64 {
        self.prompt
    }

    #[cfg(test)]
    pub fn cached_prompt(&self) -> u64 {
        self.cached_prompt
    }

    #[cfg(test)]
    pub fn completion(&self) -> u64 {
        self.completion
    }

    fn billed_quantities(&self, usage: NormalizedUsage) -> Vec<BilledQuantity> {
        let billed = |unit, quantity, unit_price| BilledQuantity {
            unit,
            quantity,
            unit_price,
        };
        let mut quantities = vec![
            billed(
                GenerationPriceUnit::Input,
                usage.input_tokens - usage.cached_input_tokens,
                self.prompt,
            ),
            billed(
                GenerationPriceUnit::CachedInput,
                usage.cached_input_tokens,
                self.cached_prompt,
            ),
        ];

        if let Some(unit_price) = self.cache_write {
            quantities.push(billed(
                GenerationPriceUnit::CacheWrite,
                usage.cache_write_tokens,
                unit_price,
            ));
        }

        match self.internal_reasoning {
            Some(unit_price) => {
                quantities.push(billed(
                    GenerationPriceUnit::Output,
                    usage.output_tokens - usage.reasoning_tokens,
                    self.completion,
                ));
                quantities.push(billed(
                    GenerationPriceUnit::Reasoning,
                    usage.reasoning_tokens,
                    unit_price,
                ));
            }
            None => quantities.push(billed(
                GenerationPriceUnit::Output,
                usage.output_tokens,
                self.completion,
            )),
        }

        quantities
    }
}

struct BilledQuantity {
    unit: GenerationPriceUnit,
    quantity: u64,
    unit_price: u64,
}

impl BilledQuantity {
    fn priced(self) -> Result<GenerationPriceComponent, PricingError> {
        let amount = self
            .quantity
            .checked_mul(self.unit_price)
            .filter(|amount| *amount <= MAX_JSON_SAFE_INTEGER)
            .ok_or(PricingError::ArithmeticOverflow)?;

        Ok(self.with_amount(amount))
    }

    fn with_amount(self, amount: u64) -> GenerationPriceComponent {
        GenerationPriceComponent {
            unit: self.unit,
            quantity: self.quantity,
            unit_price: self.unit_price,
            amount,
        }
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

fn valid_estimated_joules(joules: Option<f64>) -> Option<f64> {
    joules.filter(|value| value.is_finite() && *value >= 0.0)
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct NormalizedUsage {
    estimated_joules: Option<f64>,
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
            estimated_joules: None,
            input_tokens,
            cached_input_tokens,
            cache_write_tokens,
            output_tokens,
            reasoning_tokens,
        })
    }

    pub fn zero() -> Self {
        Self {
            estimated_joules: None,
            input_tokens: 0,
            cached_input_tokens: 0,
            cache_write_tokens: 0,
            output_tokens: 0,
            reasoning_tokens: 0,
        }
    }

    pub(crate) fn is_zero(self) -> bool {
        self.input_tokens == 0
            && self.cached_input_tokens == 0
            && self.cache_write_tokens == 0
            && self.output_tokens == 0
            && self.reasoning_tokens == 0
    }

    pub fn with_estimated_joules(mut self, joules: Option<f64>) -> Self {
        self.estimated_joules = valid_estimated_joules(joules);
        self
    }

    pub fn estimated_joules(self) -> Option<f64> {
        self.estimated_joules
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
            .map(BilledQuantity::priced)
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

    pub(crate) fn zero(prices: &CapturedPricing) -> Self {
        let usage = NormalizedUsage::zero();
        let components = prices
            .billed_quantities(usage)
            .into_iter()
            .map(|billed| billed.with_amount(0))
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
    // The event contract keeps a nullable external ID that the gateway never sets.
    external_id: (),
    organization_id: Uuid,
    workspace_id: Uuid,
    api_key_id: Uuid,
    model_id: String,
    served_release_digest: String,
    /// `eval` for grad's eval traffic, so its usage is reported apart; absent otherwise.
    #[serde(skip_serializing_if = "Option::is_none")]
    lane: Option<crate::auth::Lane>,
    #[serde(skip_serializing_if = "Option::is_none")]
    eval_id: Option<String>,
}

impl GenerationIdentity {
    pub fn authenticated(
        caller: &AuthenticatedIdentity,
        model_id: String,
        served_release_digest: String,
    ) -> Result<Self, GenerationIdentityError> {
        if model_id.is_empty() || model_id.chars().count() > 300 {
            return Err(GenerationIdentityError::InvalidModelId);
        }

        if !valid_release_digest(&served_release_digest) {
            return Err(GenerationIdentityError::InvalidReleaseDigest);
        }

        Ok(Self {
            external_id: (),
            organization_id: caller.organization_id,
            workspace_id: caller.workspace_id,
            api_key_id: caller.api_key_id,
            model_id,
            served_release_digest,
            lane: (caller.lane == crate::auth::Lane::Eval).then_some(caller.lane),
            eval_id: caller.eval_id.clone(),
        })
    }

    /// The release that actually served. Our own digests are always well formed;
    /// a malformed one keeps the admitted identity rather than corrupting the event.
    pub(crate) fn serve_release(&mut self, served_release_digest: String) {
        if valid_release_digest(&served_release_digest) {
            self.served_release_digest = served_release_digest;
        }
    }

    #[cfg(test)]
    pub fn new(
        _external_id: Option<std::convert::Infallible>,
        organization_id: Uuid,
        workspace_id: Uuid,
        api_key_id: Uuid,
        model_id: String,
        served_release_digest: String,
    ) -> Result<Self, GenerationIdentityError> {
        let caller = AuthenticatedIdentity {
            api_key_id,
            organization_id,
            workspace_id,
            lane: crate::auth::Lane::Standard,
            eval_id: None,
        };

        Self::authenticated(&caller, model_id, served_release_digest)
    }
}

#[derive(Debug, Error)]
pub enum GenerationIdentityError {
    #[error("model ID must contain between 1 and 300 characters")]
    InvalidModelId,
    #[error("served release digest must be a lowercase SHA-256 digest")]
    InvalidReleaseDigest,
}

impl GenerationIdentityError {
    pub fn diagnostic_code(&self) -> &'static str {
        match self {
            Self::InvalidModelId => "invalid_model_id",
            Self::InvalidReleaseDigest => "invalid_release_digest",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GenerationStatus {
    Succeeded,
    Failed,
    Cancelled,
}

impl GenerationStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Succeeded => "succeeded",
            Self::Failed => "failed",
            Self::Cancelled => "cancelled",
        }
    }
}

const MAX_OUTCOME_CODE_CHARS: usize = 100;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FinishReason(String);

impl FinishReason {
    pub fn parse(reason: String) -> Option<Self> {
        let length = reason.chars().count();

        (1..=MAX_OUTCOME_CODE_CHARS)
            .contains(&length)
            .then_some(Self(reason))
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TerminalOutcome {
    status: GenerationStatus,
    outcome: GenerationOutcome,
}

impl TerminalOutcome {
    pub fn succeeded(reason: FinishReason, usable_output_delivered: bool) -> Self {
        Self::from_parts(
            GenerationStatus::Succeeded,
            Some(reason.0),
            None,
            usable_output_delivered,
            None,
        )
    }

    pub fn failed(error: &GatewayError, usable_output_delivered: bool) -> Self {
        Self::from_parts(
            GenerationStatus::Failed,
            None,
            Some(error.code()),
            usable_output_delivered,
            None,
        )
    }

    pub fn cancelled(
        owner: CancellationOwner,
        error: &GatewayError,
        usable_output_delivered: bool,
    ) -> Self {
        Self::from_parts(
            GenerationStatus::Cancelled,
            None,
            Some(error.code()),
            usable_output_delivered,
            Some(owner),
        )
    }

    pub fn status(&self) -> GenerationStatus {
        self.status
    }

    pub fn error_code(&self) -> Option<&str> {
        self.outcome.error_code.as_deref()
    }

    pub fn cancellation_owner(&self) -> Option<CancellationOwner> {
        self.outcome.cancellation_owner
    }

    fn from_parts(
        status: GenerationStatus,
        finish_reason: Option<String>,
        error_code: Option<&'static str>,
        usable_output_delivered: bool,
        cancellation_owner: Option<CancellationOwner>,
    ) -> Self {
        Self {
            status,
            outcome: GenerationOutcome {
                finish_reason,
                error_code: error_code.map(str::to_owned),
                usable_output_delivered,
                cancellation_owner,
            },
        }
    }

    #[cfg(test)]
    pub fn new(
        status: GenerationStatus,
        finish_reason: Option<String>,
        error_code: Option<String>,
        usable_output_delivered: bool,
        cancellation_owner: Option<CancellationOwner>,
    ) -> Result<Self, TerminalOutcomeError> {
        if finish_reason
            .as_ref()
            .is_some_and(|reason| reason.chars().count() > MAX_OUTCOME_CODE_CHARS)
        {
            return Err(TerminalOutcomeError::InvalidFinishReason);
        }

        if error_code
            .as_ref()
            .is_some_and(|code| code.chars().count() > MAX_OUTCOME_CODE_CHARS)
        {
            return Err(TerminalOutcomeError::InvalidErrorCode);
        }

        if (status == GenerationStatus::Cancelled) != cancellation_owner.is_some() {
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
}

impl CancellationOwner {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Client => "client",
            Self::Server => "server",
        }
    }
}

#[cfg(test)]
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
    started_at: DateTime<Utc>,
    first_token_at: Option<DateTime<Utc>>,
    completed_at: DateTime<Utc>,
}

impl GenerationTiming {
    pub fn ordered(
        received_at: DateTime<Utc>,
        started_at: DateTime<Utc>,
        first_token_at: Option<DateTime<Utc>>,
        now: DateTime<Utc>,
    ) -> Self {
        let started_at = started_at.max(received_at);
        let completed_at = now
            .max(started_at)
            .max(first_token_at.unwrap_or(started_at));

        Self {
            received_at,
            started_at,
            first_token_at: first_token_at.map(|first_token_at| first_token_at.max(started_at)),
            completed_at,
        }
    }

    pub fn received_at(&self) -> DateTime<Utc> {
        self.received_at
    }

    pub fn started_at(&self) -> DateTime<Utc> {
        self.started_at
    }

    pub fn first_token_at(&self) -> Option<DateTime<Utc>> {
        self.first_token_at
    }

    pub fn completed_at(&self) -> DateTime<Utc> {
        self.completed_at
    }

    #[cfg(test)]
    pub fn new(
        received_at: DateTime<Utc>,
        started_at: Option<DateTime<Utc>>,
        first_token_at: Option<DateTime<Utc>>,
        completed_at: DateTime<Utc>,
    ) -> Result<Self, GenerationTimingError> {
        let Some(started_at) = started_at else {
            return Err(GenerationTimingError::Inconsistent);
        };

        if started_at < received_at
            || started_at > completed_at
            || first_token_at.is_some_and(|first_token_at| {
                first_token_at < started_at || first_token_at > completed_at
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

#[cfg(test)]
#[derive(Debug, Error)]
pub enum GenerationTimingError {
    #[error("generation timing is inconsistent")]
    Inconsistent,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct GenerationProperties {
    #[serde(skip_serializing_if = "Option::is_none")]
    estimated_joules: Option<f64>,
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
            estimated_joules: None,
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

    pub fn with_estimated_joules(mut self, joules: Option<f64>) -> Self {
        self.estimated_joules = valid_estimated_joules(joules);
        self
    }

    pub fn organization_id(&self) -> Uuid {
        self.identity.organization_id
    }

    pub fn charge(&self) -> u64 {
        self.usage.charge
    }
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
pub(crate) mod fixtures {
    use super::CapturedPricing;
    use crate::{InputTokenPrice, OutputTokenPrice, TokenUnit};

    pub(crate) fn token_prices(
        prompt: u64,
        cached_prompt: u64,
        completion: u64,
    ) -> CapturedPricing {
        CapturedPricing::new(
            &[
                InputTokenPrice::Prompt {
                    unit: TokenUnit::Token,
                    cost: prompt,
                },
                InputTokenPrice::CachedPrompt {
                    unit: TokenUnit::Token,
                    cost: cached_prompt,
                },
            ],
            &[OutputTokenPrice::Completion {
                unit: TokenUnit::Token,
                cost: completion,
            }],
        )
        .expect("token prices are within range")
    }
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

    #[test]
    fn openrouter_may_charge_no_more_than_the_caller_pays() {
        assert_eq!(
            prices().price_cap(),
            crate::PriceCap {
                prompt: 10,
                completion: 5
            }
        );
        assert_eq!(
            fixtures::token_prices(30, 6, 1_200).price_cap(),
            crate::PriceCap {
                prompt: 30,
                completion: 1_200
            }
        );
    }

    fn caller() -> AuthenticatedIdentity {
        AuthenticatedIdentity {
            api_key_id: Uuid::from_u128(1),
            organization_id: Uuid::from_u128(2),
            workspace_id: Uuid::from_u128(3),
            lane: crate::auth::Lane::Standard,
            eval_id: None,
        }
    }

    fn identity() -> GenerationIdentity {
        GenerationIdentity::authenticated(
            &caller(),
            "model-a".to_owned(),
            format!("sha256:{}", "a".repeat(64)),
        )
        .unwrap()
    }

    fn timing() -> GenerationTiming {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();

        GenerationTiming::ordered(
            received_at,
            received_at,
            None,
            received_at + chrono::TimeDelta::seconds(1),
        )
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
        let prices = fixtures::token_prices(MAX_JSON_SAFE_INTEGER, 0, 0);

        assert!(matches!(
            PricedUsage::calculate(&prices, NormalizedUsage::new(2, 0, 0, 0, 0).unwrap()),
            Err(PricingError::ArithmeticOverflow)
        ));
    }

    #[test]
    fn identity_rejects_an_invalid_model_or_release_digest() {
        let digest = format!("sha256:{}", "a".repeat(64));

        assert!(matches!(
            GenerationIdentity::authenticated(&caller(), String::new(), digest.clone()),
            Err(GenerationIdentityError::InvalidModelId)
        ));
        assert!(matches!(
            GenerationIdentity::authenticated(&caller(), "x".repeat(301), digest),
            Err(GenerationIdentityError::InvalidModelId)
        ));
        assert!(matches!(
            GenerationIdentity::authenticated(
                &caller(),
                "model-a".to_owned(),
                format!("sha256:{}", "A".repeat(64)),
            ),
            Err(GenerationIdentityError::InvalidReleaseDigest)
        ));
    }

    #[test]
    fn finish_reasons_hold_one_to_one_hundred_characters() {
        assert!(FinishReason::parse(String::new()).is_none());
        assert!(FinishReason::parse("é".repeat(100)).is_some());
        assert!(FinishReason::parse("x".repeat(101)).is_none());
    }

    #[test]
    fn ordered_timing_is_consistent_whatever_the_clock_reports() {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        let started_at = received_at + chrono::TimeDelta::seconds(1);
        let now = received_at + chrono::TimeDelta::seconds(2);
        let consistent = |timing: &GenerationTiming| {
            let first_token_at = timing.first_token_at.unwrap_or(timing.started_at);

            timing.received_at <= timing.started_at
                && timing.started_at <= first_token_at
                && first_token_at <= timing.completed_at
        };

        let late = GenerationTiming::ordered(
            received_at,
            started_at,
            Some(now + chrono::TimeDelta::seconds(5)),
            now,
        );
        assert!(consistent(&late));
        assert_eq!(late.completed_at(), now + chrono::TimeDelta::seconds(5));

        let early = GenerationTiming::ordered(received_at, started_at, Some(received_at), now);
        assert!(consistent(&early));
        assert_eq!(early.first_token_at(), Some(started_at));
        assert_eq!(early.completed_at(), now);
    }

    #[test]
    fn status_and_cancellation_labels_match_their_serialized_names() {
        for status in [
            GenerationStatus::Succeeded,
            GenerationStatus::Failed,
            GenerationStatus::Cancelled,
        ] {
            assert_eq!(serde_json::to_value(status).unwrap(), status.as_str());
        }

        for owner in [CancellationOwner::Client, CancellationOwner::Server] {
            assert_eq!(serde_json::to_value(owner).unwrap(), owner.as_str());
        }
    }

    #[test]
    fn serializes_the_closed_generation_properties_shape() {
        let priced = PricedUsage::calculate(&prices(), NormalizedUsage::zero()).unwrap();
        let terminal =
            TerminalOutcome::succeeded(FinishReason::parse("stop".to_owned()).unwrap(), true);
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
        assert_eq!(value.get("external_id"), Some(&Value::Null));
        assert!(value.get("settlement").is_none());
        assert_eq!(value.as_object().unwrap().len(), 14);
    }
}
