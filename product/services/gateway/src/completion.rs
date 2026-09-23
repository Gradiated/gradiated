use std::{
    cmp,
    future::Future,
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};

use chrono::{DateTime, Utc};
use futures_util::stream;
use serde_json::Value;
use tokio::{
    sync::{mpsc, oneshot, watch, Notify},
    task::JoinHandle,
};
use tracing::Instrument;
use uuid::Uuid;

use crate::{
    metrics::{AdmittedGenerationMetrics, TerminalRecord},
    protocol::StreamItem,
    routing::{order_deployments_diagnosed, RoutePrompt},
    AdmissionLease, BoundedRequest, CancellationOwner, CapturedPricing, FinalizationOutcome,
    GatewayConfig, GatewayError, GatewayMetrics, GatewayModelDeployment, GenerationIdentity,
    GenerationProperties, GenerationStatus, GenerationTiming, InferenceRequest, ModelRuntime,
    ModelTokenizer, NormalizedUsage, PricedUsage, QualifiedRequest, RouteAvailability, RouteInput,
    RoutedDeployment, RuntimeCompletion, RuntimeEventStream, RuntimeFailure, RuntimeFailureKind,
    RuntimeStreamChunk, RuntimeStreamEvent, ServiceTier, ServingState, TerminalOutcome,
};

const FINALIZATION_ATTEMPTS: usize = 3;
const FINALIZATION_RETRY_DELAY: Duration = Duration::from_millis(25);
const STREAM_CHANNEL_CAPACITY: usize = 8;

#[derive(Clone)]
struct GenerationTasks {
    inner: Arc<GenerationTasksInner>,
}

struct GenerationTasksInner {
    draining: AtomicBool,
    force_shutdown: watch::Sender<bool>,
    active: AtomicUsize,
    idle: Notify,
}

impl GenerationTasks {
    fn new() -> Self {
        let (force_shutdown, _) = watch::channel(false);

        Self {
            inner: Arc::new(GenerationTasksInner {
                draining: AtomicBool::new(false),
                force_shutdown,
                active: AtomicUsize::new(0),
                idle: Notify::new(),
            }),
        }
    }

    fn spawn<F>(&self, future: F) -> JoinHandle<F::Output>
    where
        F: Future + Send + 'static,
        F::Output: Send + 'static,
    {
        self.inner.active.fetch_add(1, Ordering::AcqRel);
        let inner = self.inner.clone();

        tokio::spawn(
            async move {
                let _active = ActiveGeneration(inner);
                future.await
            }
            .in_current_span(),
        )
    }

    fn subscribe(&self) -> watch::Receiver<bool> {
        self.inner.force_shutdown.subscribe()
    }

    fn begin_draining(&self) {
        self.inner.draining.store(true, Ordering::Release);
    }

    fn is_draining(&self) -> bool {
        self.inner.draining.load(Ordering::Acquire)
    }

    fn force_shutdown(&self) {
        self.begin_draining();
        self.inner.force_shutdown.send_replace(true);
    }

    async fn wait(&self) {
        loop {
            let idle = self.inner.idle.notified();
            if self.inner.active.load(Ordering::Acquire) == 0 {
                return;
            }

            idle.await;
        }
    }
}

struct ActiveGeneration(Arc<GenerationTasksInner>);

impl Drop for ActiveGeneration {
    fn drop(&mut self) {
        if self.0.active.fetch_sub(1, Ordering::AcqRel) == 1 {
            self.0.idle.notify_waiters();
        }
    }
}

