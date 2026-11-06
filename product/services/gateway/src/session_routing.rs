use std::{collections::HashMap, fmt::Write, time::Duration};

use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::routing::RoutePlacement;

/// Longer than the pause between an agent's turns, so a working session keeps its replica.
pub(crate) const SESSION_LIFETIME: Duration = Duration::from_secs(30 * 60);

pub struct PlacementRequest<'a> {
    pub placement: &'a RoutePlacement,
    pub candidates: &'a [Uuid],
    pub generation_id: Uuid,
    pub now: DateTime<Utc>,
    pub lease_expires_at: DateTime<Utc>,
}

impl PlacementRequest<'_> {
    pub(crate) fn session_key(&self) -> String {
        session_key(&self.placement.release_digest, &self.placement.route_key)
    }

    pub(crate) fn lease_keys(&self) -> Vec<String> {
        self.candidates
            .iter()
            .map(|deployment_id| lease_key(&self.placement.release_digest, *deployment_id))
            .collect()
    }

    pub(crate) fn limit(&self, deployment_id: Uuid) -> u32 {
        limit(&self.placement.limits, deployment_id)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlacementOutcome {
    Kept,
    Placed,
    Moved,
    Spilled,
}

impl PlacementOutcome {
    pub(crate) fn from_script(code: i64) -> Option<Self> {
        match code {
            1 => Some(Self::Kept),
            2 => Some(Self::Placed),
            3 => Some(Self::Moved),
            4 => Some(Self::Spilled),
            _ => None,
        }
    }

    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Kept => "kept",
            Self::Placed => "placed",
            Self::Moved => "moved",
            Self::Spilled => "spilled",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Placed {
    pub deployment_id: Uuid,
    pub outcome: PlacementOutcome,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RouteLease {
    pub release_digest: String,
    pub route_key: [u8; 32],
    pub deployment_id: Uuid,
    pub generation_id: Uuid,
    pub expires_at: DateTime<Utc>,
}

impl RouteLease {
    pub(crate) fn session_key(&self) -> String {
        session_key(&self.release_digest, &self.route_key)
    }

    pub(crate) fn lease_key(&self) -> String {
        lease_key(&self.release_digest, self.deployment_id)
    }
}

/// Session and lease keys share the release's hash tag, like its deployment
/// statuses, so one script can read and write all of them.
fn session_key(release_digest: &str, route_key: &[u8; 32]) -> String {
    let mut key = format!("route-session:{{{release_digest}}}:");
    for byte in route_key {
        let _ = write!(key, "{byte:02x}");
    }

    key
}

fn lease_key(release_digest: &str, deployment_id: Uuid) -> String {
    format!("route-leases:{{{release_digest}}}:{deployment_id}")
}

/// 0 tells the placement script that the replica reports no limit.
fn limit(limits: &HashMap<Uuid, Option<u32>>, deployment_id: Uuid) -> u32 {
    limits.get(&deployment_id).copied().flatten().unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keys_share_the_release_hash_tag() {
        let lease = RouteLease {
            release_digest: "abc".to_owned(),
            route_key: [0xab; 32],
            deployment_id: Uuid::from_u128(1),
            generation_id: Uuid::from_u128(2),
            expires_at: DateTime::UNIX_EPOCH,
        };

        assert_eq!(
            lease.session_key(),
            format!("route-session:{{abc}}:{}", "ab".repeat(32))
        );
        assert_eq!(
            lease.lease_key(),
            "route-leases:{abc}:00000000-0000-0000-0000-000000000001"
        );
    }

    #[test]
    fn unreported_limits_are_zero() {
        let limits = HashMap::from([(Uuid::from_u128(1), Some(12)), (Uuid::from_u128(2), None)]);

        assert_eq!(limit(&limits, Uuid::from_u128(1)), 12);
        assert_eq!(limit(&limits, Uuid::from_u128(2)), 0);
        assert_eq!(limit(&limits, Uuid::from_u128(3)), 0);
    }
}
