use std::collections::HashMap;

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
pub struct RoutedDeployment {
    pub deployment: GatewayModelDeployment,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RouteAvailability {
    Ready(Vec<RoutedDeployment>),
    AtCapacity,
    Unavailable,
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
    let deployments: HashMap<Uuid, &GatewayModelDeployment> = deployments
        .iter()
        .filter(|deployment| {
            deployment.status == DeploymentStatus::Available && deployment.validate().is_ok()
        })
        .map(|deployment| (deployment.id, deployment))
        .collect();
    statuses
        .iter()
        .filter(|status| {
            status.validate().is_ok()
                && status.healthy
                && status.is_fresh_at(now, MAXIMUM_STATUS_AGE)
                && deployments
                    .get(&status.deployment_id)
                    .is_some_and(|deployment| {
                        status.runtime_revision == deployment.release.runtime_revision
                    })
        })
        .count() as u64
}

/// Counts only the first rejection reason for each candidate; never contains endpoints.
#[derive(Default, Debug, Eq, PartialEq)]
pub(crate) struct RouteDiagnostics {
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

/// Why a deployment cannot serve a request, in the order the checks run.
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

/// Returns the fresh, healthy status of a deployment that serves the release.
fn healthy_status<'a>(
    deployment: &GatewayModelDeployment,
    statuses: &HashMap<Uuid, &'a DeploymentRuntimeStatus>,
    release_digest: &str,
    now: DateTime<Utc>,
) -> Result<&'a DeploymentRuntimeStatus, Rejection> {
    if deployment.status != DeploymentStatus::Available {
        return Err(Rejection::Unavailable);
    }
    if deployment.validate().is_err() {
        return Err(Rejection::InvalidDeployment);
    }
    if deployment.served_release_digest().ok().as_deref() != Some(release_digest) {
        return Err(Rejection::ReleaseMismatch);
    }

    let status = *statuses
        .get(&deployment.id)
        .ok_or(Rejection::MissingStatus)?;
    if status.validate().is_err() {
        return Err(Rejection::InvalidStatus);
    }
    if status.runtime_revision != deployment.release.runtime_revision {
        return Err(Rejection::RevisionMismatch);
    }
    if !status.is_fresh_at(now, MAXIMUM_STATUS_AGE) {
        return Err(Rejection::StaleStatus);
    }
    if !status.healthy {
        return Err(Rejection::Unhealthy);
    }

    Ok(status)
}

pub fn order_deployments(input: RouteInput<'_>) -> RouteAvailability {
    order_deployments_diagnosed(input).0
}

/// Orders the healthy deployments that are accepting requests by rendezvous
/// hash, so one session or prompt prefix keeps landing on the same runtime.
pub(crate) fn order_deployments_diagnosed(
    input: RouteInput<'_>,
) -> (RouteAvailability, RouteDiagnostics) {
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
    let statuses: HashMap<Uuid, &DeploymentRuntimeStatus> = statuses
        .iter()
        .map(|status| (status.deployment_id, status))
        .collect();
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
        return (RouteAvailability::Unavailable, diagnostics);
    }

    let mut accepting: Vec<RoutedDeployment> = healthy
        .iter()
        .filter(|(_, accepting)| *accepting)
        .map(|(deployment, _)| RoutedDeployment {
            deployment: (*deployment).clone(),
        })
        .collect();
    diagnostics.at_capacity = healthy.len() - accepting.len();
    if accepting.is_empty() {
        return (RouteAvailability::AtCapacity, diagnostics);
    }

    let route_key = route_key(workspace_id, model_id, release_digest, session_id, prompt);
    accepting.sort_by_cached_key(|candidate| {
        std::cmp::Reverse(rendezvous_score(&route_key, candidate.deployment.id))
    });

    (RouteAvailability::Ready(accepting), diagnostics)
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
    if let Some(session_id) = session_id {
        hash.update([1]);
        hash.update((session_id.len() as u64).to_be_bytes());
        hash.update(session_id.as_bytes());
    } else {
        match prompt {
            RoutePrompt::TokenIds(input_ids) => {
                hash.update([0]);
                for token in input_ids.iter().take(PREFIX_TOKEN_LIMIT) {
                    hash.update(token.to_be_bytes());
                }
            }
            RoutePrompt::ChatMessages(messages) => {
                hash.update([2]);
                // JSON values are serializable without consulting model artifacts.
                let bytes = serde_json::to_vec(messages).expect("chat messages are JSON values");
                hash.update(&bytes[..bytes.len().min(PREFIX_BYTE_LIMIT)]);
            }
            RoutePrompt::DecisionState(state) => {
                hash.update([3]);
                let bytes = serde_json::to_vec(state).expect("decision state is JSON");
                hash.update(&bytes[..bytes.len().min(PREFIX_BYTE_LIMIT)]);
            }
        }
    }
    hash.finalize().into()
}

