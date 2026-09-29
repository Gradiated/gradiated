use std::{collections::HashMap, io};

use chrono::{DateTime, TimeDelta, Utc};
use sha2::{Digest, Sha256};
use uuid::Uuid;
use validator::Validate;

use crate::{DeploymentRuntimeStatus, DeploymentStatus, GatewayModelDeployment};

const MAXIMUM_STATUS_AGE: TimeDelta = TimeDelta::seconds(15);
const PREFIX_TOKEN_LIMIT: usize = 4_096;
const PREFIX_BYTE_LIMIT: usize = 16_384;

#[derive(Clone, Copy)]
pub enum RoutePrompt<'a> {
    TokenIds(&'a [u32]),
    ChatMessages(&'a [serde_json::Value]),
    DecisionState(&'a serde_json::Value),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Route {
    pub primary: GatewayModelDeployment,
    pub fallbacks: Vec<GatewayModelDeployment>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
#[expect(
    clippy::large_enum_variant,
    reason = "built once per request and destructured immediately"
)]
pub enum RouteAvailability {
    Ready(Route),
    AtCapacity(RouteDiagnostics),
    Unavailable(RouteDiagnostics),
}

pub struct RouteInput<'a> {
    pub workspace_id: Uuid,
    pub model_id: &'a str,
    pub release_digest: &'a str,
    pub session_id: Option<&'a str>,
    pub prompt: RoutePrompt<'a>,
    pub deployments: &'a [GatewayModelDeployment],
    pub statuses: &'a [DeploymentRuntimeStatus],
    pub now: DateTime<Utc>,
}

pub fn healthy_deployment_count(
    deployments: &[GatewayModelDeployment],
    statuses: &[DeploymentRuntimeStatus],
    now: DateTime<Utc>,
) -> u64 {
    let statuses = statuses_by_deployment(statuses);

    deployments
        .iter()
        .filter(|deployment| {
            deployment_rejection(deployment).is_none()
                && statuses
                    .get(&deployment.id)
                    .is_some_and(|status| status_rejection(deployment, status, now).is_none())
        })
        .count() as u64
}

/// Counts only the first rejection reason for each candidate; never contains endpoints.
#[derive(Clone, Default, Debug, Eq, PartialEq)]
pub struct RouteDiagnostics {
    pub candidates: usize,
    pub unavailable: usize,
    pub invalid_deployment: usize,
    pub release_mismatch: usize,
    pub missing_status: usize,
    pub invalid_status: usize,
    pub revision_mismatch: usize,
    pub stale_status: usize,
    pub unhealthy: usize,
    pub at_capacity: usize,
}

impl RouteDiagnostics {
    pub(crate) fn warn(&self, generation_id: Uuid, model_id: &str) {
        crate::diagnostics::limited_warn!(%generation_id, model_id, phase = "routing",
            candidates = self.candidates,
            unavailable = self.unavailable,
            invalid_deployment = self.invalid_deployment,
            release_mismatch = self.release_mismatch,
            missing_status = self.missing_status,
            invalid_status = self.invalid_status,
            revision_mismatch = self.revision_mismatch,
            stale_status = self.stale_status,
            unhealthy = self.unhealthy,
            at_capacity = self.at_capacity,
            "no eligible runtime deployment");
    }

    fn count(&mut self, rejection: Rejection) {
        let counter = match rejection {
            Rejection::Unavailable => &mut self.unavailable,
            Rejection::InvalidDeployment => &mut self.invalid_deployment,
            Rejection::ReleaseMismatch => &mut self.release_mismatch,
            Rejection::MissingStatus => &mut self.missing_status,
            Rejection::InvalidStatus => &mut self.invalid_status,
            Rejection::RevisionMismatch => &mut self.revision_mismatch,
            Rejection::StaleStatus => &mut self.stale_status,
            Rejection::Unhealthy => &mut self.unhealthy,
        };
        *counter += 1;
    }
}

enum Rejection {
    Unavailable,
    InvalidDeployment,
    ReleaseMismatch,
    MissingStatus,
    InvalidStatus,
    RevisionMismatch,
    StaleStatus,
    Unhealthy,
}

fn statuses_by_deployment(
    statuses: &[DeploymentRuntimeStatus],
) -> HashMap<Uuid, &DeploymentRuntimeStatus> {
    statuses
        .iter()
        .map(|status| (status.deployment_id, status))
        .collect()
}

