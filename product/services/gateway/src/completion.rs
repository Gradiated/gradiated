mod dispatch;
mod settlement;
mod stream;
mod tasks;

use std::{
    cmp,
    future::Future,
    panic::AssertUnwindSafe,
    sync::Arc,
    time::{Duration, Instant},
};

use chrono::Utc;
use futures_util::{stream as stream_util, FutureExt};
use serde_json::Value;
use tokio::sync::{mpsc, oneshot, watch};
use uuid::Uuid;

use self::{
    dispatch::RuntimeCall,
    settlement::{
        Delivery, FailedGeneration, GenerationEnd, GenerationSettlement, GenerationTerminal,
    },
    stream::{StreamProgress, StreamStop},
    tasks::{force_shutdown_requested, ActiveGeneration, GenerationTasks},
};
use crate::{
    metrics::{AdmittedGenerationMetrics, GenerationScope},
    protocol::StreamItem,
    routing::{order_deployments, RoutePrompt},
    AdmissionLease, BoundedRequest, CancellationOwner, GatewayConfig, GatewayError, GatewayMetrics,
    GenerationIdentity, InferenceRequest, ModelRuntime, ModelTokenizer, QualifiedRequest, Route,
    RouteAvailability, RouteInput, ServiceTier, ServingState,
};

const STREAM_CHANNEL_CAPACITY: usize = 8;
const STREAM_STARTUP_GRACE: Duration = Duration::from_secs(1);

#[derive(Clone)]
pub struct CompletionService {
    tokenizer: ModelTokenizer,
    serving_state: Arc<dyn ServingState>,
    runtime: Arc<dyn ModelRuntime>,
    config: Arc<GatewayConfig>,
    tasks: GenerationTasks,
    metrics: GatewayMetrics,
}

impl CompletionService {
    pub fn new(
        serving_state: Arc<dyn ServingState>,
        runtime: Arc<dyn ModelRuntime>,
        tokenizer: ModelTokenizer,
        config: Arc<GatewayConfig>,
    ) -> Self {
        Self {
            tokenizer,
            serving_state,
            runtime,
            config,
            tasks: GenerationTasks::new(),
            metrics: GatewayMetrics::new(),
        }
    }

    pub fn metrics(&self) -> GatewayMetrics {
        self.metrics.clone()
    }

    pub fn begin_draining(&self) {
        self.tasks.begin_draining();
    }

    pub fn is_draining(&self) -> bool {
        self.tasks.is_draining()
    }

    pub fn force_shutdown(&self) {
        self.tasks.force_shutdown();
    }

    pub async fn wait_for_drain(&self) {
        self.tasks.wait().await;
    }

    pub async fn complete(
        &self,
        qualified: QualifiedRequest,
    ) -> Result<CompletionResponse, GatewayError> {
        let Some(active) = self.tasks.enter() else {
            return Err(GatewayError::RuntimeUnavailable);
        };

        let streaming = qualified.request.stream;
        let service_tier = qualified.request.service_tier;
        let qualified = self.bound(qualified).await?;
        let route = self.route(&qualified).await?;
        let generation = self.admit(qualified, route).await?;

        if streaming {
            let result = self.stream(active, generation).await?;
            Ok(CompletionResponse::Streaming {
                result,
                service_tier,
            })
        } else {
            let result = self.run(active, generation).await?;
            Ok(CompletionResponse::NonStreaming {
                result,
                service_tier,
            })
        }
    }

    pub async fn count_tokens(&self, qualified: &QualifiedRequest) -> Result<u64, GatewayError> {
        self.tokenizer.count(qualified).await
    }

    async fn bound(&self, qualified: QualifiedRequest) -> Result<QualifiedRequest, GatewayError> {
        if qualified.deployment.release.sends_token_ids() {
            let BoundedRequest { qualified, .. } = self.tokenizer.enforce(qualified).await?;

            return Ok(qualified);
        }

        // Chat deployments own normalization, tokenization, and context
        // validation. Local rendering must not veto their requests.
        Ok(qualified)
    }

