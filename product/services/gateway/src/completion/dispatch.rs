use std::{
    future::Future,
    sync::Arc,
    time::{Duration, Instant},
};

use chrono::{DateTime, Utc};
use uuid::Uuid;

use super::{settlement::FailedGeneration, unless_panicked};
use crate::{
    metrics::{Capacity, CapacityMetrics, FallbackReason},
    ExternalCapacity, ExternalModel, ExternalRequest, GatewayModelDeployment, InferenceRequest,
    ModelRuntime, NormalizedUsage, Route, RuntimeCompletion, RuntimeEventStream, RuntimeFailure,
    RuntimeFailureKind,
};

/// An attempt with less time than this left would only spend the deadline.
const MIN_FALLBACK_BUDGET: Duration = Duration::from_secs(1);
const MAX_LOCAL_ATTEMPTS: u8 = 2;

/// Where a generation runs now, and what it may still move to.
pub(super) struct CapacityPlan {
    pub(super) target: Target,
    pub(super) fallbacks: Vec<GatewayModelDeployment>,
    pub(super) degraded: Option<LocalTier>,
    pub(super) external: Option<ExternalModel>,
    /// Why `target` is not the preferred local capacity.
    pub(super) reason: Option<FallbackReason>,
}

pub(super) struct LocalTier {
    pub(super) route: Route,
    pub(super) served_release_digest: String,
    pub(super) adapter: bool,
}

impl LocalTier {
    fn split(self) -> (Target, Vec<GatewayModelDeployment>) {
        let target = Target::Local {
            deployment: self.route.primary,
            served_release_digest: self.served_release_digest,
            adapter: self.adapter,
        };

        (target, self.route.fallbacks)
    }
}

impl CapacityPlan {
    pub(super) fn local(tier: LocalTier) -> Self {
        let (target, fallbacks) = tier.split();

        Self {
            target,
            fallbacks,
            degraded: None,
            external: None,
            reason: None,
        }
    }

    pub(super) fn external(model: ExternalModel, reason: FallbackReason) -> Self {
        Self {
            target: Target::External(model),
            fallbacks: Vec::new(),
            degraded: None,
            external: None,
            reason: Some(reason),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
#[expect(
    clippy::large_enum_variant,
    reason = "one per generation, replaced only between attempts"
)]
pub(super) enum Target {
    Local {
        deployment: GatewayModelDeployment,
        served_release_digest: String,
        /// False when a base deployment serves an adapter's request without it.
        adapter: bool,
    },
    External(ExternalModel),
}

impl Target {
    pub(super) fn metric_label(&self) -> String {
        match self {
            Self::Local { deployment, .. } => deployment.id.to_string(),
            Self::External(_) => "openrouter".to_owned(),
        }
    }

    pub(super) fn capacity(&self) -> Capacity {
        match self {
            Self::Local { adapter: false, .. } => Capacity::Local,
            Self::Local { adapter: true, .. } => Capacity::Adapter,
            Self::External(_) => Capacity::OpenRouter,
        }
    }

    pub(super) fn protocol_label(&self) -> &'static str {
        match self {
            Self::Local { deployment, .. } => deployment.release.protocol_label(),
            Self::External(_) => "openai_chat",
        }
    }

    pub(super) fn served_release_digest(&self) -> String {
        match self {
            Self::Local {
                served_release_digest,
                ..
            } => served_release_digest.clone(),
            Self::External(model) => model.served_release_digest(),
        }
    }

    pub(super) fn deployment_id(&self) -> Option<Uuid> {
        match self {
            Self::Local { deployment, .. } => Some(deployment.id),
            Self::External(_) => None,
        }
    }
}

pub(super) struct RuntimeCall {
    pub(super) runtime: Arc<dyn ModelRuntime>,
    pub(super) external_runtime: Option<Arc<dyn ExternalCapacity>>,
    pub(super) generation_id: Uuid,
    pub(super) workspace_id: Uuid,
    pub(super) request: InferenceRequest,
    pub(super) effective_output_tokens: u64,
    pub(super) deadline: DateTime<Utc>,
    pub(super) plan: CapacityPlan,
    pub(super) local_attempts: u8,
    pub(super) attempts: u8,
    pub(super) capacity_metrics: CapacityMetrics,
}