async fn force_shutdown_requested(force_shutdown: &mut watch::Receiver<bool>) {
    while !*force_shutdown.borrow() {
        if force_shutdown.changed().await.is_err() {
            std::future::pending::<()>().await;
        }
    }
}

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
        if self.tasks.is_draining() {
            return Err(GatewayError::RuntimeUnavailable);
        }

        let streaming = qualified.request.stream;
        let service_tier = qualified.request.service_tier;
        let mut bounded = self.bound(qualified).await?;
        let fallbacks = self.route(&mut bounded).await?;
        let generation = self.admit(bounded, fallbacks).await?;

        if streaming {
            let result = self.stream(generation).await?;
            Ok(CompletionResponse::Streaming {
                result,
                service_tier,
            })
        } else {
            let result = self.run(generation).await?;
            Ok(CompletionResponse::NonStreaming {
                result,
                service_tier,
            })
        }
    }

    pub async fn count_tokens(&self, qualified: &QualifiedRequest) -> Result<u64, GatewayError> {
        self.tokenizer.count(qualified).await
    }

    async fn bound(&self, qualified: QualifiedRequest) -> Result<BoundedRequest, GatewayError> {
        if qualified.deployment.release.sends_token_ids() {
            return self.tokenizer.enforce(qualified).await;
        }

        // Chat deployments own normalization, tokenization, and context
        // validation. Local rendering must not veto their requests.
        Ok(BoundedRequest {
            qualified,
            input_tokens: None,
        })
    }

    /// Selects the deployment to dispatch to and returns the remaining eligible
    /// candidates, in order, for a retry. The runtime owns admission: when it is
    /// full it rejects the request and the retry moves to the next candidate.
    async fn route(
        &self,
        bounded: &mut BoundedRequest,
    ) -> Result<Vec<RoutedDeployment>, GatewayError> {
        let request = &bounded.qualified;
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

        let (availability, diagnostics) = order_deployments_diagnosed(RouteInput {
            workspace_id: request.identity.workspace_id,
            model_id: &request.request.model,
            release_digest: &request.served_release_digest,
            session_id: request.request.session_id.as_deref(),
            prompt: route_prompt(&request.request),
            deployments: &request.model_deployments,
            statuses: &statuses,
            now: Utc::now(),
        });

        let unavailable = match availability {
            RouteAvailability::Ready(candidates) => {
                let mut candidates = candidates.into_iter();
                if let Some(active) = candidates.next() {
                    bounded.qualified.deployment = active.deployment;
                    return Ok(candidates.collect());
                }

                GatewayError::RuntimeUnavailable
            }
            RouteAvailability::AtCapacity => GatewayError::CapacityExceeded,
            RouteAvailability::Unavailable => GatewayError::RuntimeUnavailable,
        };

        crate::diagnostics::limited_warn!(generation_id = %request.metadata.generation_id,
            model_id = %request.request.model, phase = "routing",
            candidates = diagnostics.candidates,
            unavailable = diagnostics.unavailable,
            invalid_deployment = diagnostics.invalid_deployment,
            release_mismatch = diagnostics.release_mismatch,
            missing_status = diagnostics.missing_status,
            invalid_status = diagnostics.invalid_status,
            revision_mismatch = diagnostics.revision_mismatch,
            stale_status = diagnostics.stale_status,
            unhealthy = diagnostics.unhealthy,
            at_capacity = diagnostics.at_capacity,
            "no eligible runtime deployment");

        Err(unavailable)
    }

    async fn admit(
        &self,
        bounded: BoundedRequest,
        fallbacks: Vec<RoutedDeployment>,
    ) -> Result<Generation, GatewayError> {
        let request = &bounded.qualified;
        let generation_identity = GenerationIdentity::new(
            None,
            request.identity.organization_id,
            request.identity.workspace_id,
            request.identity.api_key_id,
            request.request.model.clone(),
            request.served_release_digest.clone(),
        )
        .map_err(|_| GatewayError::ServingStateUnavailable)?;

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

        let lease = match admission {
            Ok(lease) => lease,
            Err(error) => {
                self.metrics.record_admission_rejection(
                    &request.request.model,
                    request.deployment.id,
                    request.deployment.release.protocol_label(),
                    request.request.stream,
                    request.request.service_tier,
                    &error,
                );
                return Err(error.into());
            }
        };

        let metrics = self.metrics.generation_admitted(
            &request.request.model,
            request.deployment.id,
            request.deployment.release.protocol_label(),
            request.request.stream,
            request.request.service_tier,
        );

        Ok(Generation {
            bounded,
            generation_identity,
            lease,
            serving_state: self.serving_state.clone(),
            runtime: self.runtime.clone(),
            metrics,
            fallbacks,
        })
    }

    /// Runs a buffered generation on its own task, so settlement completes even
    /// when the caller stops waiting.
    async fn run(&self, generation: Generation) -> Result<CompletionResult, GatewayError> {
        // The task reads a dropped sender as cancellation. The sender lives as
        // long as this future, so a caller that stops waiting cancels the work.
        let (_waiting, cancellation) = oneshot::channel();

        self.tasks
            .spawn(generation.complete(cancellation, self.tasks.subscribe()))
            .await
            .map_err(|_| GatewayError::FinalizationUnavailable)?
    }

    /// Opens a streaming generation and returns once the runtime has accepted it
    /// or the attempt has been settled as a failure.
    async fn stream(&self, generation: Generation) -> Result<StreamingCompletion, GatewayError> {
        let (events, receiver) = mpsc::channel(STREAM_CHANNEL_CAPACITY);
        let (started, startup) = oneshot::channel();

        self.tasks
            .spawn(generation.stream(started, events, self.tasks.subscribe()));

        startup
            .await
            .map_err(|_| GatewayError::FinalizationUnavailable)??;

        Ok(StreamingCompletion { receiver })
    }

    #[cfg(test)]
    async fn complete_bounded(
        &self,
        bounded: BoundedRequest,
    ) -> Result<CompletionResult, GatewayError> {
        let generation = self.admit(bounded, Vec::new()).await?;
        self.run(generation).await
    }

    #[cfg(test)]
    async fn stream_bounded(
        &self,
        bounded: BoundedRequest,
    ) -> Result<StreamingCompletion, GatewayError> {
        let generation = self.admit(bounded, Vec::new()).await?;
        self.stream(generation).await
    }
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
        stream::unfold(self.receiver, |mut receiver| async move {
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

/// An admitted generation. It holds the admission lease, so it must end in
/// exactly one settlement, whichever way it ends.
struct Generation {
    bounded: BoundedRequest,
    generation_identity: GenerationIdentity,
    lease: AdmissionLease,
    serving_state: Arc<dyn ServingState>,
    runtime: Arc<dyn ModelRuntime>,
    metrics: AdmittedGenerationMetrics,
    fallbacks: Vec<RoutedDeployment>,
}

impl Generation {
    fn start(self, streamed: bool) -> (RuntimeCall, GenerationSettlement) {
        let QualifiedRequest {
            metadata,
            identity,
            deployment,
            request,
            effective_output_tokens,
            pricing,
            ..
        } = self.bounded.qualified;
        let started_at = cmp::max(Utc::now(), metadata.received_at);

        let call = RuntimeCall {
            runtime: self.runtime,
            generation_id: metadata.generation_id,
            request,
            effective_output_tokens,
            deadline: self.lease.request_deadline(),
            deployment,
            fallbacks: self.fallbacks,
        };

        let settlement = GenerationSettlement {
            serving_state: self.serving_state,
            generation_id: metadata.generation_id,
            organization_id: identity.organization_id,
            generation_identity: self.generation_identity,
            pricing,
            service_tier: call.request.service_tier,
            received_at: metadata.received_at,
            started_at,
            streamed,
            metrics: self.metrics,
        };

        (call, settlement)
    }

    async fn complete(
        self,
        mut cancellation: oneshot::Receiver<()>,
        mut shutdown: watch::Receiver<bool>,
    ) -> Result<CompletionResult, GatewayError> {
        let (mut call, settlement) = self.start(false);

        let (usage, end, response) = tokio::select! {
            result = call.complete() => match result {
                Ok(completion) => (
                    completion.usage(),
                    GenerationEnd::Succeeded(completion.finish_reason().to_owned()),
                    Some(completion.into_response()),
                ),
                Err(failure) => (
                    failure.usage(),
                    GenerationEnd::from_runtime_failure(failure.kind()),
                    None,
                ),
            },
            _ = &mut cancellation => (
                NormalizedUsage::zero(),
                GenerationEnd::Cancelled(CancellationOwner::Client),
                None,
            ),
            _ = force_shutdown_requested(&mut shutdown) => (
                NormalizedUsage::zero(),
                GenerationEnd::Cancelled(CancellationOwner::Server),
                None,
            ),
        };

        let end = settlement
            .settle(None, usage, response.is_some(), end)
            .await?;

        if let Some(error) = end.public_error() {
            return Err(error);
        }

        response
            .map(|response| CompletionResult { response })
            .ok_or(GatewayError::RuntimeUnavailable)
    }

    async fn stream(
        self,
        started: oneshot::Sender<Result<(), GatewayError>>,
        events: mpsc::Sender<StreamItem>,
        mut shutdown: watch::Receiver<bool>,
    ) {
        let (mut call, settlement) = self.start(true);

        let opened = tokio::select! {
            result = call.stream() => Some(result),
            _ = force_shutdown_requested(&mut shutdown) => None,
        };

        let mut runtime_stream = match opened {
            Some(Ok(runtime_stream)) => runtime_stream,
            Some(Err(failure)) => {
                let end = GenerationEnd::from_runtime_failure(failure.kind());
                let error = settlement
                    .settle(None, failure.usage(), false, end)
                    .await
                    .map_or_else(|error| error, |_| failure.gateway_error());
                let _ = started.send(Err(error));
                return;
            }
            None => {
                let end = GenerationEnd::Cancelled(CancellationOwner::Server);
                let error = settlement
                    .settle(None, NormalizedUsage::zero(), false, end)
                    .await
                    .map_or_else(|error| error, |_| GatewayError::RuntimeUnavailable);
                let _ = started.send(Err(error));
                return;
            }
        };

        if started.send(Ok(())).is_err() {
            let end = GenerationEnd::Cancelled(CancellationOwner::Client);
            let _ = settlement
                .settle(None, NormalizedUsage::zero(), false, end)
                .await;
            return;
        }

        let deadline = tokio::time::sleep_until(tokio_instant(call.deadline));
        tokio::pin!(deadline);
        let mut progress = StreamProgress::new();

        let stop = loop {
            let event = tokio::select! {
                _ = events.closed() => break StreamStop::ClientGone,
                _ = &mut deadline => break StreamStop::Deadline,
                _ = force_shutdown_requested(&mut shutdown) => break StreamStop::Shutdown,
                event = runtime_stream.next_event() => event,
            };

            let chunk = match event {
                Ok(Some(RuntimeStreamEvent::Chunk(chunk))) => chunk,
                Ok(Some(RuntimeStreamEvent::Done)) => break progress.finish(),
                Ok(None) => break StreamStop::Incomplete,
                Err(failure) => {
                    progress.observe_failure(&failure);
                    break StreamStop::RuntimeFailed(failure);
                }
            };

            if let Err(stop) = progress.observe(&chunk) {
                break stop;
            }

            let usable_output = chunk.has_usable_output();
            let delivery = tokio::select! {
                result = events.send(StreamItem::Chunk(chunk.into_response())) => {
                    result.map_err(|_| StreamStop::ClientGone)
                }
                _ = &mut deadline => Err(StreamStop::Deadline),
                _ = force_shutdown_requested(&mut shutdown) => Err(StreamStop::Shutdown),
            };
            if let Err(stop) = delivery {
                break stop;
            }

            progress.delivered(usable_output);
        };

        if stop.is_abnormal() {
            let failure = stop.failure();
            crate::diagnostics::limited_warn!(generation_id = %call.generation_id,
                model_id = %call.request.model, deployment_id = %call.deployment.id,
                phase = "stream", reason = stop.reason(),
                failure_kind = ?failure.map(RuntimeFailure::kind),
                transport = failure.and_then(RuntimeFailure::transport_code),
                usable_output_delivered = progress.usable_output_delivered,
                elapsed_ms = (Utc::now() - settlement.started_at).num_milliseconds().max(0),
                "generation stream terminated abnormally");
        }
        drop(runtime_stream);

        let end = stop.into_end();
        let client_gone = matches!(end, GenerationEnd::Cancelled(CancellationOwner::Client));
        let settled = settlement
            .settle(
                progress.first_token_at,
                progress.usage,
                progress.usable_output_delivered,
                end,
            )
            .await;

        if client_gone {
            return;
        }

        let last = match settled {
            Ok(end) => end
                .public_error()
                .map_or(StreamItem::Done, StreamItem::Error),
            Err(error) => StreamItem::Error(error),
        };
        let _ = events.send(last).await;
    }
}

fn tokio_instant(deadline: DateTime<Utc>) -> tokio::time::Instant {
    let remaining = deadline
        .signed_duration_since(Utc::now())
        .to_std()
        .unwrap_or_default();

    tokio::time::Instant::now() + remaining
}

/// One dispatch to the runtime, with at most one retry on another candidate.
struct RuntimeCall {
    runtime: Arc<dyn ModelRuntime>,
    generation_id: Uuid,
    request: InferenceRequest,
    effective_output_tokens: u64,
    deadline: DateTime<Utc>,
    deployment: GatewayModelDeployment,
    fallbacks: Vec<RoutedDeployment>,
}

impl RuntimeCall {
    async fn complete(&mut self) -> Result<RuntimeCompletion, RuntimeFailure> {
        let mut attempt = 1;
        loop {
            let started = Instant::now();
            let result = self
                .runtime
                .complete(
                    &self.deployment,
                    self.request.clone(),
                    self.effective_output_tokens,
                    self.deadline,
                )
                .await;

            match result {
                Ok(completion) => return Ok(completion),
                Err(failure) if self.retry(&failure, attempt, started) => attempt += 1,
                Err(failure) => return Err(failure),
            }
        }
    }

    async fn stream(&mut self) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let mut attempt = 1;
        loop {
            let started = Instant::now();
            let result = self
                .runtime
                .stream(
                    &self.deployment,
                    self.request.clone(),
                    self.effective_output_tokens,
                    self.deadline,
                )
                .await;

            match result {
                Ok(runtime_stream) => return Ok(runtime_stream),
                Err(failure) if self.retry(&failure, attempt, started) => attempt += 1,
                Err(failure) => return Err(failure),
            }
        }
    }

    /// Logs the failed attempt and, when a retry is allowed, moves to the next
    /// candidate. Only a first attempt that the runtime rejected before doing any
    /// work may retry, so no generation is ever run twice.
    fn retry(&mut self, failure: &RuntimeFailure, attempt: u8, started: Instant) -> bool {
        let retryable = attempt == 1
            && failure.usage() == NormalizedUsage::zero()
            && matches!(
                failure.kind(),
                RuntimeFailureKind::Unavailable | RuntimeFailureKind::CapacityExceeded
            );
        let next = retryable
            .then(|| self.take_fallback(failure.kind()))
            .flatten();

        failure.log_attempt(
            self.generation_id,
            &self.request.model,
            self.deployment.id,
            attempt,
            started.elapsed().as_millis() as u64,
            next.is_some(),
        );

        match next {
            Some(next) => {
                self.deployment = next;
                true
            }
            None => false,
        }
    }

    /// Prefers a candidate in another fault domain and, when the runtime was
    /// unavailable rather than full, one from another provider.
    fn take_fallback(&mut self, failure: RuntimeFailureKind) -> Option<GatewayModelDeployment> {
        let prior = &self.deployment;
        let (index, _) = self
            .fallbacks
            .iter()
            .enumerate()
            .min_by_key(|(_, candidate)| {
                let same_fault_domain = candidate.deployment.fault_domain == prior.fault_domain;
                let same_provider = candidate.deployment.provider == prior.provider;
                (
                    same_fault_domain,
                    failure == RuntimeFailureKind::Unavailable && same_provider,
                )
            })?;

        Some(self.fallbacks.remove(index).deployment)
    }
}

/// What a stream has delivered so far, and therefore what settlement records.
struct StreamProgress {
    usage: NormalizedUsage,
    finish_reason: Option<String>,
    terminal_usage_seen: bool,
    usable_output_delivered: bool,
    first_token_at: Option<DateTime<Utc>>,
}

impl StreamProgress {
    fn new() -> Self {
        Self {
            usage: NormalizedUsage::zero(),
            finish_reason: None,
            terminal_usage_seen: false,
            usable_output_delivered: false,
            first_token_at: None,
        }
    }

    /// Records a chunk's counters. Usage that moves backwards is a runtime fault,
    /// because billing takes the last value the runtime reported.
    fn observe(&mut self, chunk: &RuntimeStreamChunk) -> Result<(), StreamStop> {
        if let Some(usage) = chunk.usage() {
            if !usage_is_monotonic(self.usage, usage) {
                return Err(StreamStop::InvalidUsage);
            }

            self.usage = usage;
        }

        if let Some(reason) = chunk.finish_reason() {
            self.finish_reason = Some(reason.to_owned());
        }
        self.terminal_usage_seen |= chunk.is_terminal_usage();

        Ok(())
    }

    /// A failure can still report usage the runtime consumed before it failed.
    fn observe_failure(&mut self, failure: &RuntimeFailure) {
        let usage = failure.usage();
        if usage != NormalizedUsage::zero() && usage_is_monotonic(self.usage, usage) {
            self.usage = usage;
        }
    }

    fn delivered(&mut self, usable_output: bool) {
        if usable_output {
            self.usable_output_delivered = true;
            self.first_token_at.get_or_insert_with(Utc::now);
        }
    }

    /// A stream succeeds only if the runtime reported a finish reason and
    /// terminal usage before it signalled the end.
    fn finish(&mut self) -> StreamStop {
        match self.finish_reason.take() {
            Some(reason) if self.terminal_usage_seen => StreamStop::Finished(reason),
            _ => StreamStop::Incomplete,
        }
    }
}

enum StreamStop {
    Finished(String),
    ClientGone,
    Deadline,
    Shutdown,
    InvalidUsage,
    Incomplete,
    RuntimeFailed(RuntimeFailure),
}

impl StreamStop {
    fn is_abnormal(&self) -> bool {
        !matches!(self, Self::Finished(_) | Self::ClientGone)
    }

    fn reason(&self) -> &'static str {
        match self {
            Self::Finished(_) => "finished",
            Self::ClientGone => "client_disconnect",
            Self::Deadline => "deadline",
            Self::Shutdown => "shutdown",
            Self::InvalidUsage => "invalid_usage",
            Self::Incomplete => "incomplete_stream",
            Self::RuntimeFailed(_) => "runtime_failure",
        }
    }

    fn failure(&self) -> Option<&RuntimeFailure> {
        match self {
            Self::RuntimeFailed(failure) => Some(failure),
            _ => None,
        }
    }

    fn into_end(self) -> GenerationEnd {
        match self {
            Self::Finished(reason) => GenerationEnd::Succeeded(reason),
            Self::ClientGone => GenerationEnd::Cancelled(CancellationOwner::Client),
            Self::Deadline | Self::Shutdown => GenerationEnd::Cancelled(CancellationOwner::Server),
            Self::InvalidUsage | Self::Incomplete => {
                GenerationEnd::Failed(GatewayError::RuntimeUnavailable)
            }
            Self::RuntimeFailed(failure) => GenerationEnd::from_runtime_failure(failure.kind()),
        }
    }
}

