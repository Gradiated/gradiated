use std::collections::HashMap;

use chrono::{DateTime, TimeDelta, Utc};
use sha2::{Digest, Sha256};
use uuid::Uuid;
use validator::Validate;

use crate::{DeploymentRuntimeStatus, DeploymentStatus, GatewayModelDeployment};

const MAXIMUM_STATUS_AGE: TimeDelta = TimeDelta::seconds(15);
const PREFIX_TOKEN_LIMIT: usize = 4_096;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RoutedDeployment {
    pub deployment: GatewayModelDeployment,
    pub maximum_concurrency: u64,
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
    pub input_ids: &'a [u32],
    pub deployments: &'a [GatewayModelDeployment],
    pub statuses: &'a [DeploymentRuntimeStatus],
    pub now: DateTime<Utc>,
}

pub fn healthy_installed_concurrency(
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
        .map(|status| status.maximum_concurrency)
        .sum()
}

pub fn order_deployments(input: RouteInput<'_>) -> RouteAvailability {
    let RouteInput {
        workspace_id,
        model_id,
        release_digest,
        session_id,
        input_ids,
        deployments,
        statuses,
        now,
    } = input;
    let statuses: HashMap<Uuid, &DeploymentRuntimeStatus> = statuses
        .iter()
        .map(|status| (status.deployment_id, status))
        .collect();
    let mut healthy = Vec::new();
    for deployment in deployments {
        if deployment.status != DeploymentStatus::Available
            || deployment.validate().is_err()
            || deployment.served_release_digest().ok().as_deref() != Some(release_digest)
        {
            continue;
        }
        let Some(status) = statuses.get(&deployment.id) else {
            continue;
        };
        if status.validate().is_err()
            || status.runtime_revision != deployment.release.runtime_revision
            || !status.is_fresh_at(now, MAXIMUM_STATUS_AGE)
            || !status.healthy
        {
            continue;
        }
        healthy.push(RoutedDeployment {
            deployment: deployment.clone(),
            maximum_concurrency: status.maximum_concurrency,
        });
    }
    if healthy.is_empty() {
        return RouteAvailability::Unavailable;
    }
    healthy.retain(|candidate| {
        statuses
            .get(&candidate.deployment.id)
            .is_some_and(|status| status.accepting_requests)
    });
    if healthy.is_empty() {
        return RouteAvailability::AtCapacity;
    }

    let route_key = route_key(
        workspace_id,
        model_id,
        release_digest,
        session_id,
        input_ids,
    );
    healthy.sort_by(|left, right| {
        rendezvous_score(&route_key, right.deployment.id)
            .cmp(&rendezvous_score(&route_key, left.deployment.id))
    });
    RouteAvailability::Ready(healthy)
}

fn route_key(
    workspace_id: Uuid,
    model_id: &str,
    release_digest: &str,
    session_id: Option<&str>,
    input_ids: &[u32],
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
        hash.update([0]);
        for token in input_ids.iter().take(PREFIX_TOKEN_LIMIT) {
            hash.update(token.to_be_bytes());
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
            maximum_concurrency: 4,
            reason_code: None,
        }
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
            input_ids: &[1, 2, 3],
            deployments: &deployments,
            statuses: &statuses,
            now,
        });
        let second = order_deployments(RouteInput {
            workspace_id: Uuid::from_u128(9),
            model_id: "z-ai/glm-5.3-flash",
            release_digest: &digest,
            session_id: Some("conversation-1"),
            input_ids: &[9, 9, 9],
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
                input_ids: &[1],
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
                input_ids: &[1],
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
                input_ids: &[1],
                deployments: &deployments,
                statuses: &[runtime_status],
                now,
            }),
            RouteAvailability::AtCapacity,
        );
    }
}
