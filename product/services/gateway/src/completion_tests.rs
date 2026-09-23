use std::{
    collections::VecDeque,
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Mutex,
    },
};

use async_trait::async_trait;
use chrono::{DateTime, TimeDelta, Utc};
use futures_util::StreamExt;
use serde_json::json;

use super::*;
use crate::{
    auth::AuthenticatedIdentity,
    domain::{GatewayAccount, GatewayCredential, GatewayWorkspace},
    serving_state::ServingStateError,
    AdmissionError, AdmissionLease, CapturedPricing, DeploymentStatus, FinalizationError,
    GatewayModel, GatewayModelDeployment, InferenceRequest, InputTokenPrice,
    ModelDeploymentRelease, OutputTokenPrice, QualifiedRequest, RuntimeCompletion,
    RuntimeEventStream, RuntimeStreamChunk, TokenUnit,
};

/// Observes admission and settlement. It serves no projections, because these
/// tests build a qualified request directly. Projection fixtures live in
/// `test_support`.
struct SettlementServingState {
    finalized: Mutex<Vec<Value>>,
    admitted: Arc<AtomicBool>,
    finalization_failures: AtomicUsize,
    finalization_attempts: AtomicUsize,
}

impl SettlementServingState {
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
impl ServingState for SettlementServingState {
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

