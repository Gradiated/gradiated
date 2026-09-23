use chrono::{DateTime, TimeDelta, Utc};
use thiserror::Error;
use uuid::Uuid;

use crate::{GatewayConfig, GatewayError};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdmissionLease {
    generation_id: Uuid,
    request_deadline: DateTime<Utc>,
    lease_expires_at: DateTime<Utc>,
}

impl AdmissionLease {
    pub(crate) fn new(
        generation_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
    ) -> Result<Self, AdmissionError> {
        if admitted_at < received_at {
            return Err(AdmissionError::InvalidTiming(
                "admitted_at cannot precede received_at",
            ));
        }

        after_epoch(admitted_at, "admitted_at must be after the Unix epoch")?;

        let message = "generation timeout is outside the supported timestamp range";
        let request_deadline = received_at
            .checked_add_signed(seconds(config.generation_timeout_seconds, message)?)
            .ok_or(AdmissionError::InvalidTiming(message))?;
        if admitted_at >= request_deadline {
            return Err(AdmissionError::DeadlineElapsed);
        }

        let message = "lease expiry is outside the supported timestamp range";
        let lease_expires_at = request_deadline
            .checked_add_signed(seconds(config.lease_finalization_margin_seconds, message)?)
            .ok_or(AdmissionError::InvalidTiming(message))?;

        Ok(Self {
            generation_id,
            request_deadline,
            lease_expires_at,
        })
    }

    pub fn generation_id(&self) -> Uuid {
        self.generation_id
    }

    pub fn request_deadline(&self) -> DateTime<Utc> {
        self.request_deadline
    }

    pub fn lease_expires_at(&self) -> DateTime<Utc> {
        self.lease_expires_at
    }
}

pub(crate) fn cleanup_cutoff(
    admitted_at: DateTime<Utc>,
    config: &GatewayConfig,
) -> Result<DateTime<Utc>, AdmissionError> {
    let message = "cleanup cutoff is outside the supported timestamp range";
    let cutoff = admitted_at
        .checked_sub_signed(seconds(
            config.expired_lease_cleanup_grace_seconds,
            message,
        )?)
        .ok_or(AdmissionError::InvalidTiming(message))?;

    after_epoch(cutoff, "cleanup_cutoff must be after the Unix epoch")
}

fn seconds(seconds: u64, message: &'static str) -> Result<TimeDelta, AdmissionError> {
    i64::try_from(seconds)
        .ok()
        .and_then(TimeDelta::try_seconds)
        .ok_or(AdmissionError::InvalidTiming(message))
}

fn after_epoch(
    timestamp: DateTime<Utc>,
    message: &'static str,
) -> Result<DateTime<Utc>, AdmissionError> {
    if timestamp.timestamp_millis() <= 0 {
        return Err(AdmissionError::InvalidTiming(message));
    }

    Ok(timestamp)
}

#[derive(Debug, Error)]
pub enum AdmissionError {
    #[error("admission timing is invalid: {0}")]
    InvalidTiming(&'static str),
    #[error("the request deadline elapsed before admission")]
    DeadlineElapsed,
    #[error("the prepaid balance is not positive")]
    InsufficientBalance,
    #[error("the prepaid organization concurrency limit was reached")]
    ConcurrencyExceeded,
    #[error("the settlement backlog limit was reached")]
    SettlementBacklog,
    #[error("the generation ID already has an in-flight lease")]
    DuplicateGeneration,
    #[error("the admission script returned an unknown result: {0}")]
    UnknownScriptResult(i64),
    #[error("Valkey admission failed: {0}")]
    Redis(#[from] redis::RedisError),
}

impl AdmissionError {
    pub(crate) fn diagnostic_code(&self) -> &'static str {
        match self {
            Self::InvalidTiming(_) => "invalid_timing",
            Self::DeadlineElapsed => "deadline_elapsed",
            Self::InsufficientBalance => "insufficient_balance",
            Self::ConcurrencyExceeded => "concurrency_exceeded",
            Self::SettlementBacklog => "settlement_backlog",
            Self::DuplicateGeneration => "duplicate_generation",
            Self::UnknownScriptResult(_) => "unknown_script_result",
            Self::Redis(_) => "valkey_error",
        }
    }

    pub(crate) fn redis_code(&self) -> Option<&str> {
        match self {
            Self::Redis(error) => error.code(),
            _ => None,
        }
    }

    /// Every error that is not a policy rejection reaches the client as a bare
    /// 503, so its cause must be logged.
    pub(crate) fn is_serving_state_failure(&self) -> bool {
        self.policy_rejection().is_none()
    }

    fn policy_rejection(&self) -> Option<GatewayError> {
        match self {
            Self::InsufficientBalance => Some(GatewayError::InsufficientBalance),
            Self::ConcurrencyExceeded => Some(GatewayError::ConcurrencyExceeded),
            Self::SettlementBacklog => Some(GatewayError::SettlementBacklog),
            Self::InvalidTiming(_)
            | Self::DeadlineElapsed
            | Self::DuplicateGeneration
            | Self::UnknownScriptResult(_)
            | Self::Redis(_) => None,
        }
    }
}

impl From<AdmissionError> for GatewayError {
    fn from(error: AdmissionError) -> Self {
        error
            .policy_rejection()
            .unwrap_or(Self::ServingStateUnavailable)
    }
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;

