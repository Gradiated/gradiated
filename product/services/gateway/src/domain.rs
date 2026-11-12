//! Records are read from a cache that another, possibly older or newer, gateway
//! wrote. Rejecting a field this binary does not know turns one additive schema
//! change into every request failing for a full record lifetime, fleet-wide, and
//! makes a rollback do the same. Unknown fields are ignored; the domain invariants
//! are still enforced after parsing.

use std::collections::HashMap;

use chrono::{DateTime, Utc};
use serde::{de, de::value::MapDeserializer, Deserialize, Deserializer};
use thiserror::Error;
use uuid::Uuid;

pub use crate::model::GatewayModel;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct GatewayCredential {
    pub api_key_id: Uuid,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub expires_at: Option<DateTime<Utc>>,
    pub revoked_at: Option<DateTime<Utc>>,
    /// Whether the key belongs to OpenRouter's own distribution-channel
    /// organization. Absent in a record cached before the field existed.
    #[serde(default)]
    pub openrouter_channel: Option<bool>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct GatewayWorkspace {
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub archived_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum OrganizationKind {
    Customer,
    DistributionChannel,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum OrganizationStatus {
    Active,
    Suspended,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum BillingMode {
    Prepaid,
    Invoiced,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct GatewayAccount {
    pub organization_id: Uuid,
    pub organization_kind: OrganizationKind,
    pub organization_status: OrganizationStatus,
    pub billing_mode: BillingMode,
    #[serde(deserialize_with = "deserialize_i64_from_string")]
    pub balance: i64,
}

impl GatewayAccount {
    pub fn funds_hosted_requests(&self) -> bool {
        self.billing_mode == BillingMode::Invoiced || self.balance > 0
    }

    pub fn from_hash(fields: HashMap<String, String>) -> Result<Self, RecordError> {
        let values = MapDeserializer::<_, de::value::Error>::new(fields.into_iter());
        Self::deserialize(values).map_err(RecordError::from)
    }
}

fn deserialize_i64_from_string<'de, D>(deserializer: D) -> Result<i64, D::Error>
where
    D: Deserializer<'de>,
{
    String::deserialize(deserializer)?
        .parse()
        .map_err(de::Error::custom)
}

#[derive(Debug, Error)]
#[error("record does not match its schema: {0}")]
pub struct RecordError(#[from] de::value::Error);

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_account() -> HashMap<String, String> {
        HashMap::from([
            (
                "organization_id".to_owned(),
                "0198c36f-9b6a-7000-8000-000000000001".to_owned(),
            ),
            ("organization_kind".to_owned(), "customer".to_owned()),
            ("organization_status".to_owned(), "active".to_owned()),
            ("billing_mode".to_owned(), "prepaid".to_owned()),
            ("balance".to_owned(), "1000000000".to_owned()),
        ])
    }

    #[test]
    fn account_hash_parses_integer_money() {
        let account = GatewayAccount::from_hash(valid_account()).expect("account should parse");
        assert_eq!(account.balance, 1_000_000_000);
        assert_eq!(account.billing_mode, BillingMode::Prepaid);
    }

    #[test]
    /// The hash carries the gateway's own bookkeeping beside the account, and a
    /// newer gateway may add more of it. Those fields are not the account's, and
    /// rejecting them would fail every request for the organization.
    fn the_account_ignores_fields_that_are_not_its_own() {
        let mut fields = valid_account();
        fields.insert("balance_seeded_at".to_owned(), "1790000000000".to_owned());
        fields.insert(
            "balance_seeded_id".to_owned(),
            "ffffffff-ffff-ffff-ffff-ffffffffffff".to_owned(),
        );
        fields.insert("a_field_from_a_later_gateway".to_owned(), "1".to_owned());

        let account = GatewayAccount::from_hash(fields).expect("the account parses");
        assert_eq!(account.balance, 1_000_000_000);
    }

    #[test]
    fn only_a_positive_prepaid_balance_or_invoicing_funds_hosted_requests() {
        let account = GatewayAccount::from_hash(valid_account()).expect("account should parse");

        for (billing_mode, balance, funded) in [
            (BillingMode::Prepaid, 1, true),
            (BillingMode::Prepaid, 0, false),
            (BillingMode::Prepaid, -1, false),
            (BillingMode::Invoiced, -1, true),
        ] {
            let account = GatewayAccount {
                billing_mode,
                balance,
                ..account.clone()
            };

            assert_eq!(
                account.funds_hosted_requests(),
                funded,
                "{billing_mode:?} {balance}"
            );
        }
    }

    #[test]
    fn account_hash_rejects_missing_or_malformed_fields() {
        let mut missing = valid_account();
        missing.remove("billing_mode");
        assert!(GatewayAccount::from_hash(missing).is_err());

        let mut malformed = valid_account();
        malformed.insert("balance".to_owned(), "one dollar".to_owned());
        assert!(GatewayAccount::from_hash(malformed).is_err());
    }
}