impl CapacityPlan {
    /// Prefers another fault domain, and another provider after an outage.
    fn move_to_replica(&mut self, failure: RuntimeFailureKind) -> bool {
        let Target::Local {
            deployment: prior,
            served_release_digest,
            adapter,
        } = &self.target
        else {
            return false;
        };

        let Some((index, _)) = self
            .fallbacks
            .iter()
            .enumerate()
            .min_by_key(|(_, candidate)| {
                let same_fault_domain = candidate.fault_domain == prior.fault_domain;
                let same_provider = candidate.provider == prior.provider;
                (
                    same_fault_domain,
                    failure == RuntimeFailureKind::Unavailable && same_provider,
                )
            })
        else {
            return false;
        };

        self.target = Target::Local {
            deployment: self.fallbacks.remove(index),
            served_release_digest: served_release_digest.clone(),
            adapter: *adapter,
        };

        true
    }

    /// The degraded base model while a local attempt is left, else OpenRouter.
    fn move_to_next_tier(&mut self, local_attempt_left: bool) -> bool {
        let next = match self.degraded.take() {
            Some(tier) if local_attempt_left => {
                let (target, fallbacks) = tier.split();
                self.fallbacks = fallbacks;
                target
            }
            _ => match self.external.take() {
                Some(model) => Target::External(model),
                None => return false,
            },
        };

        self.target = next;

        true
    }

    /// Metric labels of every capacity the generation may still move to.
    pub(super) fn later_labels(&self) -> Vec<String> {
        let local =
            self.fallbacks
                .iter()
                .chain(self.degraded.iter().flat_map(|tier| {
                    std::iter::once(&tier.route.primary).chain(&tier.route.fallbacks)
                }))
                .map(|deployment| deployment.id.to_string());

        local
            .chain(self.external.iter().map(|_| "openrouter".to_owned()))
            .collect()
    }
}

impl RuntimeCall {
    pub(super) async fn complete(&mut self) -> Result<RuntimeCompletion, FailedGeneration> {
        self.dispatch(RuntimeAttempt::complete).await
    }

    pub(super) async fn stream(&mut self) -> Result<Box<dyn RuntimeEventStream>, FailedGeneration> {
        self.dispatch(RuntimeAttempt::stream).await
    }

    async fn dispatch<T, F>(
        &mut self,
        send: impl Fn(RuntimeAttempt) -> F,
    ) -> Result<T, FailedGeneration>
    where
        F: Future<Output = Result<T, RuntimeFailure>>,
    {
        match unless_panicked(self.generation_id, self.dispatch_with_fallback(send)).await {
            Some(result) => {
                result.map_err(|failure| FailedGeneration::from_runtime_failure(&failure))
            }
            None => Err(FailedGeneration::panicked()),
        }
    }

    /// Earlier attempts delivered nothing, so only the attempt that ends the loop is billed.
    async fn dispatch_with_fallback<T, F>(
        &mut self,
        send: impl Fn(RuntimeAttempt) -> F,
    ) -> Result<T, RuntimeFailure>
    where
        F: Future<Output = Result<T, RuntimeFailure>>,
    {
        loop {
            let started = Instant::now();
            let failure = match send(self.attempt()).await {
                Ok(response) => return Ok(response),
                Err(failure) => failure,
            };

            let refused = failure.usage() == NormalizedUsage::zero()
                && matches!(
                    failure.kind(),
                    RuntimeFailureKind::Unavailable | RuntimeFailureKind::CapacityExceeded
                );
            let failed_target = self.plan.target.clone();
            let next = self.fall_back(failure.kind(), refused);
            failure.log_attempt(
                self.generation_id,
                &self.request.model,
                failed_target.deployment_id(),
                failed_target.capacity().as_str(),
                self.attempts,
                started.elapsed().as_millis() as u64,
                next.map(Capacity::as_str),
            );

            if next.is_none() {
                return Err(failure);
            }
        }
    }

    fn attempt(&mut self) -> RuntimeAttempt {
        self.attempts += 1;
        let mut request = self.request.clone();

        match &self.plan.target {
            Target::Local {
                deployment,
                adapter,
                ..
            } => {
                self.local_attempts += 1;
                if !adapter {
                    request.runtime_model_name = None;
                }

                RuntimeAttempt::Local {
                    runtime: self.runtime.clone(),
                    deployment: deployment.clone(),
                    request,
                    output_tokens: self.effective_output_tokens,
                    deadline: self.deadline,
                }
            }
            Target::External(model) => RuntimeAttempt::External {
                client: self
                    .external_runtime
                    .clone()
                    .expect("only a configured client plans external capacity"),
                request: ExternalRequest {
                    generation_id: self.generation_id,
                    workspace_id: self.workspace_id,
                    model: model.clone(),
                    request,
                    output_tokens: self.effective_output_tokens,
                    deadline: self.deadline,
                },
            },
        }
    }

