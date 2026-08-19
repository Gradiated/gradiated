use std::{cmp, sync::Arc, time::Duration};

use axum::{body::Bytes, http::HeaderMap};
use chrono::Utc;
use serde_json::Value;
use tokio::sync::oneshot;
use uuid::Uuid;

use crate::{
    BoundedRequest, CancellationOwner, FinalizationOutcome, GatewayConfig, GatewayError,
    GenerationIdentity, GenerationProperties, GenerationStatus, GenerationTiming, ModelRuntime,
    ModelTokenizer, NormalizedUsage, PricedUsage, RequestCoordinator, RequestMetadata,
    RuntimeFailure, RuntimeFailureKind, ServingState, TerminalOutcome,
};

const FINALIZATION_ATTEMPTS: usize = 3;
const FINALIZATION_RETRY_DELAY: Duration = Duration::from_millis(25);

#[derive(Clone)]
pub struct CompletionService {
    coordinator: RequestCoordinator,
    tokenizer: ModelTokenizer,
    serving_state: Arc<dyn ServingState>,
    runtime: Arc<dyn ModelRuntime>,
    config: Arc<GatewayConfig>,
}

impl CompletionService {
    pub fn new(
        serving_state: Arc<dyn ServingState>,
        runtime: Arc<dyn ModelRuntime>,
        tokenizer: ModelTokenizer,
        config: Arc<GatewayConfig>,
    ) -> Self {
        Self {
            coordinator: RequestCoordinator::new(serving_state.clone()),
            tokenizer,
            serving_state,
            runtime,
            config,
        }
    }

    pub async fn complete_non_streaming(
        &self,
        metadata: RequestMetadata,
        headers: &HeaderMap,
        body: Bytes,
    ) -> Result<CompletionResult, GatewayError> {
        let qualified = self.coordinator.qualify(metadata, headers, &body).await?;
        drop(body);
        if qualified.request.stream {
            return Err(GatewayError::unsupported_parameter("stream"));
        }
        let bounded = self.tokenizer.enforce(qualified).await?;
        self.complete_bounded(bounded).await
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
        let admitted_at = cmp::max(Utc::now(), bounded.qualified.metadata.received_at);
        let lease = self
            .serving_state
            .admit(
                bounded.qualified.metadata.generation_id,
                bounded.qualified.identity.organization_id,
                bounded.qualified.metadata.received_at,
                admitted_at,
                &self.config,
            )
            .await?;
        wait_for_generation(GenerationTask {
            bounded,
            generation_identity,
            lease,
            serving_state: self.serving_state.clone(),
            runtime: self.runtime.clone(),
        })
        .await
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CompletionResult {
    generation_id: Uuid,
    response: Value,
}

impl CompletionResult {
    pub fn generation_id(&self) -> Uuid {
        self.generation_id
    }

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
}

impl GenerationTask {
    async fn run(
        self,
        mut cancellation: oneshot::Receiver<()>,
    ) -> Result<CompletionResult, GatewayError> {
        let GenerationTask {
            bounded,
            generation_identity,
            lease,
            serving_state,
            runtime,
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

        let (
            usage,
            mut status,
            mut finish_reason,
            mut error,
            mut cancellation_owner,
            mut usable,
            mut response,
        ) = {
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
                        let finish_reason = Some(completion.finish_reason().to_owned());
                        (
                            usage,
                            GenerationStatus::Succeeded,
                            finish_reason,
                            None,
                            None,
                            true,
                            Some(completion.into_response()),
                        )
                    }
                    Err(failure) => {
                        let error = failure.gateway_error();
                        let (status, owner) = if failure.kind() == RuntimeFailureKind::TimedOut {
                            (GenerationStatus::Cancelled, Some(CancellationOwner::Server))
                        } else {
                            (GenerationStatus::Failed, None)
                        };
                        (
                            failure.usage(),
                            status,
                            None,
                            Some(error),
                            owner,
                            false,
                            None,
                        )
                    }
                },
                _ = &mut cancellation => (
                    NormalizedUsage::zero(),
                    GenerationStatus::Cancelled,
                    None,
                    Some(GatewayError::RuntimeUnavailable),
                    Some(CancellationOwner::Client),
                    false,
                    None,
                ),
            }
        };

        let priced_usage = match PricedUsage::calculate(&pricing, usage) {
            Ok(priced_usage) => priced_usage,
            Err(_) => {
                status = GenerationStatus::Failed;
                finish_reason = None;
                error = Some(GatewayError::RuntimeUnavailable);
                cancellation_owner = None;
                usable = false;
                PricedUsage::zero(&pricing)
            }
        };
        let error_code = error.as_ref().map(|error| error.code().to_owned());
        let outcome = match TerminalOutcome::new(
            status,
            finish_reason,
            error_code,
            usable,
            cancellation_owner,
        ) {
            Ok(outcome) => outcome,
            Err(_) => {
                error = Some(GatewayError::RuntimeUnavailable);
                response = None;
                TerminalOutcome::failed("runtime_unavailable")
            }
        };
        let completed_at = cmp::max(Utc::now(), started_at);
        let properties = GenerationProperties::new(
            generation_identity,
            false,
            priced_usage,
            outcome,
            GenerationTiming::completed(received_at, started_at, completed_at),
        );

        finalize_with_retry(&serving_state, generation_id, organization_id, &properties).await?;
        match (response, error) {
            (Some(response), None) => Ok(CompletionResult {
                generation_id,
                response,
            }),
            (_, Some(error)) => Err(error),
            _ => Err(GatewayError::RuntimeUnavailable),
        }
    }
}