#[derive(Clone)]
enum GenerationEnd {
    Succeeded(String),
    Failed(GatewayError),
    Cancelled(CancellationOwner),
}

impl GenerationEnd {
    fn from_runtime_failure(kind: RuntimeFailureKind) -> Self {
        if kind == RuntimeFailureKind::TimedOut {
            Self::Cancelled(CancellationOwner::Server)
        } else {
            Self::Failed(RuntimeFailure::new(kind).gateway_error())
        }
    }

    fn public_error(&self) -> Option<GatewayError> {
        match self {
            Self::Succeeded(_) => None,
            Self::Failed(error) => Some(error.clone()),
            Self::Cancelled(_) => Some(GatewayError::RuntimeUnavailable),
        }
    }

    fn error_code(&self) -> Option<&'static str> {
        match self {
            Self::Succeeded(_) => None,
            Self::Failed(error) => Some(error.code()),
            Self::Cancelled(_) => Some(GatewayError::RuntimeUnavailable.code()),
        }
    }

    fn outcome(&self, usable_output_delivered: bool) -> Result<TerminalOutcome, GatewayError> {
        let (status, finish_reason, cancellation_owner) = match self {
            Self::Succeeded(reason) => (GenerationStatus::Succeeded, Some(reason.clone()), None),
            Self::Failed(_) => (GenerationStatus::Failed, None, None),
            Self::Cancelled(owner) => (GenerationStatus::Cancelled, None, Some(*owner)),
        };

        TerminalOutcome::new(
            status,
            finish_reason,
            self.error_code().map(str::to_owned),
            usable_output_delivered,
            cancellation_owner,
        )
        .map_err(|_| GatewayError::RuntimeUnavailable)
    }

    /// Status, error code and cancellation owner, as metric labels.
    fn metric_labels(&self) -> (&'static str, &'static str, &'static str) {
        let error_code = self.error_code().unwrap_or("none");

        match self {
            Self::Succeeded(_) => ("succeeded", error_code, "none"),
            Self::Failed(_) => ("failed", error_code, "none"),
            Self::Cancelled(owner) => ("cancelled", error_code, owner.as_str()),
        }
    }
}