fn deployment_rejection(deployment: &GatewayModelDeployment) -> Option<Rejection> {
    if deployment.status != DeploymentStatus::Available {
        return Some(Rejection::Unavailable);
    }

    deployment
        .validate()
        .is_err()
        .then_some(Rejection::InvalidDeployment)
}

fn status_rejection(
    deployment: &GatewayModelDeployment,
    status: &DeploymentRuntimeStatus,
    now: DateTime<Utc>,
) -> Option<Rejection> {
    if status.validate().is_err() {
        Some(Rejection::InvalidStatus)
    } else if status.runtime_revision != deployment.release.runtime_revision {
        Some(Rejection::RevisionMismatch)
    } else if !status.is_fresh_at(now, MAXIMUM_STATUS_AGE) {
        Some(Rejection::StaleStatus)
    } else if !status.healthy {
        Some(Rejection::Unhealthy)
    } else {
        None
    }
}

fn healthy_status<'a>(
    deployment: &GatewayModelDeployment,
    statuses: &HashMap<Uuid, &'a DeploymentRuntimeStatus>,
    release_digest: &str,
    now: DateTime<Utc>,
) -> Result<&'a DeploymentRuntimeStatus, Rejection> {
    if let Some(rejection) = deployment_rejection(deployment) {
        return Err(rejection);
    }

    if deployment.served_release_digest().ok().as_deref() != Some(release_digest) {
        return Err(Rejection::ReleaseMismatch);
    }

    let status = *statuses
        .get(&deployment.id)
        .ok_or(Rejection::MissingStatus)?;

    match status_rejection(deployment, status, now) {
        Some(rejection) => Err(rejection),
        None => Ok(status),
    }
}

pub fn order_deployments(input: RouteInput<'_>) -> RouteAvailability {
    let RouteInput {
        workspace_id,
        model_id,
        release_digest,
        session_id,
        prompt,
        deployments,
        statuses,
        now,
    } = input;
    let statuses = statuses_by_deployment(statuses);
    let mut diagnostics = RouteDiagnostics {
        candidates: deployments.len(),
        ..Default::default()
    };

    let mut healthy = Vec::new();
    for deployment in deployments {
        match healthy_status(deployment, &statuses, release_digest, now) {
            Ok(status) => healthy.push((deployment, status.accepting_requests)),
            Err(rejection) => diagnostics.count(rejection),
        }
    }

    if healthy.is_empty() {
        return RouteAvailability::Unavailable(diagnostics);
    }

    let mut accepting: Vec<GatewayModelDeployment> = healthy
        .iter()
        .filter(|(_, accepting)| *accepting)
        .map(|(deployment, _)| (*deployment).clone())
        .collect();
    diagnostics.at_capacity = healthy.len() - accepting.len();

    let route_key = route_key(workspace_id, model_id, release_digest, session_id, prompt);
    accepting.sort_by_cached_key(|candidate| {
        std::cmp::Reverse(rendezvous_score(&route_key, candidate.id))
    });

    let mut ordered = accepting.into_iter();
    let Some(primary) = ordered.next() else {
        return RouteAvailability::AtCapacity(diagnostics);
    };

    RouteAvailability::Ready(Route {
        primary,
        fallbacks: ordered.collect(),
    })
}

fn route_key(
    workspace_id: Uuid,
    model_id: &str,
    release_digest: &str,
    session_id: Option<&str>,
    prompt: RoutePrompt<'_>,
) -> [u8; 32] {
    let mut hash = Sha256::new();
    hash.update(workspace_id.as_bytes());
    hash.update((model_id.len() as u64).to_be_bytes());
    hash.update(model_id.as_bytes());
    hash.update((release_digest.len() as u64).to_be_bytes());
    hash.update(release_digest.as_bytes());

    match (session_id, prompt) {
        (Some(session_id), _) => {
            hash.update([1]);
            hash.update((session_id.len() as u64).to_be_bytes());
            hash.update(session_id.as_bytes());
        }
        (None, RoutePrompt::TokenIds(input_ids)) => {
            hash.update([0]);
            for token in input_ids.iter().take(PREFIX_TOKEN_LIMIT) {
                hash.update(token.to_be_bytes());
            }
        }
        (None, RoutePrompt::ChatMessages(messages)) => {
            hash.update([2]);
            hash_json_prefix(&mut hash, messages);
        }
        (None, RoutePrompt::DecisionState(state)) => {
            hash.update([3]);
            hash_json_prefix(&mut hash, state);
        }
    }

    hash.finalize().into()
}