fn rendezvous_score(route_key: &[u8; 32], deployment_id: Uuid) -> [u8; 32] {
    let mut hash = Sha256::new();
    hash.update(route_key);
    hash.update(deployment_id.as_bytes());
    hash.finalize().into()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ModelDeploymentRelease;

    fn deployment(id: u128) -> GatewayModelDeployment {
        GatewayModelDeployment {
            id: Uuid::from_u128(id),
            status: DeploymentStatus::Available,
            provider: "runpod".to_owned(),
            region: "sg".to_owned(),
            fault_domain: format!("runpod:runtime-{id}"),
            service_url: format!("https://runtime-{id}.example.test"),
            release: ModelDeploymentRelease {
                schema_version: 1,
                runtime_revision: "vllm-revision".to_owned(),
                protocol: None,
                model_path: "zai-org/GLM-5.3-Flash".to_owned(),
                model_revision: "model-revision".to_owned(),
                runtime_model_name: None,
                tokenizer_path: "zai-org/GLM-5.3-Flash".to_owned(),
                tokenizer_revision: "model-revision".to_owned(),
                tokenizer_mode: None,
            },
        }
    }

    fn status(deployment: &GatewayModelDeployment, now: DateTime<Utc>) -> DeploymentRuntimeStatus {
        DeploymentRuntimeStatus {
            schema_version: 1,
            deployment_id: deployment.id,
            runtime_revision: deployment.release.runtime_revision.clone(),
            received_at: now,
            healthy: true,
            accepting_requests: true,
            reason_code: None,
        }
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
        let now = Utc::now();
        let deployments = (1..=5).map(deployment).collect::<Vec<_>>();
        let digest = deployments[0].served_release_digest().unwrap();
        let mut statuses = deployments[1..]
            .iter()
            .map(|d| status(d, now))
            .collect::<Vec<_>>();
        statuses[0].received_at = now - TimeDelta::seconds(16);
        statuses[1].runtime_revision = "different".to_owned();
        statuses[2].healthy = false;
        statuses[3].accepting_requests = false;
        let (availability, diagnostics) = order_deployments_diagnosed(RouteInput {
            workspace_id: Uuid::from_u128(9),
            model_id: "model",
            release_digest: &digest,
            session_id: None,
            prompt: RoutePrompt::TokenIds(&[1]),
            deployments: &deployments,
            statuses: &statuses,
            now,
        });
        assert_eq!(availability, RouteAvailability::AtCapacity);
        assert_eq!(
            diagnostics,
            RouteDiagnostics {
                candidates: 5,
                missing_status: 1,
                stale_status: 1,
                revision_mismatch: 1,
                unhealthy: 1,
                at_capacity: 1,
                ..Default::default()
            }
        );
    }

    #[test]
    fn rendezvous_order_is_stable_and_uses_live_status() {
        let now = Utc::now();
        let deployments = vec![deployment(1), deployment(2)];
        let digest = deployments[0].served_release_digest().unwrap();
        let statuses = deployments
            .iter()
            .map(|deployment| status(deployment, now))
            .collect::<Vec<_>>();
        let first = order_deployments(RouteInput {
            workspace_id: Uuid::from_u128(9),
            model_id: "z-ai/glm-5.3-flash",
            release_digest: &digest,
            session_id: Some("conversation-1"),
            prompt: RoutePrompt::TokenIds(&[1, 2, 3]),
            deployments: &deployments,
            statuses: &statuses,
            now,
        });
        let second = order_deployments(RouteInput {
            workspace_id: Uuid::from_u128(9),
            model_id: "z-ai/glm-5.3-flash",
            release_digest: &digest,
            session_id: Some("conversation-1"),
            prompt: RoutePrompt::TokenIds(&[9, 9, 9]),
            deployments: &deployments,
            statuses: &statuses,
            now,
        });
        assert_eq!(first, second);
    }

    #[test]
    fn stale_status_is_unavailable_and_busy_status_is_at_capacity() {
        let now = Utc::now();
        let deployments = vec![deployment(1)];
        let digest = deployments[0].served_release_digest().unwrap();
        let mut runtime_status = status(&deployments[0], now - TimeDelta::seconds(16));
        assert_eq!(
            order_deployments(RouteInput {
                workspace_id: Uuid::from_u128(9),
                model_id: "model",
                release_digest: &digest,
                session_id: None,
                prompt: RoutePrompt::TokenIds(&[1]),
                deployments: &deployments,
                statuses: &[runtime_status.clone()],
                now,
            }),
            RouteAvailability::Unavailable,
        );
        runtime_status.received_at = now - TimeDelta::seconds(14);
        assert!(matches!(
            order_deployments(RouteInput {
                workspace_id: Uuid::from_u128(9),
                model_id: "model",
                release_digest: &digest,
                session_id: None,
                prompt: RoutePrompt::TokenIds(&[1]),
                deployments: &deployments,
                statuses: &[runtime_status.clone()],
                now,
            }),
            RouteAvailability::Ready(_),
        ));
        runtime_status.received_at = now;
        runtime_status.accepting_requests = false;
        assert_eq!(
            order_deployments(RouteInput {
                workspace_id: Uuid::from_u128(9),
                model_id: "model",
                release_digest: &digest,
                session_id: None,
                prompt: RoutePrompt::TokenIds(&[1]),
                deployments: &deployments,
                statuses: &[runtime_status],
                now,
            }),
            RouteAvailability::AtCapacity,
        );
    }
}
