use std::{sync::Arc, time::Duration};

use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::{
    generation::FinishReason,
    metrics::{AdmittedGenerationMetrics, FinalizationAttempt, TerminalRecord},
    CancellationOwner, CapturedPricing, FinalizationOutcome, GatewayError, GenerationIdentity,
    GenerationProperties, GenerationTiming, NormalizedUsage, PricedUsage, RuntimeFailure,
    RuntimeFailureKind, ServiceTier, ServingState, TerminalOutcome,
};

pub(super) const FINALIZATION_ATTEMPTS: usize = 3;
const FINALIZATION_RETRY_DELAY: Duration = Duration::from_millis(25);

pub(super) enum GenerationEnd {
    Succeeded(FinishReason),
    Unsuccessful(Unsuccessful),
}

impl GenerationEnd {
    pub(super) fn failed(error: GatewayError) -> Self {
        Self::Unsuccessful(Unsuccessful::Failed(error))
    }

    pub(super) fn cancelled(owner: CancellationOwner) -> Self {
        Self::Unsuccessful(Unsuccessful::Cancelled(owner))
    }

    pub(super) fn finished(reason: String, generation_id: Uuid) -> Self {
        match FinishReason::parse(reason) {
            Some(reason) => Self::Succeeded(reason),
            None => {
                crate::diagnostics::limited_warn!(%generation_id, phase = "completion",
                    error_code = "invalid_finish_reason", "runtime finish reason rejected");
                Self::failed(GatewayError::RuntimeUnavailable)
            }
        }
    }

    pub(super) fn public_error(&self) -> Option<GatewayError> {
        match self {
            Self::Succeeded(_) => None,
            Self::Unsuccessful(unsuccessful) => Some(unsuccessful.public_error()),
        }
    }

    fn outcome(&self, usable_output_delivered: bool) -> TerminalOutcome {
        match self {
            Self::Succeeded(reason) => {
                TerminalOutcome::succeeded(reason.clone(), usable_output_delivered)
            }
            Self::Unsuccessful(unsuccessful) => unsuccessful.outcome(usable_output_delivered),
        }
    }
}

pub(super) enum Unsuccessful {
    Failed(GatewayError),
    Cancelled(CancellationOwner),
}

impl Unsuccessful {
    pub(super) fn from_runtime_failure(failure: &RuntimeFailure) -> Self {
        if failure.kind() == RuntimeFailureKind::TimedOut {
            Self::Cancelled(CancellationOwner::Server)
        } else {
            Self::Failed(failure.gateway_error())
        }
    }

    fn public_error(&self) -> GatewayError {
        match self {
            Self::Failed(error) => error.clone(),
            Self::Cancelled(_) => GatewayError::RuntimeUnavailable,
        }
    }

    fn outcome(&self, usable_output_delivered: bool) -> TerminalOutcome {
        let error = self.public_error();

        match self {
            Self::Failed(_) => TerminalOutcome::failed(&error, usable_output_delivered),
            Self::Cancelled(owner) => {
                TerminalOutcome::cancelled(*owner, &error, usable_output_delivered)
            }
        }
    }
}

pub(super) enum Delivery {
    NoOutput,
    Buffered,
    Streamed { first_token_at: DateTime<Utc> },
}

impl Delivery {
    fn usable_output_delivered(&self, end: &GenerationEnd) -> bool {
        match self {
            Self::NoOutput => false,
            Self::Buffered => matches!(end, GenerationEnd::Succeeded(_)),
            Self::Streamed { .. } => true,
        }
    }

    fn first_token_at(&self) -> Option<DateTime<Utc>> {
        match self {
            Self::Streamed { first_token_at } => Some(*first_token_at),
            Self::NoOutput | Self::Buffered => None,
        }
    }
}

pub(super) struct GenerationTerminal {
    pub(super) end: GenerationEnd,
    pub(super) usage: NormalizedUsage,
    pub(super) delivery: Delivery,
}

pub(super) struct FailedGeneration {
    end: Unsuccessful,
    usage: NormalizedUsage,
}

impl FailedGeneration {
    pub(super) fn cancelled(owner: CancellationOwner) -> Self {
        Self {
            end: Unsuccessful::Cancelled(owner),
            usage: NormalizedUsage::zero(),
        }
    }

    pub(super) fn from_runtime_failure(failure: &RuntimeFailure) -> Self {
        Self {
            end: Unsuccessful::from_runtime_failure(failure),
            usage: failure.usage(),
        }
    }

    pub(super) fn panicked() -> Self {
        Self {
            end: Unsuccessful::Failed(GatewayError::RuntimeUnavailable),
            usage: NormalizedUsage::zero(),
        }
    }
}

