use std::{future::Future, sync::Arc, time::Instant};

use chrono::{DateTime, Utc};
use uuid::Uuid;

use super::{settlement::FailedGeneration, unless_panicked};
use crate::{
    GatewayModelDeployment, InferenceRequest, ModelRuntime, NormalizedUsage, RuntimeCompletion,
    RuntimeEventStream, RuntimeFailure, RuntimeFailureKind,
};

pub(super) struct RuntimeCall {
    pub(super) runtime: Arc<dyn ModelRuntime>,
    pub(super) generation_id: Uuid,
    pub(super) request: InferenceRequest,
    pub(super) effective_output_tokens: u64,
    pub(super) deadline: DateTime<Utc>,
    pub(super) deployment: GatewayModelDeployment,
    pub(super) fallbacks: Vec<GatewayModelDeployment>,
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
        match unless_panicked(self.generation_id, self.dispatch_with_retry(send)).await {
            Some(result) => {
                result.map_err(|failure| FailedGeneration::from_runtime_failure(&failure))
            }
            None => Err(FailedGeneration::panicked()),
        }
    }

    /// Only a first attempt that the runtime rejected before doing any work may
    /// retry, so no generation is ever run twice.
    async fn dispatch_with_retry<T, F>(
        &mut self,
        send: impl Fn(RuntimeAttempt) -> F,
    ) -> Result<T, RuntimeFailure>
    where
        F: Future<Output = Result<T, RuntimeFailure>>,
    {
        let started = Instant::now();
        let failure = match send(self.attempt()).await {
            Ok(response) => return Ok(response),
            Err(failure) => failure,
        };

        let fallback = self.retry_target(&failure);
        self.log_failure(&failure, 1, started, fallback.is_some());
        let Some(fallback) = fallback else {
            return Err(failure);
        };

        self.deployment = fallback;
        let started = Instant::now();
        let result = send(self.attempt()).await;

        if let Err(failure) = &result {
            self.log_failure(failure, 2, started, false);
        }

        result
    }

    fn attempt(&self) -> RuntimeAttempt {
        RuntimeAttempt {
            runtime: self.runtime.clone(),
            deployment: self.deployment.clone(),
            request: self.request.clone(),
            output_tokens: self.effective_output_tokens,
            deadline: self.deadline,
        }
    }

    fn retry_target(&mut self, failure: &RuntimeFailure) -> Option<GatewayModelDeployment> {
        let retryable = failure.usage() == NormalizedUsage::zero()
            && matches!(
                failure.kind(),
                RuntimeFailureKind::Unavailable | RuntimeFailureKind::CapacityExceeded
            );
        if !retryable {
            return None;
        }

        self.take_fallback(failure.kind())
    }

    fn log_failure(&self, failure: &RuntimeFailure, attempt: u8, started: Instant, retry: bool) {
        failure.log_attempt(
            self.generation_id,
            &self.request.model,
            self.deployment.id,
            attempt,
            started.elapsed().as_millis() as u64,
            retry,
        );
    }

    /// Prefers a candidate in another fault domain and, when the runtime was
    /// unavailable rather than full, one from another provider.
    pub(super) fn take_fallback(
        &mut self,
        failure: RuntimeFailureKind,
    ) -> Option<GatewayModelDeployment> {
        let prior = &self.deployment;
        let (index, _) = self
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
            })?;

        Some(self.fallbacks.remove(index))
    }
}

struct RuntimeAttempt {
    runtime: Arc<dyn ModelRuntime>,
    deployment: GatewayModelDeployment,
    request: InferenceRequest,
    output_tokens: u64,
    deadline: DateTime<Utc>,
}

impl RuntimeAttempt {
    async fn complete(self) -> Result<RuntimeCompletion, RuntimeFailure> {
        self.runtime
            .complete(
                &self.deployment,
                self.request,
                self.output_tokens,
                self.deadline,
            )
            .await
    }

    async fn stream(self) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        self.runtime
            .stream(
                &self.deployment,
                self.request,
                self.output_tokens,
                self.deadline,
            )
            .await
    }
}