struct GenerationSettlement {
    serving_state: Arc<dyn ServingState>,
    generation_id: Uuid,
    organization_id: Uuid,
    generation_identity: GenerationIdentity,
    pricing: CapturedPricing,
    service_tier: ServiceTier,
    received_at: DateTime<Utc>,
    started_at: DateTime<Utc>,
    streamed: bool,
    metrics: AdmittedGenerationMetrics,
}

impl GenerationSettlement {
    /// Charges the usage, records the terminal event and releases the lease.
    /// Returns the end that was recorded, which is a failure if the usage
    /// could not be priced.
    async fn settle(
        self,
        first_token_at: Option<DateTime<Utc>>,
        usage: NormalizedUsage,
        usable_output_delivered: bool,
        mut end: GenerationEnd,
    ) -> Result<GenerationEnd, GatewayError> {
        let priced_usage = match PricedUsage::calculate(&self.pricing, usage) {
            Ok(priced_usage) => priced_usage,
            Err(_) => {
                end = GenerationEnd::Failed(GatewayError::RuntimeUnavailable);
                PricedUsage::zero(&self.pricing)
            }
        };

        let outcome = end.outcome(usable_output_delivered)?;
        let completed_at = cmp::max(Utc::now(), self.started_at);
        let timing = GenerationTiming::new(
            self.received_at,
            Some(self.started_at),
            first_token_at,
            completed_at,
        )
        .map_err(|_| GatewayError::RuntimeUnavailable)?;

        let (status, error_code, cancellation_owner) = end.metric_labels();
        self.metrics.record_terminal(&TerminalRecord {
            generation_id: self.generation_id,
            status,
            error: error_code,
            cancellation_owner,
            usage,
            charge_nano_usd: priced_usage.charge(),
            received_at: self.received_at,
            started_at: self.started_at,
            first_token_at,
            completed_at,
        });

        let properties = GenerationProperties::new(
            self.generation_identity,
            self.service_tier,
            self.streamed,
            priced_usage,
            outcome,
            timing,
        );
        finalize_with_retry(
            &self.serving_state,
            self.generation_id,
            self.organization_id,
            &properties,
            &self.metrics,
        )
        .await?;

        Ok(end)
    }
}