    use super::*;

    fn config() -> GatewayConfig {
        GatewayConfig::for_tests()
    }

    #[test]
    fn derives_a_fixed_deadline_lease_and_cleanup_cutoff() {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        let admitted_at = received_at + TimeDelta::seconds(1);
        let config = config();
        let lease = AdmissionLease::new(Uuid::nil(), received_at, admitted_at, &config).unwrap();

        assert_eq!(
            lease.request_deadline(),
            received_at + TimeDelta::seconds(300)
        );
        assert_eq!(
            lease.lease_expires_at(),
            received_at + TimeDelta::seconds(360)
        );
        assert_eq!(
            cleanup_cutoff(admitted_at, &config).unwrap(),
            admitted_at - TimeDelta::seconds(300)
        );
    }

    #[test]
    fn every_admission_error_has_a_diagnostic_code_and_a_matching_response() {
        let redis = redis::RedisError::from((redis::ErrorKind::Io, "connection refused"));
        let cases = [
            (AdmissionError::InvalidTiming("x"), "invalid_timing", true),
            (AdmissionError::DeadlineElapsed, "deadline_elapsed", true),
            (
                AdmissionError::InsufficientBalance,
                "insufficient_balance",
                false,
            ),
            (
                AdmissionError::ConcurrencyExceeded,
                "concurrency_exceeded",
                false,
            ),
            (
                AdmissionError::SettlementBacklog,
                "settlement_backlog",
                false,
            ),
            (
                AdmissionError::DuplicateGeneration,
                "duplicate_generation",
                true,
            ),
            (
                AdmissionError::UnknownScriptResult(9),
                "unknown_script_result",
                true,
            ),
            (AdmissionError::Redis(redis), "valkey_error", true),
        ];

        for (error, code, is_failure) in cases {
            assert_eq!(error.diagnostic_code(), code);
            assert_eq!(error.is_serving_state_failure(), is_failure, "{code}");
            assert_eq!(
                matches!(
                    GatewayError::from(error),
                    GatewayError::ServingStateUnavailable
                ),
                is_failure,
                "{code}"
            );
        }
    }

    #[test]
    fn rejects_admission_before_receipt() {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();

        let result = AdmissionLease::new(
            Uuid::nil(),
            received_at,
            received_at - TimeDelta::seconds(1),
            &config(),
        );

        assert!(matches!(result, Err(AdmissionError::InvalidTiming(_))));
    }

    #[test]
    fn rejects_admission_at_the_deadline_and_admits_just_before_it() {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        let deadline = received_at + TimeDelta::seconds(300);

        let at_deadline = AdmissionLease::new(Uuid::nil(), received_at, deadline, &config());
        let just_before = AdmissionLease::new(
            Uuid::nil(),
            received_at,
            deadline - TimeDelta::milliseconds(1),
            &config(),
        );

        assert!(matches!(at_deadline, Err(AdmissionError::DeadlineElapsed)));
        assert_eq!(just_before.unwrap().request_deadline(), deadline);
    }

    #[test]
    fn rejects_a_timeout_outside_the_timestamp_range() {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        let mut config = config();
        config.generation_timeout_seconds = u64::MAX;

        let result = AdmissionLease::new(Uuid::nil(), received_at, received_at, &config);

        assert!(matches!(result, Err(AdmissionError::InvalidTiming(_))));
    }

    #[test]
    fn rejects_admission_at_the_unix_epoch() {
        let epoch = DateTime::UNIX_EPOCH;

        let result = AdmissionLease::new(Uuid::nil(), epoch, epoch, &config());

        assert!(matches!(result, Err(AdmissionError::InvalidTiming(_))));
    }

    #[test]
    fn rejects_a_cleanup_cutoff_before_the_unix_epoch() {
        let admitted_at = DateTime::UNIX_EPOCH + TimeDelta::seconds(10);
        let mut config = config();
        config.expired_lease_cleanup_grace_seconds = 20;

        let result = cleanup_cutoff(admitted_at, &config);

        assert!(matches!(result, Err(AdmissionError::InvalidTiming(_))));
    }
}
