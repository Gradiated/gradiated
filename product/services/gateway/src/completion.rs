use std::{
    cmp,
    convert::Infallible,
    future::Future,
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc,
    },
    time::Duration,
};

use axum::{body::Bytes, http::HeaderMap, response::sse::Event};
use chrono::Utc;
use futures_util::stream;
use serde_json::Value;
use tokio::{
    sync::{mpsc, oneshot, watch, Notify},
    task::JoinHandle,
};
use uuid::Uuid;

use crate::{
    metrics::AdmittedGenerationMetrics, BoundedRequest, CancellationOwner, FinalizationOutcome,
    GatewayConfig, GatewayError, GatewayMetrics, GenerationIdentity, GenerationProperties,
    GenerationStatus, GenerationTiming, ModelRuntime, ModelTokenizer, NormalizedUsage, PricedUsage,
    RequestCoordinator, RequestMetadata, RuntimeFailure, RuntimeFailureKind, RuntimeStreamEvent,
    ServingState, TerminalOutcome,
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
        tokio::spawn(async move {
            let _active = ActiveGeneration(inner);
            future.await
        })
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
    coordinator: RequestCoordinator,
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
        let metrics = GatewayMetrics::new();
        Self {
            coordinator: RequestCoordinator::new(serving_state.clone()),
            tokenizer,
            serving_state,
            runtime,
            config,
            tasks: GenerationTasks::new(),
            metrics,
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
        metadata: RequestMetadata,
        headers: &HeaderMap,
        body: Bytes,
    ) -> Result<CompletionResponse, GatewayError> {
        if self.tasks.is_draining() {
            return Err(GatewayError::RuntimeUnavailable);
        }
        let qualified = self.coordinator.qualify(metadata, headers, &body).await?;
        drop(body);
        let streaming = qualified.request.stream;
        let bounded = self.tokenizer.enforce(qualified).await?;
        if streaming {
            self.stream_bounded(bounded)
                .await
                .map(CompletionResponse::Streaming)
        } else {
            self.complete_bounded(bounded)
                .await
                .map(CompletionResponse::NonStreaming)
        }
    }

    async fn complete_bounded(
        &self,
        bounded: BoundedRequest,
    ) -> Result<CompletionResult, GatewayError> {
        let generation_identity = GenerationIdentity::new(
            None,
            bounded.qualified.identity.organization_id,
            bounded.qualified.identity.workspace_id,
            bounded.qualified.identity.api_key_id,
            bounded.qualified.request.model.clone(),
            bounded.qualified.served_release_digest.clone(),
        )
        .map_err(|_| GatewayError::ServingStateUnavailable)?;
        let (lease, generation_metrics) = self.admit_generation(&bounded).await?;
        wait_for_generation(
            GenerationTask {
                bounded,
                generation_identity,
                lease,
                serving_state: self.serving_state.clone(),
                runtime: self.runtime.clone(),
                metrics: generation_metrics,
            },
            &self.tasks,
        )
        .await
    }

    async fn stream_bounded(
        &self,
        bounded: BoundedRequest,
    ) -> Result<StreamingCompletion, GatewayError> {
        let generation_identity = generation_identity(&bounded)?;
        let (lease, generation_metrics) = self.admit_generation(&bounded).await?;
        let (events, receiver) = mpsc::channel(STREAM_CHANNEL_CAPACITY);
        let (started, startup) = oneshot::channel();
        self.tasks.spawn(
            StreamingGenerationTask {
                bounded,
                generation_identity,
                lease,
                serving_state: self.serving_state.clone(),
                runtime: self.runtime.clone(),
                metrics: generation_metrics,
            }
            .run(started, events, self.tasks.subscribe()),
        );
        startup
            .await
            .map_err(|_| GatewayError::FinalizationUnavailable)??;
        Ok(StreamingCompletion { receiver })
    }

    async fn admit_generation(
        &self,
        bounded: &BoundedRequest,
    ) -> Result<(crate::AdmissionLease, AdmittedGenerationMetrics), GatewayError> {
        let request = &bounded.qualified;
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
                    request.request.stream,
                    &error,
                );
                return Err(error.into());
            }
        };
        let metrics = self.metrics.generation_admitted(
            &request.request.model,
            request.deployment.id,
            request.request.stream,
        );
        Ok((lease, metrics))
    }
}

fn generation_identity(bounded: &BoundedRequest) -> Result<GenerationIdentity, GatewayError> {
    GenerationIdentity::new(
        None,
        bounded.qualified.identity.organization_id,
        bounded.qualified.identity.workspace_id,
        bounded.qualified.identity.api_key_id,
        bounded.qualified.request.model.clone(),
        bounded.qualified.served_release_digest.clone(),
    )
    .map_err(|_| GatewayError::ServingStateUnavailable)
}