    async fn route(&self, request: &QualifiedRequest) -> Result<Route, GatewayError> {
        let statuses = self
            .serving_state
            .deployment_statuses(&request.served_release_digest)
            .await
            .map_err(|error| {
                crate::diagnostics::limited_warn!(generation_id = %request.metadata.generation_id,
                    model_id = %request.request.model, phase = "deployment_status_read",
                    error_code = error.diagnostic_code(), "routing dependency failed");
                GatewayError::ServingStateUnavailable
            })?;

        let availability = order_deployments(RouteInput {
            workspace_id: request.identity.workspace_id,
            model_id: &request.request.model,
            release_digest: &request.served_release_digest,
            session_id: request.request.session_id.as_deref(),
            prompt: route_prompt(&request.request),
            deployments: &request.model_deployments,
            statuses: &statuses,
            now: Utc::now(),
        });

        let (diagnostics, error) = match availability {
            RouteAvailability::Ready(route) => return Ok(route),
            RouteAvailability::AtCapacity(diagnostics) => {
                self.metrics.routing_capacity_rejected(
                    request
                        .adapter
                        .as_ref()
                        .map_or(request.request.model.as_str(), |adapter| {
                            adapter.base_model_id.as_str()
                        }),
                    request.is_verification,
                );

                (diagnostics, GatewayError::CapacityExceeded)
            }
            RouteAvailability::Unavailable(diagnostics) => {
                (diagnostics, GatewayError::RuntimeUnavailable)
            }
        };

        diagnostics.warn(request.metadata.generation_id, &request.request.model);
        Err(error)
    }

    async fn admit(
        &self,
        request: QualifiedRequest,
        route: Route,
    ) -> Result<Generation, GatewayError> {
        let generation_identity = GenerationIdentity::authenticated(
            &request.identity,
            request.request.model.clone(),
            request.adapter.as_ref().map_or_else(
                || request.served_release_digest.clone(),
                |adapter| adapter.served_digest(&request.served_release_digest),
            ),
        )
        .map_err(|error| {
            crate::diagnostics::limited_error!(generation_id = %request.metadata.generation_id,
                phase = "generation_identity", error_code = error.diagnostic_code(),
                "generation identity rejected");
            GatewayError::ServingStateUnavailable
        })?;

        let admitted_at = cmp::max(Utc::now(), request.metadata.received_at);
        let admission = self
            .serving_state
            .admit(
                request.metadata.generation_id,
                request.identity.organization_id,
                request.metadata.received_at,
                admitted_at,
                &self.config,
            )
            .await;

        let scope = GenerationScope {
            model: request
                .adapter
                .as_ref()
                .map_or(request.request.model.as_str(), |adapter| {
                    adapter.base_model_id.as_str()
                }),
            deployment: route.primary.id,
            protocol: route.primary.release.protocol_label(),
            stream: request.request.stream,
            service_tier: request.request.service_tier,
            is_verification: request.is_verification,
        };
        let lease = match admission {
            Ok(lease) => lease,
            Err(error) => {
                self.metrics.record_admission_rejection(&scope, &error);
                return Err(error.into());
            }
        };

        let metrics = self.metrics.generation_admitted(&scope);

        Ok(Generation {
            request,
            route,
            generation_identity,
            lease,
            serving_state: self.serving_state.clone(),
            runtime: self.runtime.clone(),
            metrics,
        })
    }

    async fn run(
        &self,
        active: ActiveGeneration,
        generation: Generation,
    ) -> Result<CompletionResult, GatewayError> {
        // The generation runs on its own task so settlement completes after the caller
        // goes away. The task reads the dropped `_waiting` sender as cancellation.
        let (_waiting, cancellation) = oneshot::channel();
        let generation_id = generation.id();

        active
            .spawn(generation.complete(cancellation, self.tasks.subscribe()))
            .await
            .map_err(|join_error| {
                log_generation_task_failure(generation_id, join_error.is_panic());
                GatewayError::FinalizationUnavailable
            })?
    }

    async fn stream(
        &self,
        active: ActiveGeneration,
        generation: Generation,
    ) -> Result<StreamingCompletion, GatewayError> {
        let (events, receiver) = mpsc::channel(STREAM_CHANNEL_CAPACITY);
        let (started, startup) = oneshot::channel();
        let shutdown = self.tasks.subscribe();
        let failure_events = events.clone();
        let generation_id = generation.id();

        active.spawn(async move {
            let streamed = AssertUnwindSafe(generation.stream(started, events, shutdown))
                .catch_unwind()
                .await;

            if streamed.is_err() {
                log_generation_task_failure(generation_id, true);
                let _ = failure_events
                    .send(StreamItem::Error(GatewayError::FinalizationUnavailable))
                    .await;
            }
        });

        startup
            .await
            .map_err(|_| GatewayError::FinalizationUnavailable)??;

        Ok(StreamingCompletion { receiver })
    }
}