pub(super) struct GenerationSettlement {
    pub(super) serving_state: Arc<dyn ServingState>,
    pub(super) generation_id: Uuid,
    pub(super) generation_identity: GenerationIdentity,
    pub(super) pricing: CapturedPricing,
    pub(super) service_tier: ServiceTier,
    pub(super) received_at: DateTime<Utc>,
    pub(super) started_at: DateTime<Utc>,
    pub(super) streamed: bool,
    pub(super) metrics: AdmittedGenerationMetrics,
}

impl GenerationSettlement {
    pub(super) async fn settle_failure(self, failed: FailedGeneration) -> GatewayError {
        let error = failed.end.public_error();
        let terminal = GenerationTerminal {
            end: GenerationEnd::Unsuccessful(failed.end),
            usage: failed.usage,
            delivery: Delivery::NoOutput,
        };

        match self.settle(terminal).await {
            Ok(_) => error,
            Err(finalization) => finalization,
        }
    }

    pub(super) async fn settle(
        self,
        terminal: GenerationTerminal,
    ) -> Result<GenerationEnd, GatewayError> {
        let GenerationTerminal {
            mut end,
            usage,
            delivery,
        } = terminal;

        let priced_usage = match PricedUsage::calculate(&self.pricing, usage) {
            Ok(priced_usage) => priced_usage,
            Err(_) => {
                crate::diagnostics::limited_error!(generation_id = %self.generation_id,
                    phase = "settlement", error_code = "pricing_overflow",
                    input_tokens = usage.input_tokens(),
                    cached_input_tokens = usage.cached_input_tokens(),
                    cache_write_tokens = usage.cache_write_tokens(),
                    output_tokens = usage.output_tokens(),
                    reasoning_tokens = usage.reasoning_tokens(),
                    "generation usage could not be priced; settling without a charge");
                if let GenerationEnd::Succeeded(_) = end {
                    end = GenerationEnd::failed(GatewayError::RuntimeUnavailable);
                }
                PricedUsage::zero(&self.pricing)
            }
        };

        let outcome = end.outcome(delivery.usable_output_delivered(&end));
        let timing = GenerationTiming::ordered(
            self.received_at,
            self.started_at,
            delivery.first_token_at(),
            Utc::now(),
        );
        self.metrics.record_terminal(&TerminalRecord {
            generation_id: self.generation_id,
            outcome: &outcome,
            usage,
            charge_nano_usd: priced_usage.charge(),
            timing: &timing,
        });

        let properties = GenerationProperties::new(
            self.generation_identity.clone(),
            self.service_tier,
            self.streamed,
            priced_usage,
            outcome,
            timing,
        );
        self.finalize(&properties).await?;

        Ok(end)
    }

    async fn finalize(&self, properties: &GenerationProperties) -> Result<(), GatewayError> {
        let generation_id = self.generation_id;
        let organization_id = properties.organization_id();
        let mut attempt = 1;

        loop {
            let result = self
                .serving_state
                .finalize(generation_id, organization_id, properties)
                .await;

            match result {
                Ok(FinalizationOutcome::Settled) => {
                    self.metrics
                        .record_finalization_attempt(FinalizationAttempt::Settled);
                    return Ok(());
                }
                Ok(FinalizationOutcome::AlreadyAbsent) => {
                    self.metrics
                        .record_finalization_attempt(FinalizationAttempt::AlreadyAbsent);
                    // On the first attempt an absent lease was lost, not settled by a retry:
                    // the customer has its answer but nothing was charged or recorded.
                    if attempt == 1 {
                        self.metrics.record_unsettled_generation();
                        crate::diagnostics::limited_error!(
                            %generation_id,
                            %organization_id,
                            charge_nano_usd = properties.charge(),
                            "generation lost its admission lease before settlement; \
                             the charge was not applied and no terminal event was appended"
                        );
                    }
                    return Ok(());
                }
                Err(error) => {
                    self.metrics
                        .record_finalization_attempt(FinalizationAttempt::Error);
                    if attempt == FINALIZATION_ATTEMPTS {
                        self.metrics.record_finalization_failure();
                        crate::diagnostics::limited_error!(%generation_id, %organization_id,
                            phase = "finalization", attempts = FINALIZATION_ATTEMPTS,
                            error_code = error.diagnostic_code(),
                            "generation settlement retries exhausted");
                        return Err(error.into());
                    }
                }
            }

            self.metrics.record_finalization_retry();
            tokio::time::sleep(FINALIZATION_RETRY_DELAY).await;
            attempt += 1;
        }
    }
}