    /// `None` means the failure is final. `refused` permits another replica of the
    /// same capacity: the runtime did no work, so none runs twice.
    pub(super) fn fall_back(
        &mut self,
        failure: RuntimeFailureKind,
        refused: bool,
    ) -> Option<Capacity> {
        if matches!(self.plan.target, Target::External(_)) {
            return None;
        }

        let local_attempt_left = self.local_attempts < MAX_LOCAL_ATTEMPTS;
        if refused && local_attempt_left && self.plan.move_to_replica(failure) {
            return Some(self.plan.target.capacity());
        }

        if !self.can_fall_back(failure) || !self.plan.move_to_next_tier(local_attempt_left) {
            return None;
        }

        let reason = if failure == RuntimeFailureKind::CapacityExceeded {
            FallbackReason::CapacityExceeded
        } else {
            FallbackReason::AttemptFailed
        };
        self.capacity_metrics
            .fell_back(self.plan.target.capacity(), reason);
        self.plan.reason = Some(reason);

        Some(self.plan.target.capacity())
    }

    /// A request the runtime called invalid is the caller's to fix, and a shared
    /// deadline with almost no time left cannot be met by another attempt.
    fn can_fall_back(&self, failure: RuntimeFailureKind) -> bool {
        let remaining = self
            .deadline
            .signed_duration_since(Utc::now())
            .to_std()
            .unwrap_or_default();

        failure != RuntimeFailureKind::InvalidRequest && remaining >= MIN_FALLBACK_BUDGET
    }
}

#[expect(
    clippy::large_enum_variant,
    reason = "built for one attempt and consumed by it"
)]
enum RuntimeAttempt {
    Local {
        runtime: Arc<dyn ModelRuntime>,
        deployment: GatewayModelDeployment,
        request: InferenceRequest,
        output_tokens: u64,
        deadline: DateTime<Utc>,
    },
    External {
        client: Arc<dyn ExternalCapacity>,
        request: ExternalRequest,
    },
}

impl RuntimeAttempt {
    async fn complete(self) -> Result<RuntimeCompletion, RuntimeFailure> {
        match self {
            Self::Local {
                runtime,
                deployment,
                request,
                output_tokens,
                deadline,
            } => {
                runtime
                    .complete(&deployment, request, output_tokens, deadline)
                    .await
            }
            Self::External { client, request } => client.complete(request).await,
        }
    }

    async fn stream(self) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        match self {
            Self::Local {
                runtime,
                deployment,
                request,
                output_tokens,
                deadline,
            } => {
                runtime
                    .stream(&deployment, request, output_tokens, deadline)
                    .await
            }
            Self::External { client, request } => client.stream(request).await,
        }
    }
}

#[cfg(test)]
impl RuntimeCall {
    pub(super) fn local(
        runtime: Arc<dyn ModelRuntime>,
        request: InferenceRequest,
        effective_output_tokens: u64,
        deadline: DateTime<Utc>,
        deployment: GatewayModelDeployment,
        fallbacks: Vec<GatewayModelDeployment>,
    ) -> Self {
        Self {
            runtime,
            external_runtime: None,
            generation_id: Uuid::now_v7(),
            workspace_id: Uuid::now_v7(),
            request,
            effective_output_tokens,
            deadline,
            plan: CapacityPlan {
                target: Target::Local {
                    served_release_digest: deployment.served_release_digest().unwrap(),
                    deployment,
                    adapter: false,
                },
                fallbacks,
                degraded: None,
                external: None,
                reason: None,
            },
            local_attempts: 0,
            attempts: 0,
            capacity_metrics: crate::GatewayMetrics::new().capacity("model-a", false),
        }
    }

    pub(super) fn deployment(&self) -> &GatewayModelDeployment {
        match &self.plan.target {
            Target::Local { deployment, .. } => deployment,
            Target::External(_) => panic!("the call targets external capacity"),
        }
    }
}