fn log_generation_task_failure(generation_id: Uuid, panicked: bool) {
    crate::diagnostics::limited_error!(
        %generation_id,
        phase = "generation_task",
        panicked,
        "generation task ended without a result"
    );
}

/// A panic in runtime code must not skip settlement, so runtime work runs
/// inside this boundary and settlement stays outside it.
async fn unless_panicked<T>(
    generation_id: Uuid,
    runtime_work: impl Future<Output = T>,
) -> Option<T> {
    let result = AssertUnwindSafe(runtime_work).catch_unwind().await;

    if result.is_err() {
        crate::diagnostics::limited_error!(%generation_id, phase = "runtime",
            error_code = "runtime_panic", "runtime work panicked; settling as failed");
    }

    result.ok()
}

fn route_prompt(request: &InferenceRequest) -> RoutePrompt<'_> {
    if let Some(decision) = &request.decision {
        return RoutePrompt::DecisionState(&decision.state);
    }

    match request.encoded_input_ids.as_deref() {
        Some(ids) => RoutePrompt::TokenIds(ids),
        None => RoutePrompt::ChatMessages(&request.messages),
    }
}

pub enum CompletionResponse {
    NonStreaming {
        result: CompletionResult,
        service_tier: ServiceTier,
    },
    Streaming {
        result: StreamingCompletion,
        service_tier: ServiceTier,
    },
}

pub struct StreamingCompletion {
    receiver: mpsc::Receiver<StreamItem>,
}

