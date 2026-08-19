use chrono::{DateTime, TimeDelta, Utc};
use thiserror::Error;
use uuid::Uuid;

use crate::{GatewayConfig, GatewayError};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdmissionAttempt {
    pub generation_id: Uuid,
    pub organization_id: Uuid,
    pub admitted_at: DateTime<Utc>,
    pub request_deadline: DateTime<Utc>,
    pub lease_expires_at: DateTime<Utc>,
    cleanup_cutoff: DateTime<Utc>,
    prepaid_organization_concurrency_cap: u64,
    balance_per_concurrency_slot_nano_usd: u64,
    settlement_backlog_limit: u64,
}

impl AdmissionAttempt {
    pub fn new(
        generation_id: Uuid,
        organization_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
    ) -> Result<Self, AdmissionError> {
        if admitted_at < received_at {
            return Err(AdmissionError::InvalidTiming(
                "admitted_at cannot precede received_at",
            ));
        }
        let request_deadline = checked_add_seconds(
            received_at,
            config.generation_timeout_seconds,
            "generation timeout is outside the supported timestamp range",
        )?;
        if admitted_at >= request_deadline {
            return Err(AdmissionError::DeadlineElapsed);
        }
        let lease_expires_at = checked_add_seconds(
            request_deadline,
            config.lease_finalization_margin_seconds,
            "lease expiry is outside the supported timestamp range",
        )?;
        let cleanup_cutoff = checked_sub_seconds(
            admitted_at,
            config.expired_lease_cleanup_grace_seconds,
            "cleanup cutoff is outside the supported timestamp range",
        )?;
        for (name, timestamp) in [
            ("admitted_at", admitted_at),
            ("request_deadline", request_deadline),
            ("lease_expires_at", lease_expires_at),
            ("cleanup_cutoff", cleanup_cutoff),
        ] {
            if timestamp.timestamp_millis() <= 0 {
                return Err(AdmissionError::InvalidTiming(match name {
                    "admitted_at" => "admitted_at must be after the Unix epoch",
                    "request_deadline" => "request_deadline must be after the Unix epoch",
                    "lease_expires_at" => "lease_expires_at must be after the Unix epoch",
                    _ => "cleanup_cutoff must be after the Unix epoch",
                }));
            }
        }

        Ok(Self {
            generation_id,
            organization_id,
            admitted_at,
            request_deadline,
            lease_expires_at,
            cleanup_cutoff,
            prepaid_organization_concurrency_cap: config.prepaid_organization_concurrency_cap,
            balance_per_concurrency_slot_nano_usd: config.balance_per_concurrency_slot_nano_usd,
            settlement_backlog_limit: config.settlement_backlog_limit,
        })
    }

    pub(crate) fn script_arguments(&self) -> [String; 8] {
        [
            self.generation_id.to_string(),
            self.organization_id.to_string(),
            self.admitted_at.timestamp_millis().to_string(),
            self.lease_expires_at.timestamp_millis().to_string(),
            self.cleanup_cutoff.timestamp_millis().to_string(),
            self.prepaid_organization_concurrency_cap.to_string(),
            self.balance_per_concurrency_slot_nano_usd.to_string(),
            self.settlement_backlog_limit.to_string(),
        ]
    }

    pub(crate) fn lease(&self) -> AdmissionLease {
        AdmissionLease {
            generation_id: self.generation_id,
            admitted_at: self.admitted_at,
            request_deadline: self.request_deadline,
            lease_expires_at: self.lease_expires_at,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdmissionLease {
    pub generation_id: Uuid,
    pub admitted_at: DateTime<Utc>,
    pub request_deadline: DateTime<Utc>,
    pub lease_expires_at: DateTime<Utc>,
}

fn checked_add_seconds(
    timestamp: DateTime<Utc>,
    seconds: u64,
    message: &'static str,
) -> Result<DateTime<Utc>, AdmissionError> {
    let seconds = i64::try_from(seconds).map_err(|_| AdmissionError::InvalidTiming(message))?;
    let duration = TimeDelta::try_seconds(seconds).ok_or(AdmissionError::InvalidTiming(message))?;
    timestamp
        .checked_add_signed(duration)
        .ok_or(AdmissionError::InvalidTiming(message))
}

fn checked_sub_seconds(
    timestamp: DateTime<Utc>,
    seconds: u64,
    message: &'static str,
) -> Result<DateTime<Utc>, AdmissionError> {
    let seconds = i64::try_from(seconds).map_err(|_| AdmissionError::InvalidTiming(message))?;
    let duration = TimeDelta::try_seconds(seconds).ok_or(AdmissionError::InvalidTiming(message))?;
    timestamp
        .checked_sub_signed(duration)
        .ok_or(AdmissionError::InvalidTiming(message))
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

impl From<AdmissionError> for GatewayError {
    fn from(error: AdmissionError) -> Self {
        match error {
            AdmissionError::InsufficientBalance => Self::InsufficientBalance,
            AdmissionError::ConcurrencyExceeded => Self::ConcurrencyExceeded,
            AdmissionError::SettlementBacklog => Self::SettlementBacklog,
            AdmissionError::InvalidTiming(_)
            | AdmissionError::DeadlineElapsed
            | AdmissionError::DuplicateGeneration
            | AdmissionError::UnknownScriptResult(_)
            | AdmissionError::Redis(_) => Self::ServingStateUnavailable,
        }
    }
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;

    use super::*;

    fn config() -> GatewayConfig {
        GatewayConfig {
            bind_address: "127.0.0.1:3002".parse().unwrap(),
            generation_timeout_seconds: 300,
            lease_finalization_margin_seconds: 60,
            expired_lease_cleanup_grace_seconds: 300,
            prepaid_organization_concurrency_cap: 50,
            balance_per_concurrency_slot_nano_usd: 1_000_000_000,
            settlement_backlog_limit: 100_000,
            valkey_url: "redis://127.0.0.1:6379".to_owned(),
            sglang_api_key: None,
        }
    }

    #[test]
    fn derives_a_fixed_deadline_lease_and_cleanup_cutoff() {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        let admitted_at = received_at + TimeDelta::seconds(1);
        let attempt = AdmissionAttempt::new(
            Uuid::nil(),
            Uuid::nil(),
            received_at,
            admitted_at,
            &config(),
        )
        .unwrap();

        assert_eq!(
            attempt.request_deadline,
            received_at + TimeDelta::seconds(300)
        );
        assert_eq!(
            attempt.lease_expires_at,
            received_at + TimeDelta::seconds(360)
        );
        assert_eq!(
            attempt.cleanup_cutoff,
            admitted_at - TimeDelta::seconds(300)
        );
    }

    #[test]
    fn rejects_elapsed_or_inconsistent_timing() {
        let received_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        assert!(matches!(
            AdmissionAttempt::new(
                Uuid::nil(),
                Uuid::nil(),
                received_at,
                received_at - TimeDelta::seconds(1),
                &config(),
            ),
            Err(AdmissionError::InvalidTiming(_))
        ));
        assert!(matches!(
            AdmissionAttempt::new(
                Uuid::nil(),
                Uuid::nil(),
                received_at,
                received_at + TimeDelta::seconds(300),
                &config(),
            ),
            Err(AdmissionError::DeadlineElapsed)
        ));
    }
}