pub enum CompletionResponse {
    NonStreaming(CompletionResult),
    Streaming(StreamingCompletion),
}

pub struct StreamingCompletion {
    receiver: mpsc::Receiver<Event>,
}

impl StreamingCompletion {
    pub fn into_stream(self) -> impl futures_util::Stream<Item = Result<Event, Infallible>> + Send {
        stream::unfold(self.receiver, |mut receiver| async move {
            receiver.recv().await.map(|event| (Ok(event), receiver))
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

struct GenerationTask {
    bounded: BoundedRequest,
    generation_identity: GenerationIdentity,
    lease: crate::AdmissionLease,
    serving_state: Arc<dyn ServingState>,
    runtime: Arc<dyn ModelRuntime>,
    metrics: AdmittedGenerationMetrics,
}

impl GenerationTask {
    async fn run(
        self,
        mut cancellation: oneshot::Receiver<()>,
        mut shutdown: watch::Receiver<bool>,
    ) -> Result<CompletionResult, GatewayError> {
        let GenerationTask {
            bounded,
            generation_identity,
            lease,
            serving_state,
            runtime,
            metrics,
        } = self;
        let crate::QualifiedRequest {
            metadata,
            identity: authenticated_identity,
            deployment,
            request,
            effective_output_tokens,
            pricing,
            ..
        } = bounded.qualified;
        let generation_id = metadata.generation_id;
        let organization_id = authenticated_identity.organization_id;
        let received_at = metadata.received_at;
        let expected_input_tokens = bounded.input_tokens;
        let started_at = cmp::max(Utc::now(), received_at);
        let settlement = GenerationSettlement {
            serving_state,
            generation_id,
            organization_id,
            generation_identity,
            pricing,
            received_at,
            started_at,
            streamed: false,
            metrics,
        };

        let (usage, terminal, response) = {
            let runtime = runtime.complete(
                &deployment,
                request,
                effective_output_tokens,
                lease.request_deadline(),
            );
            tokio::pin!(runtime);

            tokio::select! {
                result = &mut runtime => match result.and_then(|completion| {
                    if completion.usage().input_tokens() == expected_input_tokens {
                        Ok(completion)
                    } else {
                        Err(RuntimeFailure::with_usage(
                            RuntimeFailureKind::ProtocolViolation,
                            completion.usage(),
                        ))
                    }
                }) {
                    Ok(completion) => {
                        let usage = completion.usage();
                        (
                            usage,
                            GenerationEnd::Succeeded(completion.finish_reason().to_owned()),
                            Some(completion.into_response()),
                        )
                    }
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
            }
        };
        let usable_output_delivered = response.is_some();
        let terminal = settlement
            .settle(None, usage, usable_output_delivered, terminal)
            .await?;
        match (response, terminal.public_error()) {
            (Some(response), None) => Ok(CompletionResult { response }),
            (_, Some(error)) => Err(error),
            _ => Err(GatewayError::RuntimeUnavailable),
        }
    }
}

struct StreamingGenerationTask {
    bounded: BoundedRequest,
    generation_identity: GenerationIdentity,
    lease: crate::AdmissionLease,
    serving_state: Arc<dyn ServingState>,
    runtime: Arc<dyn ModelRuntime>,
    metrics: AdmittedGenerationMetrics,
}

impl StreamingGenerationTask {
    async fn run(
        self,
        started: oneshot::Sender<Result<(), GatewayError>>,
        events: mpsc::Sender<Event>,
        mut shutdown: watch::Receiver<bool>,
    ) {
        let StreamingGenerationTask {
            bounded,
            generation_identity,
            lease,
            serving_state,
            runtime,
            metrics,
        } = self;
        let crate::QualifiedRequest {
            metadata,
            identity,
            deployment,
            request,
            effective_output_tokens,
            pricing,
            ..
        } = bounded.qualified;
        let generation_id = metadata.generation_id;
        let received_at = metadata.received_at;
        let expected_input_tokens = bounded.input_tokens;
        let started_at = cmp::max(Utc::now(), received_at);
        let settlement = GenerationSettlement {
            serving_state,
            generation_id,
            organization_id: identity.organization_id,
            generation_identity,
            pricing,
            received_at,
            started_at,
            streamed: true,
            metrics,
        };
        let runtime_stream = tokio::select! {
            result = runtime.stream(
                &deployment,
                request,
                effective_output_tokens,
                lease.request_deadline(),
            ) => result,
            _ = force_shutdown_requested(&mut shutdown) => {
                let result = settlement
                    .settle(
                        None,
                        NormalizedUsage::zero(),
                        false,
                        GenerationEnd::Cancelled(CancellationOwner::Server),
                    )
                    .await
                    .map(|_| GatewayError::RuntimeUnavailable)
                    .unwrap_or_else(|error| error);
                let _ = started.send(Err(result));
                return;
            }
        };

        let mut runtime_stream = match runtime_stream {
            Ok(runtime_stream) => runtime_stream,
            Err(failure) => {
                let public_error = failure.gateway_error();
                let usage = failure.usage();
                let result = settlement
                    .settle(
                        None,
                        usage,
                        false,
                        GenerationEnd::from_runtime_failure(failure.kind()),
                    )
                    .await
                    .map(|_| public_error);
                let _ = started.send(Err(result.unwrap_or_else(|error| error)));
                return;
            }
        };

        if started.send(Ok(())).is_err() {
            let _ = settlement
                .settle(
                    None,
                    NormalizedUsage::zero(),
                    false,
                    GenerationEnd::Cancelled(CancellationOwner::Client),
                )
                .await;
            return;
        }

        let mut latest_usage = NormalizedUsage::zero();
        let mut finish_reason = None;
        let mut terminal_usage_seen = false;
        let mut usable_output_delivered = false;
        let mut first_token_at = None;
        let deadline = tokio::time::sleep_until(tokio::time::Instant::from_std(
            std::time::Instant::now()
                + lease
                    .request_deadline()
                    .signed_duration_since(Utc::now())
                    .to_std()
                    .unwrap_or_default(),
        ));
        tokio::pin!(deadline);

        let terminal = loop {
            tokio::select! {
                _ = events.closed() => {
                    break GenerationEnd::Cancelled(CancellationOwner::Client);
                }
                _ = &mut deadline => {
                    break GenerationEnd::Cancelled(CancellationOwner::Server);
                }
                _ = force_shutdown_requested(&mut shutdown) => {
                    break GenerationEnd::Cancelled(CancellationOwner::Server);
                }
                event = runtime_stream.next_event() => {
                    match event {
                        Ok(Some(RuntimeStreamEvent::Chunk(chunk))) => {
                            if let Some(usage) = chunk.usage() {
                                if usage.input_tokens() != expected_input_tokens
                                    || !usage_is_monotonic(latest_usage, usage)
                                {
                                    break GenerationEnd::Failed(GatewayError::RuntimeUnavailable);
                                }
                                latest_usage = usage;
                            }
                            if let Some(reason) = chunk.finish_reason() {
                                finish_reason = Some(reason.to_owned());
                            }
                            terminal_usage_seen |= chunk.is_terminal_usage();
                            let usable_output = chunk.has_usable_output();
                            let event = sse_data(&chunk.into_response());
                            let delivery = tokio::select! {
                                result = events.send(event) => result
                                    .map_err(|_| CancellationOwner::Client),
                                _ = &mut deadline => Err(CancellationOwner::Server),
                                _ = force_shutdown_requested(&mut shutdown) => {
                                    Err(CancellationOwner::Server)
                                },
                            };
                            if let Err(owner) = delivery {
                                break GenerationEnd::Cancelled(owner);
                            }
                            if usable_output {
                                usable_output_delivered = true;
                                first_token_at.get_or_insert_with(Utc::now);
                            }
                        }
                        Ok(Some(RuntimeStreamEvent::Done))
                            if terminal_usage_seen && finish_reason.is_some() =>
                        {
                            break GenerationEnd::Succeeded(
                                finish_reason.expect("checked finish reason"),
                            );
                        }
                        Ok(Some(RuntimeStreamEvent::Done) | None) => {
                            break GenerationEnd::Failed(GatewayError::RuntimeUnavailable);
                        }
                        Err(failure) => {
                            let failure_usage = failure.usage();
                            if failure_usage != NormalizedUsage::zero()
                                && failure_usage.input_tokens() == expected_input_tokens
                                && usage_is_monotonic(latest_usage, failure_usage)
                            {
                                latest_usage = failure_usage;
                            }
                            break GenerationEnd::from_runtime_failure(failure.kind());
                        }
                    }
                }
            }
        };
        drop(runtime_stream);

        let client_cancelled = matches!(
            terminal,
            GenerationEnd::Cancelled(CancellationOwner::Client)
        );
        let settlement = settlement
            .settle(
                first_token_at,
                latest_usage,
                usable_output_delivered,
                terminal,
            )
            .await;
        if client_cancelled {
            return;
        }
        match settlement {
            Ok(GenerationEnd::Succeeded(_)) => {
                let _ = events.send(Event::default().data("[DONE]")).await;
            }
            Ok(terminal) => {
                if let Some(error) = terminal.public_error() {
                    let _ = events.send(error.sse_event()).await;
                }
            }
            Err(error) => {
                let _ = events.send(error.sse_event()).await;
            }
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
}

struct GenerationSettlement {
    serving_state: Arc<dyn ServingState>,
    generation_id: Uuid,
    organization_id: Uuid,
    generation_identity: GenerationIdentity,
    pricing: crate::CapturedPricing,
    received_at: chrono::DateTime<Utc>,
    started_at: chrono::DateTime<Utc>,
    streamed: bool,
    metrics: AdmittedGenerationMetrics,
}

impl GenerationSettlement {
    async fn settle(
        self,
        first_token_at: Option<chrono::DateTime<Utc>>,
        usage: NormalizedUsage,
        usable_output_delivered: bool,
        mut terminal: GenerationEnd,
    ) -> Result<GenerationEnd, GatewayError> {
        let priced_usage = match PricedUsage::calculate(&self.pricing, usage) {
            Ok(priced_usage) => priced_usage,
            Err(_) => {
                terminal = GenerationEnd::Failed(GatewayError::RuntimeUnavailable);
                PricedUsage::zero(&self.pricing)
            }
        };
        let (metric_status, metric_error, metric_cancellation_owner) = match &terminal {
            GenerationEnd::Succeeded(_) => ("succeeded", "none", "none"),
            GenerationEnd::Failed(error) => ("failed", error.code(), "none"),
            GenerationEnd::Cancelled(CancellationOwner::Client) => {
                ("cancelled", "runtime_unavailable", "client")
            }
            GenerationEnd::Cancelled(CancellationOwner::Server) => {
                ("cancelled", "runtime_unavailable", "server")
            }
            GenerationEnd::Cancelled(CancellationOwner::Runtime) => {
                ("cancelled", "runtime_unavailable", "runtime")
            }
        };
        let (status, finish_reason, error_code, cancellation_owner) = match &terminal {
            GenerationEnd::Succeeded(reason) => (
                GenerationStatus::Succeeded,
                Some(reason.clone()),
                None,
                None,
            ),
            GenerationEnd::Failed(error) => (
                GenerationStatus::Failed,
                None,
                Some(error.code().to_owned()),
                None,
            ),
            GenerationEnd::Cancelled(owner) => (
                GenerationStatus::Cancelled,
                None,
                Some(GatewayError::RuntimeUnavailable.code().to_owned()),
                Some(*owner),
            ),
        };
        let outcome = TerminalOutcome::new(
            status,
            finish_reason,
            error_code,
            usable_output_delivered,
            cancellation_owner,
        )
        .map_err(|_| GatewayError::RuntimeUnavailable)?;
        let completed_at = cmp::max(Utc::now(), self.started_at);
        let timing = GenerationTiming::new(
            self.received_at,
            Some(self.started_at),
            first_token_at,
            completed_at,
        )
        .map_err(|_| GatewayError::RuntimeUnavailable)?;
        self.metrics.record_terminal(
            metric_status,
            metric_error,
            metric_cancellation_owner,
            usage,
            priced_usage.charge(),
            self.received_at,
            self.started_at,
            first_token_at,
            completed_at,
        );
        let properties = GenerationProperties::new(
            self.generation_identity,
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
        Ok(terminal)
    }
}

fn usage_is_monotonic(previous: NormalizedUsage, next: NormalizedUsage) -> bool {
    (previous == NormalizedUsage::zero() || previous.input_tokens() == next.input_tokens())
        && previous.cached_input_tokens() <= next.cached_input_tokens()
        && previous.cache_write_tokens() <= next.cache_write_tokens()
        && previous.output_tokens() <= next.output_tokens()
        && previous.reasoning_tokens() <= next.reasoning_tokens()
}

fn sse_data(value: &Value) -> Event {
    Event::default()
        .json_data(value)
        .expect("normalized JSON values always serialize")
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
        match serving_state
            .finalize(generation_id, organization_id, properties)
            .await
        {
            Ok(FinalizationOutcome::Settled) => {
                metrics.record_finalization_attempt("settled");
                return Ok(());
            }
            Ok(FinalizationOutcome::AlreadyAbsent) => {
                metrics.record_finalization_attempt("already_absent");
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
    match last_error {
        Some(error) => Err(error.into()),
        None => Err(GatewayError::FinalizationUnavailable),
    }
}

async fn wait_for_generation(
    task: GenerationTask,
    tasks: &GenerationTasks,
) -> Result<CompletionResult, GatewayError> {
    let (cancel, cancellation) = oneshot::channel();
    let generation = tasks.spawn(task.run(cancellation, tasks.subscribe()));
    let mut cancellation = CancellationOnDrop(Some(cancel));
    let result = generation
        .await
        .map_err(|_| GatewayError::FinalizationUnavailable)?;
    cancellation.0 = None;
    result
}

struct CancellationOnDrop(Option<oneshot::Sender<()>>);

impl Drop for CancellationOnDrop {
    fn drop(&mut self) {
        if let Some(cancellation) = self.0.take() {
            let _ = cancellation.send(());
        }
    }
}

#[cfg(test)]
mod tests {
    use std::{
        collections::VecDeque,
        sync::{
            atomic::{AtomicBool, AtomicUsize, Ordering},
            Mutex,
        },
    };

    use async_trait::async_trait;
    use axum::{
        body::to_bytes,
        response::{sse::Sse, IntoResponse},
    };
    use chrono::{DateTime, TimeDelta, Utc};
    use serde_json::json;

    use super::*;
    use crate::{
        auth::AuthenticatedIdentity,
        domain::{GatewayAccount, GatewayCredential, GatewayWorkspace},
        serving_state::ServingStateError,
        AdmissionError, AdmissionLease, CapturedPricing, ChatCompletionRequest, DeploymentStatus,
        FinalizationError, GatewayModel, GatewayModelDeployment, InputTokenPrice,
        ModelDeploymentRelease, OutputTokenPrice, QualifiedRequest, RuntimeCompletion,
        RuntimeEventStream, RuntimeStreamChunk, TokenUnit,
    };

    struct FakeServingState {
        finalized: Mutex<Vec<Value>>,
        admitted: Arc<AtomicBool>,
        finalization_failures: AtomicUsize,
        finalization_attempts: AtomicUsize,
    }

    impl FakeServingState {
        fn new(finalization_failures: usize) -> Self {
            Self {
                finalized: Mutex::new(Vec::new()),
                admitted: Arc::new(AtomicBool::new(false)),
                finalization_failures: AtomicUsize::new(finalization_failures),
                finalization_attempts: AtomicUsize::new(0),
            }
        }
    }

    #[async_trait]
    impl ServingState for FakeServingState {
        async fn credential(
            &self,
            _digest_hex: &str,
        ) -> Result<Option<GatewayCredential>, ServingStateError> {
            Ok(None)
        }

        async fn workspace(
            &self,
            _workspace_id: Uuid,
        ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
            Ok(None)
        }

        async fn account(
            &self,
            _organization_id: Uuid,
        ) -> Result<Option<GatewayAccount>, ServingStateError> {
            Ok(None)
        }

        async fn model(&self, _model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
            Ok(None)
        }

        async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
            Ok(Vec::new())
        }

        async fn admit(
            &self,
            generation_id: Uuid,
            _organization_id: Uuid,
            received_at: DateTime<Utc>,
            admitted_at: DateTime<Utc>,
            config: &GatewayConfig,
        ) -> Result<AdmissionLease, AdmissionError> {
            self.admitted.store(true, Ordering::SeqCst);
            AdmissionLease::new(generation_id, received_at, admitted_at, config)
        }

        async fn finalize(
            &self,
            _generation_id: Uuid,
            _organization_id: Uuid,
            properties: &GenerationProperties,
        ) -> Result<FinalizationOutcome, FinalizationError> {
            self.finalization_attempts.fetch_add(1, Ordering::SeqCst);
            if self
                .finalization_failures
                .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |remaining| {
                    remaining.checked_sub(1)
                })
                .is_ok()
            {
                return Err(FinalizationError::UnknownScriptResult(99));
            }
            self.finalized
                .lock()
                .unwrap()
                .push(serde_json::to_value(properties).unwrap());
            Ok(FinalizationOutcome::Settled)
        }
    }

    #[derive(Clone)]
    struct FixedRuntime(Result<RuntimeCompletion, RuntimeFailure>);

    #[async_trait]
    impl ModelRuntime for FixedRuntime {
        async fn complete(
            &self,
            _deployment: &GatewayModelDeployment,
            _request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: DateTime<Utc>,
        ) -> Result<RuntimeCompletion, RuntimeFailure> {
            self.0.clone()
        }
    }

    struct PendingRuntime {
        started: Mutex<Option<oneshot::Sender<()>>>,
        dropped: Arc<AtomicBool>,
    }

    struct FixedEventStream {
        events: VecDeque<Result<RuntimeStreamEvent, RuntimeFailure>>,
    }

    #[async_trait]
    impl RuntimeEventStream for FixedEventStream {
        async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
            self.events.pop_front().transpose()
        }
    }

    struct StreamingRuntime {
        events: Mutex<Option<VecDeque<Result<RuntimeStreamEvent, RuntimeFailure>>>>,
    }

    struct PendingEventStream;

    #[async_trait]
    impl RuntimeEventStream for PendingEventStream {
        async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
            std::future::pending().await
        }
    }

    struct PendingStreamingRuntime;

    #[async_trait]
    impl ModelRuntime for PendingStreamingRuntime {
        async fn complete(
            &self,
            _deployment: &GatewayModelDeployment,
            _request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: DateTime<Utc>,
        ) -> Result<RuntimeCompletion, RuntimeFailure> {
            unreachable!("streaming tests do not call complete")
        }

        async fn stream(
            &self,
            _deployment: &GatewayModelDeployment,
            _request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: DateTime<Utc>,
        ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
            Ok(Box::new(PendingEventStream))
        }
    }

    #[async_trait]
    impl ModelRuntime for StreamingRuntime {
        async fn complete(
            &self,
            _deployment: &GatewayModelDeployment,
            _request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: DateTime<Utc>,
        ) -> Result<RuntimeCompletion, RuntimeFailure> {
            unreachable!("streaming tests do not call complete")
        }

        async fn stream(
            &self,
            _deployment: &GatewayModelDeployment,
            request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: DateTime<Utc>,
        ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
            assert!(request.stream);
            Ok(Box::new(FixedEventStream {
                events: self.events.lock().unwrap().take().unwrap(),
            }))
        }
    }

    struct AdmissionCheckingRuntime {
        admitted: Arc<AtomicBool>,
    }

    #[async_trait]
    impl ModelRuntime for AdmissionCheckingRuntime {
        async fn complete(
            &self,
            _deployment: &GatewayModelDeployment,
            _request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: DateTime<Utc>,
        ) -> Result<RuntimeCompletion, RuntimeFailure> {
            if !self.admitted.load(Ordering::SeqCst) {
                return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
            }
            Ok(successful_completion())
        }
    }

    #[async_trait]
    impl ModelRuntime for PendingRuntime {
        async fn complete(
            &self,
            _deployment: &GatewayModelDeployment,
            _request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: DateTime<Utc>,
        ) -> Result<RuntimeCompletion, RuntimeFailure> {
            struct DropNotice(Arc<AtomicBool>);

            impl Drop for DropNotice {
                fn drop(&mut self) {
                    self.0.store(true, Ordering::SeqCst);
                }
            }

            let _notice = DropNotice(self.dropped.clone());
            if let Some(started) = self.started.lock().unwrap().take() {
                let _ = started.send(());
            }
            std::future::pending().await
        }
    }

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
            valkey_iam_cache_name: None,
            valkey_iam_region: None,
            valkey_iam_user: None,
            sglang_api_key: None,
        }
    }

    fn bounded_request() -> BoundedRequest {
        let generation_id = Uuid::now_v7();
        let organization_id = Uuid::now_v7();
        let request = ChatCompletionRequest::parse(
            br#"{"model":"model-a","messages":[{"role":"user","content":"hello"}]}"#,
        )
        .unwrap();
        let qualified = QualifiedRequest {
            metadata: RequestMetadata {
                generation_id,
                received_at: Utc::now(),
            },
            identity: AuthenticatedIdentity {
                api_key_id: Uuid::now_v7(),
                organization_id,
                workspace_id: Uuid::now_v7(),
            },
            deployment: GatewayModelDeployment {
                id: Uuid::now_v7(),
                status: DeploymentStatus::Available,
                service_url: "http://127.0.0.1:30000".to_owned(),
                release: ModelDeploymentRelease {
                    schema_version: 1,
                    runtime_revision: "runtime".to_owned(),
                    model_path: "model-a".to_owned(),
                    model_revision: "model-revision".to_owned(),
                    tokenizer_path: "model-a".to_owned(),
                    tokenizer_revision: "tokenizer-revision".to_owned(),
                },
            },
            served_release_digest: format!("sha256:{}", "a".repeat(64)),
            max_context_tokens: 8_192,
            max_prompt_tokens: 7_168,
            effective_output_tokens: 1_024,
            pricing: CapturedPricing::new(
                &[
                    InputTokenPrice::Prompt {
                        unit: TokenUnit::Token,
                        cost: 2,
                    },
                    InputTokenPrice::CachedPrompt {
                        unit: TokenUnit::Token,
                        cost: 1,
                    },
                ],
                &[OutputTokenPrice::Completion {
                    unit: TokenUnit::Token,
                    cost: 3,
                }],
            )
            .unwrap(),
            request,
        };
        BoundedRequest {
            qualified,
            input_tokens: 10,
        }
    }

    fn task(state: Arc<FakeServingState>, runtime: Arc<dyn ModelRuntime>) -> GenerationTask {
        let bounded = bounded_request();
        let generation_identity = GenerationIdentity::new(
            None,
            bounded.qualified.identity.organization_id,
            bounded.qualified.identity.workspace_id,
            bounded.qualified.identity.api_key_id,
            bounded.qualified.request.model.clone(),
            bounded.qualified.served_release_digest.clone(),
        )
        .unwrap();
        let lease = AdmissionLease::new(
            bounded.qualified.metadata.generation_id,
            bounded.qualified.metadata.received_at,
            bounded.qualified.metadata.received_at + TimeDelta::milliseconds(1),
            &config(),
        )
        .unwrap();
        let metrics = GatewayMetrics::new().generation_admitted(
            &bounded.qualified.request.model,
            bounded.qualified.deployment.id,
            bounded.qualified.request.stream,
        );
        GenerationTask {
            bounded,
            generation_identity,
            lease,
            serving_state: state,
            runtime,
            metrics,
        }
    }

    fn successful_completion() -> RuntimeCompletion {
        RuntimeCompletion::from_normalized_parts(
            json!({"id": "chatcmpl-1"}),
            "stop".to_owned(),
            NormalizedUsage::new(10, 4, 0, 5, 0).unwrap(),
        )
    }

    fn running_shutdown() -> watch::Receiver<bool> {
        watch::channel(false).1
    }

    #[tokio::test]
    async fn successful_generation_is_finalized_before_its_response_is_returned() {
        let state = Arc::new(FakeServingState::new(0));
        let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
        let (_cancel, cancellation) = oneshot::channel();

        let result = task(state.clone(), runtime)
            .run(cancellation, running_shutdown())
            .await
            .unwrap();

        assert_eq!(result.response["id"], "chatcmpl-1");
        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized.len(), 1);
        assert_eq!(finalized[0]["status"], "succeeded");
        assert_eq!(finalized[0]["usage"]["charge"], 31);
        assert_eq!(finalized[0]["usage"]["input_tokens"], 10);
    }

    #[tokio::test]
    async fn completion_service_admits_before_dispatching_runtime_work() {
        let state = Arc::new(FakeServingState::new(0));
        let runtime = Arc::new(AdmissionCheckingRuntime {
            admitted: state.admitted.clone(),
        });
        let service = CompletionService::new(
            state.clone(),
            runtime,
            ModelTokenizer::new().unwrap(),
            Arc::new(config()),
        );

        let result = service.complete_bounded(bounded_request()).await.unwrap();

        assert_eq!(result.response["id"], "chatcmpl-1");
        assert!(state.admitted.load(Ordering::SeqCst));
        assert_eq!(state.finalized.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn overload_is_finalized_before_the_public_error_is_returned() {
        let state = Arc::new(FakeServingState::new(0));
        let runtime = Arc::new(FixedRuntime(Err(RuntimeFailure::new(
            RuntimeFailureKind::CapacityExceeded,
        ))));
        let (_cancel, cancellation) = oneshot::channel();

        let result = task(state.clone(), runtime)
            .run(cancellation, running_shutdown())
            .await;

        assert_eq!(result, Err(GatewayError::CapacityExceeded));
        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized[0]["status"], "failed");
        assert_eq!(finalized[0]["usage"]["charge"], 0);
        assert_eq!(finalized[0]["outcome"]["error_code"], "capacity_exceeded");
    }

    #[tokio::test]
    async fn cancellation_drops_runtime_work_and_finalizes_as_client_owned() {
        let state = Arc::new(FakeServingState::new(0));
        let dropped = Arc::new(AtomicBool::new(false));
        let (started_sender, started) = oneshot::channel();
        let task = task(
            state.clone(),
            Arc::new(PendingRuntime {
                started: Mutex::new(Some(started_sender)),
                dropped: dropped.clone(),
            }),
        );
        let (cancel, cancellation) = oneshot::channel();
        let running = tokio::spawn(task.run(cancellation, running_shutdown()));
        started.await.unwrap();
        cancel.send(()).unwrap();

        assert_eq!(
            running.await.unwrap(),
            Err(GatewayError::RuntimeUnavailable)
        );
        assert!(dropped.load(Ordering::SeqCst));
        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized[0]["status"], "cancelled");
        assert_eq!(finalized[0]["outcome"]["cancellation_owner"], "client");
        assert_eq!(finalized[0]["outcome"]["usable_output_delivered"], false);
    }

    #[tokio::test]
    async fn draining_preserves_generation_until_forced_shutdown() {
        let state = Arc::new(FakeServingState::new(0));
        let dropped = Arc::new(AtomicBool::new(false));
        let (started_sender, started) = oneshot::channel();
        let service = CompletionService::new(
            state.clone(),
            Arc::new(PendingRuntime {
                started: Mutex::new(Some(started_sender)),
                dropped: dropped.clone(),
            }),
            ModelTokenizer::new().unwrap(),
            Arc::new(config()),
        );
        let running_service = service.clone();
        let mut running =
            tokio::spawn(async move { running_service.complete_bounded(bounded_request()).await });
        started.await.unwrap();

        service.begin_draining();
        assert!(
            tokio::time::timeout(Duration::from_millis(25), &mut running)
                .await
                .is_err()
        );
        assert!(!dropped.load(Ordering::SeqCst));
        assert!(state.finalized.lock().unwrap().is_empty());

        service.force_shutdown();
        assert_eq!(
            running.await.unwrap(),
            Err(GatewayError::RuntimeUnavailable)
        );
        tokio::time::timeout(Duration::from_secs(1), service.wait_for_drain())
            .await
            .unwrap();

        assert!(dropped.load(Ordering::SeqCst));
        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized[0]["status"], "cancelled");
        assert_eq!(finalized[0]["outcome"]["cancellation_owner"], "server");
    }

    #[tokio::test]
    async fn finalization_retries_before_returning_a_successful_response() {
        let state = Arc::new(FakeServingState::new(2));
        let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
        let (_cancel, cancellation) = oneshot::channel();

        let result = task(state.clone(), runtime)
            .run(cancellation, running_shutdown())
            .await;

        assert!(result.is_ok());
        assert_eq!(state.finalization_attempts.load(Ordering::SeqCst), 3);
        assert_eq!(state.finalized.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn unconfirmed_finalization_withholds_the_successful_response() {
        let state = Arc::new(FakeServingState::new(FINALIZATION_ATTEMPTS));
        let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
        let (_cancel, cancellation) = oneshot::channel();

        let result = task(state.clone(), runtime)
            .run(cancellation, running_shutdown())
            .await;

        assert_eq!(result, Err(GatewayError::FinalizationUnavailable));
        assert_eq!(
            state.finalization_attempts.load(Ordering::SeqCst),
            FINALIZATION_ATTEMPTS
        );
        assert!(state.finalized.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn streaming_finalizes_before_done_and_exposes_only_terminal_usage() {
        let state = Arc::new(FakeServingState::new(0));
        let usage = NormalizedUsage::new(10, 0, 0, 2, 0).unwrap();
        let runtime = Arc::new(StreamingRuntime {
            events: Mutex::new(Some(VecDeque::from([
                Ok(RuntimeStreamEvent::Chunk(
                    RuntimeStreamChunk::from_normalized_parts(
                        json!({"id":"chunk-1","choices":[{"delta":{"content":"hi"}}]}),
                        Some(NormalizedUsage::new(10, 0, 0, 1, 0).unwrap()),
                        None,
                        true,
                        false,
                    ),
                )),
                Ok(RuntimeStreamEvent::Chunk(
                    RuntimeStreamChunk::from_normalized_parts(
                        json!({"id":"chunk-1","choices":[{"delta":{},"finish_reason":"stop"}]}),
                        None,
                        Some("stop".to_owned()),
                        false,
                        false,
                    ),
                )),
                Ok(RuntimeStreamEvent::Chunk(
                    RuntimeStreamChunk::from_normalized_parts(
                        json!({"id":"chunk-1","choices":[],"usage":{"total_tokens":12}}),
                        Some(usage),
                        None,
                        false,
                        true,
                    ),
                )),
                Ok(RuntimeStreamEvent::Done),
            ]))),
        });
        let service = CompletionService::new(
            state.clone(),
            runtime,
            ModelTokenizer::new().unwrap(),
            Arc::new(config()),
        );
        let mut bounded = bounded_request();
        bounded.qualified.request.stream = true;

        let streaming = service.stream_bounded(bounded).await.unwrap();
        let body = to_bytes(
            Sse::new(streaming.into_stream())
                .into_response()
                .into_body(),
            16_384,
        )
        .await
        .unwrap();
        let body = String::from_utf8(body.to_vec()).unwrap();

        assert!(body.ends_with("data: [DONE]\n\n"));
        assert_eq!(body.matches("\"usage\"").count(), 1);
        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized.len(), 1);
        assert_eq!(finalized[0]["status"], "succeeded");
        assert_eq!(finalized[0]["streamed"], true);
        assert_eq!(finalized[0]["usage"]["input_tokens"], 10);
        assert_eq!(finalized[0]["usage"]["output_tokens"], 2);
        assert_eq!(finalized[0]["outcome"]["usable_output_delivered"], true);
        assert!(finalized[0]["timing"]["first_token_at"].is_string());
    }

    #[tokio::test]
    async fn a_dropped_streaming_body_finalizes_as_client_cancellation() {
        let state = Arc::new(FakeServingState::new(0));
        let service = CompletionService::new(
            state.clone(),
            Arc::new(PendingStreamingRuntime),
            ModelTokenizer::new().unwrap(),
            Arc::new(config()),
        );
        let mut bounded = bounded_request();
        bounded.qualified.request.stream = true;

        let streaming = service.stream_bounded(bounded).await.unwrap();
        drop(streaming);
        tokio::time::timeout(Duration::from_secs(1), async {
            loop {
                if !state.finalized.lock().unwrap().is_empty() {
                    break;
                }
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();

        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized[0]["status"], "cancelled");
        assert_eq!(finalized[0]["outcome"]["cancellation_owner"], "client");
    }
}