fn hash_json_prefix(hash: &mut Sha256, value: &(impl serde::Serialize + ?Sized)) {
    let mut prefix = PrefixHasher {
        hash,
        remaining: PREFIX_BYTE_LIMIT,
    };

    // A JSON value fails to serialize only when the writer stops accepting bytes.
    let _ = serde_json::to_writer(&mut prefix, value);
}

struct PrefixHasher<'a> {
    hash: &'a mut Sha256,
    remaining: usize,
}

impl io::Write for PrefixHasher<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let taken = bytes.len().min(self.remaining);
        self.hash.update(&bytes[..taken]);
        self.remaining -= taken;

        Ok(taken)
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn rendezvous_score(route_key: &[u8; 32], deployment_id: Uuid) -> [u8; 32] {
    let mut hash = Sha256::new();
    hash.update(route_key);
    hash.update(deployment_id.as_bytes());
    hash.finalize().into()
}

#[cfg(test)]
pub(crate) mod fixtures {
    use chrono::{DateTime, Utc};
    use uuid::Uuid;

    use crate::{test_support, DeploymentRuntimeStatus, GatewayModelDeployment};

    pub(crate) fn deployment(id: u128) -> GatewayModelDeployment {
        GatewayModelDeployment {
            id: Uuid::from_u128(id),
            fault_domain: format!("local:runtime-{id}"),
            ..test_support::model(true).deployments.remove(0)
        }
    }