async fn finalize_with_retry(
    serving_state: &Arc<dyn ServingState>,
    generation_id: Uuid,
    organization_id: Uuid,
    properties: &GenerationProperties,
) -> Result<(), GatewayError> {
    let mut last_error = None;
    for attempt in 0..FINALIZATION_ATTEMPTS {
        match serving_state
            .finalize(generation_id, organization_id, properties)
            .await
        {
            Ok(FinalizationOutcome::Settled | FinalizationOutcome::AlreadyAbsent) => return Ok(()),
            Err(error) => last_error = Some(error),
        }
        if attempt + 1 < FINALIZATION_ATTEMPTS {
            tokio::time::sleep(FINALIZATION_RETRY_DELAY).await;
        }
    }
    match last_error {
        Some(error) => Err(error.into()),
        None => Err(GatewayError::FinalizationUnavailable),
    }
}

async fn wait_for_generation(task: GenerationTask) -> Result<CompletionResult, GatewayError> {
    let (cancel, cancellation) = oneshot::channel();
    let generation = tokio::spawn(task.run(cancellation));
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
    use std::sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Mutex,
    };

    use async_trait::async_trait;
    use chrono::{DateTime, TimeDelta, Utc};
    use serde_json::json;

    use super::*;
    use crate::{
        auth::AuthenticatedIdentity,
        domain::{GatewayAccount, GatewayCredential, GatewayWorkspace},
        serving_state::ServingStateError,
        AdmissionError, AdmissionLease, CapturedPricing, ChatCompletionRequest, DeploymentStatus,
        FinalizationError, GatewayModel, GatewayModelDeployment, InputTokenPrice,
        ModelDeploymentRelease, OutputTokenPrice, QualifiedRequest, RuntimeCompletion, TokenUnit,
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
        GenerationTask {
            bounded,
            generation_identity,
            lease,
            serving_state: state,
            runtime,
        }
    }

    fn successful_completion() -> RuntimeCompletion {
        RuntimeCompletion::from_normalized_parts(
            json!({"id": "chatcmpl-1"}),
            "stop".to_owned(),
            NormalizedUsage::new(10, 4, 0, 5, 0).unwrap(),
        )
    }

    #[tokio::test]
    async fn successful_generation_is_finalized_before_its_response_is_returned() {
        let state = Arc::new(FakeServingState::new(0));
        let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
        let (_cancel, cancellation) = oneshot::channel();

        let result = task(state.clone(), runtime)
            .run(cancellation)
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

        let result = task(state.clone(), runtime).run(cancellation).await;

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
        let running = tokio::spawn(task.run(cancellation));
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
    async fn finalization_retries_before_returning_a_successful_response() {
        let state = Arc::new(FakeServingState::new(2));
        let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
        let (_cancel, cancellation) = oneshot::channel();

        let result = task(state.clone(), runtime).run(cancellation).await;

        assert!(result.is_ok());
        assert_eq!(state.finalization_attempts.load(Ordering::SeqCst), 3);
        assert_eq!(state.finalized.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn unconfirmed_finalization_withholds_the_successful_response() {
        let state = Arc::new(FakeServingState::new(FINALIZATION_ATTEMPTS));
        let runtime = Arc::new(FixedRuntime(Ok(successful_completion())));
        let (_cancel, cancellation) = oneshot::channel();

        let result = task(state.clone(), runtime).run(cancellation).await;

        assert_eq!(result, Err(GatewayError::FinalizationUnavailable));
        assert_eq!(
            state.finalization_attempts.load(Ordering::SeqCst),
            FINALIZATION_ATTEMPTS
        );
        assert!(state.finalized.lock().unwrap().is_empty());
    }
}