    async fn deployment_statuses(
        &self,
        _release_digest: &str,
    ) -> Result<Vec<crate::DeploymentRuntimeStatus>, ServingStateError> {
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

struct SequencedRuntime {
    results: Mutex<VecDeque<Result<RuntimeCompletion, RuntimeFailure>>>,
    deployments: Mutex<Vec<Uuid>>,
}

#[async_trait]
impl ModelRuntime for FixedRuntime {
    async fn complete(
        &self,
        _deployment: &GatewayModelDeployment,
        _request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        self.0.clone()
    }
}

#[async_trait]
impl ModelRuntime for SequencedRuntime {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        _request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        self.deployments.lock().unwrap().push(deployment.id);
        self.results.lock().unwrap().pop_front().unwrap()
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
        _request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        unreachable!("streaming tests do not call complete")
    }

    async fn stream(
        &self,
        _deployment: &GatewayModelDeployment,
        _request: InferenceRequest,
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
        _request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        unreachable!("streaming tests do not call complete")
    }

    async fn stream(
        &self,
        _deployment: &GatewayModelDeployment,
        request: InferenceRequest,
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
        _request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        if !self.admitted.load(Ordering::SeqCst) {
            return Err(RuntimeFailure::protocol_violation());
        }
        Ok(successful_completion())
    }
}

#[async_trait]
impl ModelRuntime for PendingRuntime {
    async fn complete(
        &self,
        _deployment: &GatewayModelDeployment,
        _request: InferenceRequest,
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
    GatewayConfig::for_tests()
}

fn bounded_request() -> BoundedRequest {
    let generation_id = Uuid::now_v7();
    let organization_id = Uuid::now_v7();
    let request = InferenceRequest::parse(
        br#"{"model":"model-a","messages":[{"role":"user","content":"hello"}]}"#,
    )
    .unwrap();
    let qualified = QualifiedRequest {
        metadata: crate::RequestMetadata {
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
            provider: "local".to_owned(),
            region: "local".to_owned(),
            fault_domain: "local:runtime-1".to_owned(),
            service_url: "http://127.0.0.1:30000".to_owned(),
            release: ModelDeploymentRelease {
                schema_version: 1,
                runtime_revision: "runtime".to_owned(),
                protocol: None,
                model_path: "model-a".to_owned(),
                model_revision: "model-revision".to_owned(),
                runtime_model_name: None,
                tokenizer_path: "model-a".to_owned(),
                tokenizer_revision: "tokenizer-revision".to_owned(),
                tokenizer_mode: None,
            },
        },
        served_release_digest: format!("sha256:{}", "a".repeat(64)),
        model_deployments: Vec::new(),
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
        input_tokens: Some(10),
    }
}

fn task(state: Arc<SettlementServingState>, runtime: Arc<dyn ModelRuntime>) -> Generation {
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
        bounded.qualified.deployment.release.protocol_label(),
        bounded.qualified.request.stream,
        bounded.qualified.request.service_tier,
    );
    Generation {
        bounded,
        generation_identity,
        lease,
        serving_state: state,
        runtime,
        metrics,
        fallbacks: Vec::new(),
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
    let state = Arc::new(SettlementServingState::new(0));
    let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
    let (_cancel, cancellation) = oneshot::channel();

    let result = task(state.clone(), runtime)
        .complete(cancellation, running_shutdown())
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
async fn chat_dispatch_does_not_depend_on_local_template_or_context_estimates() {
    let state = Arc::new(SettlementServingState::new(0));
    let service = CompletionService::new(
        state,
        Arc::new(FixedRuntime(Ok(successful_completion()))),
        ModelTokenizer::new().unwrap(),
        Arc::new(config()),
    );
    let mut qualified = bounded_request().qualified;
    // Invalid local artifact and absurd projected input bounds would have
    // blocked dispatch before the chat deployment could validate the request.
    qualified.deployment.release.tokenizer_path = "missing/local-artifact".to_owned();
    qualified.max_prompt_tokens = 0;
    qualified.max_context_tokens = 1;
    qualified
        .request
        .parameters
        .insert("reasoning_effort".to_owned(), json!("deployment-specific"));
    let request = qualified.request.clone();
    let prepared = service.bound(qualified).await.unwrap();
    assert_eq!(prepared.qualified.request, request);
    assert_eq!(prepared.input_tokens, None);
    assert_eq!(prepared.qualified.request.encoded_input_ids, None);
}

#[tokio::test]
async fn decision_settlement_bills_input_and_cached_input_without_output() {
    let state = Arc::new(SettlementServingState::new(0));
    let runtime = Arc::new(FixedRuntime(Ok(RuntimeCompletion::from_normalized_parts(
        json!({"model":"model-a","answers":{"q":{"type":"noul","noul":0.9}}}),
        "stop".to_owned(),
        NormalizedUsage::new(10, 4, 0, 0, 0).unwrap(),
    ))));
    let mut generation = task(state.clone(), runtime);
    generation.bounded.qualified.request = InferenceRequest::parse_kind(
        br#"{"model":"model-a","state":"x","questions":{"q":{"type":"noul","instructions":"yes?"}}}"#,
        crate::RequestKind::SystemOne,
    ).unwrap();
    generation.bounded.qualified.effective_output_tokens = 0;
    generation.bounded.qualified.deployment.release.protocol =
        Some(crate::RuntimeProtocol::SystemOne);
    let (_cancel, cancellation) = oneshot::channel();
    generation
        .complete(cancellation, running_shutdown())
        .await
        .unwrap();
    let finalized = state.finalized.lock().unwrap();
    assert_eq!(finalized.len(), 1);
    assert_eq!(finalized[0]["usage"]["input_tokens"], 10);
    assert_eq!(finalized[0]["usage"]["cached_input_tokens"], 4);
    assert_eq!(finalized[0]["usage"]["output_tokens"], 0);
    assert_eq!(finalized[0]["usage"]["charge"], 16);
}

#[tokio::test]
async fn runtime_usage_overrides_local_input_estimate_for_settlement() {
    for estimated_input in [7, 13] {
        let state = Arc::new(SettlementServingState::new(0));
        let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
        let mut generation = task(state.clone(), runtime);
        generation.bounded.input_tokens = Some(estimated_input);
        let (_cancel, cancellation) = oneshot::channel();
        assert!(generation
            .complete(cancellation, running_shutdown())
            .await
            .is_ok());
        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized.len(), 1);
        assert_eq!(finalized[0]["status"], "succeeded");
        assert_eq!(finalized[0]["usage"]["input_tokens"], 10);
        assert_eq!(finalized[0]["usage"]["charge"], 31);
    }
}

#[tokio::test]
async fn streaming_uses_runtime_counts_but_rejects_inconsistent_counters() {
    // Local admission counted 10. Both higher and lower engine counts are
    // authoritative, but a changing prompt count or decreasing output is not.
    for (first_input, last_input, last_output, status) in [
        (7, 7, 2, "succeeded"),
        (13, 13, 2, "succeeded"),
        (7, 8, 2, "failed"),
        (7, 7, 0, "failed"),
    ] {
        let state = Arc::new(SettlementServingState::new(0));
        let runtime = Arc::new(StreamingRuntime {
            events: Mutex::new(Some(VecDeque::from([
                Ok(RuntimeStreamEvent::Chunk(
                    RuntimeStreamChunk::from_normalized_parts(
                        json!({"choices":[{"delta":{"content":"hi"}}]}),
                        Some(NormalizedUsage::new(first_input, 0, 0, 1, 0).unwrap()),
                        None,
                        true,
                        false,
                    ),
                )),
                Ok(RuntimeStreamEvent::Chunk(
                    RuntimeStreamChunk::from_normalized_parts(
                        json!({"choices":[], "usage":{"prompt_tokens":last_input,"completion_tokens":last_output,"total_tokens":last_input+last_output}}),
                        Some(NormalizedUsage::new(last_input, 0, 0, last_output, 0).unwrap()),
                        Some("stop".to_owned()),
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
        let stream = service.stream_bounded(bounded).await.unwrap();
        let _items = stream.into_stream().collect::<Vec<_>>().await;
        let finalized = state.finalized.lock().unwrap();
        assert_eq!(finalized.len(), 1);
        assert_eq!(finalized[0]["status"], status);
        assert_eq!(finalized[0]["usage"]["input_tokens"], first_input);
        if status == "succeeded" {
            assert_eq!(finalized[0]["usage"]["output_tokens"], last_output);
            assert_eq!(
                finalized[0]["usage"]["charge"],
                first_input * 2 + last_output * 3
            );
        }
    }
}

#[tokio::test]
async fn unavailable_runtime_retries_one_other_deployment_and_settles_once() {
    let state = Arc::new(SettlementServingState::new(0));
    let runtime = Arc::new(SequencedRuntime {
        results: Mutex::new(VecDeque::from([
            Err(RuntimeFailure::new(RuntimeFailureKind::Unavailable)),
            Ok(successful_completion()),
        ])),
        deployments: Mutex::new(Vec::new()),
    });
    let mut task = task(state.clone(), runtime.clone());
    let first = task.bounded.qualified.deployment.clone();
    let mut second = first.clone();
    second.id = Uuid::now_v7();
    second.service_url = "http://127.0.0.1:30001".to_owned();
    second.fault_domain = "local:runtime-2".to_owned();
    task.fallbacks = vec![RoutedDeployment {
        deployment: second.clone(),
    }];
    let (_cancel, cancellation) = oneshot::channel();

    let result = task
        .complete(cancellation, running_shutdown())
        .await
        .unwrap();

    assert_eq!(result.response["id"], "chatcmpl-1");
    assert_eq!(
        *runtime.deployments.lock().unwrap(),
        vec![first.id, second.id]
    );
    assert_eq!(state.finalized.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn completion_service_admits_before_dispatching_runtime_work() {
    let state = Arc::new(SettlementServingState::new(0));
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
    let state = Arc::new(SettlementServingState::new(0));
    let runtime = Arc::new(FixedRuntime(Err(RuntimeFailure::new(
        RuntimeFailureKind::CapacityExceeded,
    ))));
    let (_cancel, cancellation) = oneshot::channel();

    let result = task(state.clone(), runtime)
        .complete(cancellation, running_shutdown())
        .await;

    assert_eq!(result, Err(GatewayError::CapacityExceeded));
    let finalized = state.finalized.lock().unwrap();
    assert_eq!(finalized[0]["status"], "failed");
    assert_eq!(finalized[0]["usage"]["charge"], 0);
    assert_eq!(finalized[0]["outcome"]["error_code"], "capacity_exceeded");
}

#[tokio::test]
async fn cancellation_drops_runtime_work_and_finalizes_as_client_owned() {
    let state = Arc::new(SettlementServingState::new(0));
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
    let running = tokio::spawn(task.complete(cancellation, running_shutdown()));
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
    let state = Arc::new(SettlementServingState::new(0));
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
    let state = Arc::new(SettlementServingState::new(2));
    let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
    let (_cancel, cancellation) = oneshot::channel();

    let result = task(state.clone(), runtime)
        .complete(cancellation, running_shutdown())
        .await;

    assert!(result.is_ok());
    assert_eq!(state.finalization_attempts.load(Ordering::SeqCst), 3);
    assert_eq!(state.finalized.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn unconfirmed_finalization_withholds_the_successful_response() {
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();
    let state = Arc::new(SettlementServingState::new(FINALIZATION_ATTEMPTS));
    let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
    let (_cancel, cancellation) = oneshot::channel();

    let result = task(state.clone(), runtime)
        .complete(cancellation, running_shutdown())
        .await;

    assert_eq!(result, Err(GatewayError::FinalizationUnavailable));
    assert_eq!(
        state.finalization_attempts.load(Ordering::SeqCst),
        FINALIZATION_ATTEMPTS
    );
    assert!(state.finalized.lock().unwrap().is_empty());
    let events = logs.events();
    let failures = events
        .iter()
        .filter(|event| event["fields"]["phase"] == "finalization")
        .collect::<Vec<_>>();
    assert_eq!(failures.len(), 1);
    assert_eq!(failures[0]["level"], "ERROR");
    assert_eq!(failures[0]["fields"]["attempts"], FINALIZATION_ATTEMPTS);
    assert!(failures[0]["fields"]["generation_id"].is_string());
}

#[tokio::test]
async fn streaming_finalizes_before_done_and_exposes_only_terminal_usage() {
    let state = Arc::new(SettlementServingState::new(0));
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
    let mut renderer = crate::protocol::Protocol::OpenAiChat.stream_renderer();
    let frames = streaming
        .into_stream()
        .flat_map(move |item| futures_util::stream::iter(renderer.render(item)))
        .collect::<Vec<_>>()
        .await;

    assert_eq!(
        frames.last().map(|frame| frame.data.as_str()),
        Some("[DONE]")
    );
    assert_eq!(
        frames
            .iter()
            .filter(|frame| frame.data.contains("\"usage\""))
            .count(),
        1
    );
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
async fn logs_incomplete_stream_after_response_start_without_payload() {
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();
    let state = Arc::new(SettlementServingState::new(0));
    let runtime = Arc::new(StreamingRuntime {
        events: Mutex::new(Some(VecDeque::from([
            Ok(RuntimeStreamEvent::Chunk(
                RuntimeStreamChunk::from_normalized_parts(
                    json!({"choices":[{"delta":{"content":"private-output-canary"}}]}),
                    None,
                    None,
                    true,
                    false,
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
    let generation_id = bounded.qualified.metadata.generation_id;
    let streaming = service.stream_bounded(bounded).await.unwrap();
    let _items = streaming.into_stream().collect::<Vec<_>>().await;
    let events = logs.events();
    let failure = events
        .iter()
        .find(|event| event["fields"]["phase"] == "stream")
        .unwrap();
    assert_eq!(
        failure["fields"]["generation_id"],
        generation_id.to_string()
    );
    assert_eq!(failure["fields"]["reason"], "incomplete_stream");
    assert_eq!(failure["fields"]["usable_output_delivered"], true);
    assert!(!serde_json::to_string(&events)
        .unwrap()
        .contains("private-output-canary"));
    assert_eq!(state.finalized.lock().unwrap()[0]["status"], "failed");
}

#[tokio::test]
async fn a_dropped_streaming_body_finalizes_as_client_cancellation() {
    let state = Arc::new(SettlementServingState::new(0));
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

#[tokio::test]
async fn generation_tasks_keep_request_identity_after_the_handler_returns() {
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();
    let tasks = GenerationTasks::new();

    let mut handles = Vec::new();
    for id in [Uuid::from_u128(1), Uuid::from_u128(2)] {
        let span = crate::diagnostics::request_span(id);
        span.record("workspace_id", tracing::field::display(id));
        handles.push(span.in_scope(|| {
            tasks.spawn(async move {
                tokio::task::yield_now().await;
                tracing::info!(event = "test_stream_terminal", "terminal");
            })
        }));
    }
    for handle in handles {
        handle.await.unwrap();
    }

    let events = logs.events();
    assert_eq!(events.len(), 2);
    for event in events {
        assert_eq!(
            event["span"]["workspace_id"],
            event["span"]["generation_id"]
        );
        assert!(event["span"]["workspace_id"].is_string());
    }
}