    pub(crate) fn healthy_status(
        deployment: &GatewayModelDeployment,
        received_at: DateTime<Utc>,
    ) -> DeploymentRuntimeStatus {
        DeploymentRuntimeStatus {
            schema_version: 1,
            deployment_id: deployment.id,
            runtime_revision: deployment.release.runtime_revision.clone(),
            received_at,
            healthy: true,
            accepting_requests: true,
            reason_code: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;

    use super::{fixtures::deployment, *};

    fn now() -> DateTime<Utc> {
        Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap()
    }

    fn deployments(count: u128) -> Vec<GatewayModelDeployment> {
        (1..=count).map(deployment).collect()
    }

    fn status(deployment: &GatewayModelDeployment) -> DeploymentRuntimeStatus {
        fixtures::healthy_status(deployment, now())
    }

    fn statuses(deployments: &[GatewayModelDeployment]) -> Vec<DeploymentRuntimeStatus> {
        deployments.iter().map(status).collect()
    }

    fn route(
        deployments: &[GatewayModelDeployment],
        statuses: &[DeploymentRuntimeStatus],
        prompt: RoutePrompt<'_>,
        session_id: Option<&str>,
    ) -> RouteAvailability {
        let release_digest = deployment(0).served_release_digest().unwrap();

        order_deployments(RouteInput {
            workspace_id: Uuid::from_u128(9),
            model_id: "model",
            release_digest: &release_digest,
            session_id,
            prompt,
            deployments,
            statuses,
            now: now(),
        })
    }

    fn ready(availability: RouteAvailability) -> Vec<Uuid> {
        match availability {
            RouteAvailability::Ready(route) => std::iter::once(route.primary)
                .chain(route.fallbacks)
                .map(|candidate| candidate.id)
                .collect(),
            unavailable => panic!("expected ready deployments, got {unavailable:?}"),
        }
    }

    fn order(deployments: &[GatewayModelDeployment], session_id: &str) -> Vec<Uuid> {
        ready(route(
            deployments,
            &statuses(deployments),
            RoutePrompt::TokenIds(&[1]),
            Some(session_id),
        ))
    }

    #[test]
    fn chat_routing_uses_request_prefix_and_preserves_session_affinity() {
        let first = vec![serde_json::json!({"role":"user","content":"hello"})];
        let second = vec![serde_json::json!({"role":"user","content":"different"})];
        let key = |messages: &[serde_json::Value], session| {
            route_key(
                Uuid::from_u128(9),
                "model",
                "release",
                session,
                RoutePrompt::ChatMessages(messages),
            )
        };
        assert_eq!(key(&first, None), key(&first, None));
        assert_ne!(key(&first, None), key(&second, None));
        assert_eq!(key(&first, Some("session")), key(&second, Some("session")));
        let long = vec![serde_json::json!({"role":"user","content":"x".repeat(PREFIX_BYTE_LIMIT)})];
        let mut extended = long.clone();
        extended.push(serde_json::json!({"role":"assistant","content":"reply"}));
        assert_eq!(key(&long, None), key(&extended, None));
    }

    #[test]
    fn token_routing_hashes_only_the_prefix_limit() {
        let key = |ids: &[u32]| {
            route_key(
                Uuid::from_u128(9),
                "model",
                "release",
                None,
                RoutePrompt::TokenIds(ids),
            )
        };
        let prefix = vec![7; PREFIX_TOKEN_LIMIT];
        let mut first = prefix.clone();
        first.push(1);
        let mut second = prefix.clone();
        second.push(2);
        let mut changed = prefix;
        changed[PREFIX_TOKEN_LIMIT - 1] = 8;

        assert_eq!(key(&first), key(&second));
        assert_ne!(key(&first), key(&changed));
    }

    #[test]
    fn decision_state_route_keys_preserve_affinity_and_isolate_domains() {
        let state = serde_json::json!([{"ticket":"billing"}]);
        let changed = serde_json::json!([{"ticket":"support"}]);
        let workspace = Uuid::from_u128(9);
        let key = |state: &serde_json::Value, session| {
            route_key(
                workspace,
                "model",
                "release",
                session,
                RoutePrompt::DecisionState(state),
            )
        };
        let original = key(&state, None);
        assert_eq!(original, key(&state.clone(), None));
        assert_ne!(original, key(&changed, None));
        assert_eq!(key(&state, Some("session")), key(&changed, Some("session")));
        assert_ne!(
            key(&state, Some("session")),
            key(&state, Some("other-session"))
        );
        assert_ne!(original, key(&state, Some("session")));

        // Identical serialized JSON must not share chat and decision route keys.
        assert_ne!(
            original,
            route_key(
                workspace,
                "model",
                "release",
                None,
                RoutePrompt::ChatMessages(state.as_array().unwrap())
            )
        );
        for session in [None, Some("session")] {
            for (workspace_id, model, release) in [
                (Uuid::from_u128(10), "model", "release"),
                (workspace, "other-model", "release"),
                (workspace, "model", "other-release"),
            ] {
                assert_ne!(
                    key(&state, session),
                    route_key(
                        workspace_id,
                        model,
                        release,
                        session,
                        RoutePrompt::DecisionState(&state)
                    )
                );
            }
        }
        let prefix = "x".repeat(PREFIX_BYTE_LIMIT);
        let long = serde_json::json!(format!("{prefix}first"));
        let extended = serde_json::json!(format!("{prefix}second"));
        assert_eq!(key(&long, None), key(&extended, None));
    }

    #[test]
    fn diagnoses_missing_stale_mismatched_and_busy_deployments_without_changing_routing() {
        let deployments = deployments(5);
        let mut statuses = statuses(&deployments[1..]);
        statuses[0].received_at = now() - TimeDelta::seconds(16);
        statuses[1].runtime_revision = "different".to_owned();
        statuses[2].healthy = false;
        statuses[3].accepting_requests = false;

        assert_eq!(
            route(&deployments, &statuses, RoutePrompt::TokenIds(&[1]), None),
            RouteAvailability::AtCapacity(RouteDiagnostics {
                candidates: 5,
                missing_status: 1,
                stale_status: 1,
                revision_mismatch: 1,
                unhealthy: 1,
                at_capacity: 1,
                ..Default::default()
            })
        );
    }

    #[test]
    fn diagnoses_unavailable_invalid_and_foreign_release_deployments() {
        let mut deployments = deployments(5);
        let mut statuses = statuses(&deployments);
        deployments[0].status = DeploymentStatus::Draining;
        deployments[1].service_url = "not a url".to_owned();
        deployments[2].release.model_revision = "other-revision".to_owned();
        statuses[3].schema_version = 2;
        statuses[4].accepting_requests = false;

        assert_eq!(
            route(&deployments, &statuses, RoutePrompt::TokenIds(&[1]), None),
            RouteAvailability::AtCapacity(RouteDiagnostics {
                candidates: 5,
                unavailable: 1,
                invalid_deployment: 1,
                release_mismatch: 1,
                invalid_status: 1,
                at_capacity: 1,
                ..Default::default()
            })
        );
    }

    #[test]
    fn rendezvous_order_is_stable_and_uses_live_status() {
        let deployments = deployments(2);
        let statuses = statuses(&deployments);
        let session = Some("conversation-1");

        assert_eq!(
            route(
                &deployments,
                &statuses,
                RoutePrompt::TokenIds(&[1, 2, 3]),
                session
            ),
            route(
                &deployments,
                &statuses,
                RoutePrompt::TokenIds(&[9, 9, 9]),
                session
            ),
        );
    }

    #[test]
    fn removing_a_deployment_moves_only_the_keys_it_served() {
        let all = deployments(4);
        let removed = all[1].id;
        let remaining = all
            .iter()
            .filter(|deployment| deployment.id != removed)
            .cloned()
            .collect::<Vec<_>>();

        for session in 0..64 {
            let session = format!("session-{session}");
            let before = order(&all, &session);
            let after = order(&remaining, &session);

            let survivors = before
                .iter()
                .copied()
                .filter(|id| *id != removed)
                .collect::<Vec<_>>();
            assert_eq!(after, survivors, "{session}");
            if before[0] != removed {
                assert_eq!(after[0], before[0], "{session}");
            }
        }
    }

    #[test]
    fn order_does_not_depend_on_deployment_input_order() {
        let forward = deployments(4);
        let mut reversed = forward.clone();
        reversed.reverse();

        for session in ["a", "b", "c", "d"] {
            assert_eq!(order(&forward, session), order(&reversed, session));
        }
    }

    #[test]
    fn sessions_spread_across_every_deployment() {
        let deployments = deployments(3);

        let primaries = (0..256)
            .map(|session| order(&deployments, &format!("session-{session}"))[0])
            .collect::<std::collections::HashSet<_>>();

        assert_eq!(primaries.len(), 3);
    }

    #[test]
    fn stale_status_is_unavailable_and_busy_status_is_at_capacity() {
        let deployments = deployments(1);
        let mut runtime_status = status(&deployments[0]);
        let availability = |status: &DeploymentRuntimeStatus| {
            route(
                &deployments,
                std::slice::from_ref(status),
                RoutePrompt::TokenIds(&[1]),
                None,
            )
        };

        runtime_status.received_at = now() - TimeDelta::seconds(16);
        assert!(matches!(
            availability(&runtime_status),
            RouteAvailability::Unavailable(_)
        ));

        runtime_status.received_at = now() - TimeDelta::seconds(14);
        assert!(matches!(
            availability(&runtime_status),
            RouteAvailability::Ready(_)
        ));

        runtime_status.received_at = now();
        runtime_status.accepting_requests = false;
        assert!(matches!(
            availability(&runtime_status),
            RouteAvailability::AtCapacity(_)
        ));
    }

    #[test]
    fn healthy_count_agrees_with_routing_and_counts_each_deployment_once() {
        let mut deployments = deployments(5);
        let mut statuses = statuses(&deployments);
        deployments[0].status = DeploymentStatus::Draining;
        statuses[1].received_at = now() - TimeDelta::seconds(16);
        statuses[2].healthy = false;
        statuses.push(status(&deployments[4]));

        let routed = ready(route(
            &deployments,
            &statuses,
            RoutePrompt::TokenIds(&[1]),
            None,
        ));

        assert_eq!(
            routed.iter().collect::<std::collections::HashSet<_>>(),
            [&deployments[3].id, &deployments[4].id].into()
        );
        assert_eq!(
            healthy_deployment_count(&deployments, &statuses, now()),
            routed.len() as u64
        );
    }

    #[test]
    fn prefix_hashing_matches_a_truncated_serialization() {
        let truncated_hash = |value: &serde_json::Value| {
            let bytes = serde_json::to_vec(value).unwrap();
            Sha256::digest(&bytes[..bytes.len().min(PREFIX_BYTE_LIMIT)])
        };
        let streamed_hash = |value: &serde_json::Value| {
            let mut hash = Sha256::new();
            hash_json_prefix(&mut hash, value);
            hash.finalize()
        };

        for value in [
            serde_json::json!([{"role": "user", "content": "hello"}]),
            serde_json::json!([{"role": "user", "content": "x".repeat(PREFIX_BYTE_LIMIT)}]),
            serde_json::json!({"state": "é".repeat(PREFIX_BYTE_LIMIT)}),
        ] {
            assert_eq!(streamed_hash(&value), truncated_hash(&value));
        }
    }
}