fn usage_is_monotonic(previous: NormalizedUsage, next: NormalizedUsage) -> bool {
    (previous == NormalizedUsage::zero() || previous.input_tokens() == next.input_tokens())
        && previous.cached_input_tokens() <= next.cached_input_tokens()
        && previous.cache_write_tokens() <= next.cache_write_tokens()
        && previous.output_tokens() <= next.output_tokens()
        && previous.reasoning_tokens() <= next.reasoning_tokens()
}

async fn finalize_with_retry(
    serving_state: &Arc<dyn ServingState>,
    generation_id: Uuid,
    organization_id: Uuid,
    properties: &GenerationProperties,
    metrics: &AdmittedGenerationMetrics,
) -> Result<(), GatewayError> {
    let mut last_error = None;
    for attempt in 0..FINALIZATION_ATTEMPTS {
        let result = serving_state
            .finalize(generation_id, organization_id, properties)
            .await;

        match result {
            Ok(FinalizationOutcome::Settled) => {
                metrics.record_finalization_attempt("settled");
                return Ok(());
            }
            Ok(FinalizationOutcome::AlreadyAbsent) => {
                metrics.record_finalization_attempt("already_absent");
                // The lease is the exactly-once token, so it being gone means either
                // this is a retry whose predecessor already settled, or the lease was
                // lost and nothing settled at all. On the first attempt it cannot be
                // our own retry: the charge was never applied and no terminal event
                // was appended, so the generation is invisible to billing and to
                // ClickHouse while the customer has its answer. That is silent lost
                // revenue and it must be loud.
                if attempt == 0 {
                    metrics.record_unsettled_generation();
                    crate::diagnostics::limited_error!(
                        %generation_id,
                        %organization_id,
                        charge_nano_usd = properties.charge(),
                        "generation lost its admission lease before settlement; \
                         the charge was not applied and no terminal event was appended"
                    );
                }
                return Ok(());
            }
            Err(error) => {
                metrics.record_finalization_attempt("error");
                last_error = Some(error);
            }
        }

        if attempt + 1 < FINALIZATION_ATTEMPTS {
            metrics.record_finalization_retry();
            tokio::time::sleep(FINALIZATION_RETRY_DELAY).await;
        }
    }

    metrics.record_finalization_failure();
    tracing::error!(%generation_id, %organization_id, phase = "finalization",
        attempts = FINALIZATION_ATTEMPTS,
        error_code = last_error.as_ref().map(|error| error.diagnostic_code()),
        "generation settlement retries exhausted");

    match last_error {
        Some(error) => Err(error.into()),
        None => Err(GatewayError::FinalizationUnavailable),
    }
}

#[cfg(test)]
#[path = "completion_tests.rs"]
mod tests;