impl StreamingCompletion {
    pub fn into_stream(self) -> impl futures_util::Stream<Item = StreamItem> + Send {
        stream_util::unfold(self.receiver, |mut receiver| async move {
            receiver.recv().await.map(|item| (item, receiver))
        })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CompletionResult {
    response: Value,
}

impl CompletionResult {
    pub fn into_response(self) -> Value {
        self.response
    }
}

/// An admitted generation. It holds an admission lease, so it must end in
/// exactly one settlement, whichever way it ends.
struct Generation {
    request: QualifiedRequest,
    route: Route,
    generation_identity: GenerationIdentity,
    lease: AdmissionLease,
    serving_state: Arc<dyn ServingState>,
    runtime: Arc<dyn ModelRuntime>,
    metrics: AdmittedGenerationMetrics,
}

impl Generation {
    fn id(&self) -> Uuid {
        self.request.metadata.generation_id
    }

    fn start(self) -> (RuntimeCall, GenerationSettlement) {
        let QualifiedRequest {
            metadata,
            request,
            effective_output_tokens,
            pricing,
            ..
        } = self.request;
        let started_at = cmp::max(Utc::now(), metadata.received_at);

        let call = RuntimeCall {
            runtime: self.runtime,
            generation_id: metadata.generation_id,
            request,
            effective_output_tokens,
            deadline: self.lease.request_deadline(),
            deployment: self.route.primary,
            fallbacks: self.route.fallbacks,
            attempts: 0,
        };

        let settlement = GenerationSettlement {
            serving_state: self.serving_state,
            generation_id: metadata.generation_id,
            generation_identity: self.generation_identity,
            pricing,
            service_tier: call.request.service_tier,
            received_at: metadata.received_at,
            started_at,
            streamed: call.request.stream,
            metrics: self.metrics,
        };

        for fallback in &call.fallbacks {
            settlement.metrics.prepare_deployment(fallback.id);
        }

        (call, settlement)
    }

    async fn complete(
        self,
        mut cancellation: oneshot::Receiver<()>,
        mut shutdown: watch::Receiver<bool>,
    ) -> Result<CompletionResult, GatewayError> {
        let (mut call, mut settlement) = self.start();

        let dispatched = tokio::select! {
            result = call.complete() => result,
            _ = &mut cancellation => Err(FailedGeneration::cancelled(CancellationOwner::Client)),
            _ = force_shutdown_requested(&mut shutdown) => Err(FailedGeneration::cancelled(CancellationOwner::Server)),
        };
        settlement.metrics.served_by(call.deployment.id);

        let completion = match dispatched {
            Ok(completion) => completion,
            Err(failed) => return Err(settlement.settle_failure(failed).await),
        };

        let terminal = GenerationTerminal {
            end: GenerationEnd::finished(completion.finish_reason().to_owned(), call.generation_id),
            usage: completion.usage(),
            delivery: Delivery::Buffered,
        };
        let settled = settlement.settle(terminal).await?;

        match settled.end.public_error() {
            Some(error) => Err(error),
            None => {
                let mut response = completion.into_response();
                if call.request.decision.is_none() {
                    crate::protocol::set_usage_cost(&mut response, settled.charge_nano_usd);
                }

                Ok(CompletionResult { response })
            }
        }
    }

    async fn stream(
        self,
        started: oneshot::Sender<Result<(), GatewayError>>,
        events: mpsc::Sender<StreamItem>,
        mut shutdown: watch::Receiver<bool>,
    ) {
        let (mut call, mut settlement) = self.start();

        let mut attempt_started = Instant::now();
        let mut started = Some(started);
        let opened = {
            let opening = call.stream();
            tokio::pin!(opening);
            tokio::select! {
                result = &mut opening => result,
                _ = started.as_mut().expect("startup sender exists").closed() => Err(FailedGeneration::cancelled(CancellationOwner::Client)),
                _ = force_shutdown_requested(&mut shutdown) => Err(FailedGeneration::cancelled(CancellationOwner::Server)),
                _ = tokio::time::sleep(STREAM_STARTUP_GRACE) => {
                    // A runtime can withhold HTTP headers throughout prefill; let SSE keepalives start.
                    let sent = started.take().expect("startup sender exists").send(Ok(()));
                    if sent.is_err() {
                        Err(FailedGeneration::cancelled(CancellationOwner::Client))
                    } else {
                        tokio::select! {
                            result = opening => result,
                            _ = events.closed() => Err(FailedGeneration::cancelled(CancellationOwner::Client)),
                            _ = force_shutdown_requested(&mut shutdown) => Err(FailedGeneration::cancelled(CancellationOwner::Server)),
                        }
                    }
                }
            }
        };
        settlement.metrics.served_by(call.deployment.id);

        let mut runtime_stream = match opened {
            Ok(runtime_stream) => runtime_stream,
            Err(failed) => {
                let error = settlement.settle_failure(failed).await;
                if let Some(started) = started {
                    let _ = started.send(Err(error));
                } else {
                    let _ = events.send(StreamItem::Error(error)).await;
                }
                return;
            }
        };

        if let Some(started) = started {
            if started.send(Ok(())).is_err() {
                drop(runtime_stream);
                settlement
                    .settle_failure(FailedGeneration::cancelled(CancellationOwner::Client))
                    .await;
                return;
            }
        }

        let mut progress = StreamProgress::new();
        let stop = loop {
            let relay = progress.relay(&mut runtime_stream, &events, &mut shutdown, call.deadline);
            let stop = unless_panicked(call.generation_id, relay)
                .await
                .unwrap_or(StreamStop::Panicked);
            let retry = match &stop {
                StreamStop::RuntimeFailed(failure)
                    if failure.kind() == crate::RuntimeFailureKind::CapacityExceeded
                        && progress.can_retry_before_any_frame() =>
                {
                    call.retry_stream_target(failure, attempt_started)
                }
                _ => false,
            };
            if !retry {
                break stop;
            }

            drop(runtime_stream);
            attempt_started = Instant::now();
            let reopened = tokio::select! {
                result = call.stream() => result,
                _ = events.closed() => Err(FailedGeneration::cancelled(CancellationOwner::Client)),
                _ = force_shutdown_requested(&mut shutdown) => Err(FailedGeneration::cancelled(CancellationOwner::Server)),
            };
            settlement.metrics.served_by(call.deployment.id);
            match reopened {
                Ok(stream) => {
                    runtime_stream = stream;
                    progress = StreamProgress::new();
                }
                Err(failed) => {
                    let error = settlement.settle_failure(failed).await;
                    let _ = events.send(StreamItem::Error(error)).await;
                    return;
                }
            }
        };
        stop.warn_if_abnormal(&call, &progress, settlement.started_at);
        drop(runtime_stream);

        let client_gone = matches!(stop, StreamStop::ClientGone);
        let terminal_response = progress.terminal_response.take();
        let settled = settlement.settle(progress.into_terminal(stop)).await;
        if client_gone {
            return;
        }

        let last = match settled {
            Ok(settled) => match settled.end.public_error() {
                Some(error) => StreamItem::Error(error),
                None => {
                    if let Some(mut response) = terminal_response {
                        crate::protocol::set_usage_cost(&mut response, settled.charge_nano_usd);
                        if events.send(StreamItem::Chunk(response)).await.is_err() {
                            return;
                        }
                    }

                    StreamItem::Done
                }
            },
            Err(error) => StreamItem::Error(error),
        };
        let _ = events.send(last).await;
    }
}

#[cfg(test)]
#[path = "completion_tests/mod.rs"]
mod tests;
