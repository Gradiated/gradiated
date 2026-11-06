use std::{
    collections::VecDeque,
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    time::Duration,
};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use futures_util::StreamExt;
use serde_json::json;

use super::super::*;
use crate::{
    auth::AuthenticatedIdentity,
    domain::{GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace},
    generation::fixtures::token_prices,
    routing::fixtures::{deployment, healthy_status},
    serving_state::ServingStateError,
    AdmissionError, DeploymentRuntimeStatus, ExternalCapacity, ExternalModel, ExternalRequest,
    FinalizationError, FinalizationOutcome, GatewayModelDeployment, GenerationProperties,
    NormalizedUsage, RequestMetadata, RuntimeCompletion, RuntimeEventStream, RuntimeFailure,
    RuntimeFailureKind, RuntimeStreamChunk, RuntimeStreamEvent,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum Step {
    Admit,
    Dispatch(Uuid),
    External,
    Finalize,
}

#[derive(Clone, Default)]
pub(super) struct Journal(Arc<Mutex<Vec<Step>>>);

impl Journal {
    pub(super) fn push(&self, step: Step) {
        self.0.lock().unwrap().push(step);
    }

    pub(super) fn steps(&self) -> Vec<Step> {
        self.0.lock().unwrap().clone()
    }

    pub(super) fn dispatches(&self) -> Vec<Uuid> {
        self.steps()
            .into_iter()
            .filter_map(|step| match step {
                Step::Dispatch(deployment) => Some(deployment),
                _ => None,
            })
            .collect()
    }

    pub(super) fn external_dispatches(&self) -> usize {
        self.steps()
            .into_iter()
            .filter(|step| *step == Step::External)
            .count()
    }

    pub(super) fn finalizations(&self) -> usize {
        self.steps()
            .into_iter()
            .filter(|step| *step == Step::Finalize)
            .count()
    }
}

pub(super) struct Hang {
    pub(super) started: oneshot::Sender<()>,
    pub(super) dropped: Arc<AtomicBool>,
}

pub(super) struct HangSignal {
    pub(super) started: oneshot::Receiver<()>,
    pub(super) dropped: Arc<AtomicBool>,
}

impl HangSignal {
    pub(super) fn dropped(&self) -> bool {
        self.dropped.load(Ordering::SeqCst)
    }
}

pub(super) fn hang() -> (Hang, HangSignal) {
    let (started, started_signal) = oneshot::channel();
    let dropped = Arc::new(AtomicBool::new(false));

    (
        Hang {
            started,
            dropped: dropped.clone(),
        },
        HangSignal {
            started: started_signal,
            dropped,
        },
    )
}

pub(super) struct DropNotice(Arc<AtomicBool>);

impl Drop for DropNotice {
    fn drop(&mut self) {
        self.0.store(true, Ordering::SeqCst);
    }
}

impl Hang {
    pub(super) async fn wait<T>(self) -> T {
        let _notice = DropNotice(self.dropped);
        let _ = self.started.send(());

        std::future::pending().await
    }
}

pub(super) struct Gate {
    entered: oneshot::Sender<()>,
    release: oneshot::Receiver<()>,
}

pub(super) struct GateHandle {
    pub(super) entered: oneshot::Receiver<()>,
    pub(super) release: oneshot::Sender<()>,
}

pub(super) fn gate() -> (Gate, GateHandle) {
    let (entered, entered_signal) = oneshot::channel();
    let (release_signal, release) = oneshot::channel();

    (
        Gate { entered, release },
        GateHandle {
            entered: entered_signal,
            release: release_signal,
        },
    )
}

impl Gate {
    async fn pass(self) {
        let _ = self.entered.send(());
        let _ = self.release.await;
    }
}

pub(super) type ScriptedEvent = Result<RuntimeStreamEvent, RuntimeFailure>;

pub(super) enum Script {
    Fail(RuntimeFailure),
    Complete(RuntimeCompletion),
    Stream(Vec<ScriptedEvent>),
    StreamThenHang(Vec<ScriptedEvent>, Hang),
    /// Unlike a hang, every later read stays pending, as a silent connection does.
    StreamThenStall(Vec<ScriptedEvent>),
    StreamThenPanic(Vec<ScriptedEvent>),
    Hang(Hang),
    Panic,
}

pub(super) struct ScriptedRuntime {
    scripts: Mutex<VecDeque<Script>>,
    journal: Journal,
}

impl ScriptedRuntime {
    pub(super) fn new(scripts: impl IntoIterator<Item = Script>, journal: Journal) -> Self {
        Self {
            scripts: Mutex::new(scripts.into_iter().collect()),
            journal,
        }
    }

    pub(super) fn next(&self, deployment: &GatewayModelDeployment) -> Script {
        self.journal.push(Step::Dispatch(deployment.id));

        self.scripts
            .lock()
            .unwrap()
            .pop_front()
            .expect("every dispatch is scripted")
    }
}

#[async_trait]
impl ModelRuntime for ScriptedRuntime {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        assert!(!request.stream);

        complete_script(self.next(deployment)).await
    }

    async fn stream(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        assert!(request.stream);

        stream_script(self.next(deployment)).await
    }
}

/// OpenRouter capacity with its own scripts. It records each request it receives.
pub(super) struct ScriptedExternal {
    scripts: Mutex<VecDeque<Script>>,
    journal: Journal,
    pub(super) requests: Mutex<Vec<ExternalRequest>>,
}

impl ScriptedExternal {
    fn next(&self, request: ExternalRequest) -> Script {
        self.journal.push(Step::External);
        self.requests.lock().unwrap().push(request);

        self.scripts
            .lock()
            .unwrap()
            .pop_front()
            .expect("every external dispatch is scripted")
    }
}

#[async_trait]
impl ExternalCapacity for ScriptedExternal {
    async fn complete(
        &self,
        request: ExternalRequest,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        assert!(!request.request.stream);

        complete_script(self.next(request)).await
    }

    async fn stream(
        &self,
        request: ExternalRequest,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        assert!(request.request.stream);

        stream_script(self.next(request)).await
    }
}

async fn complete_script(script: Script) -> Result<RuntimeCompletion, RuntimeFailure> {
    match script {
        Script::Fail(failure) => Err(failure),
        Script::Complete(completion) => Ok(completion),
        Script::Hang(hang) => hang.wait().await,
        Script::Panic => panic!("scripted runtime panic"),
        Script::Stream(_)
        | Script::StreamThenHang(..)
        | Script::StreamThenStall(_)
        | Script::StreamThenPanic(_) => {
            panic!("a buffered dispatch received a stream script")
        }
    }
}

async fn stream_script(script: Script) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
    let (events, then) = match script {
        Script::Fail(failure) => return Err(failure),
        Script::Stream(events) => (events, StreamEnd::Close),
        Script::StreamThenHang(events, hang) => (events, StreamEnd::Hang(hang)),
        Script::StreamThenStall(events) => (events, StreamEnd::Stall),
        Script::StreamThenPanic(events) => (events, StreamEnd::Panic),
        Script::Hang(hang) => return hang.wait().await,
        Script::Panic => panic!("scripted runtime panic"),
        Script::Complete(_) => panic!("a streaming dispatch received a buffered script"),
    };

    Ok(Box::new(ScriptedStream {
        events: events.into(),
        then: Some(then),
    }))
}

pub(super) enum StreamEnd {
    Close,
    Hang(Hang),
    Stall,
    Panic,
}

pub(super) struct ScriptedStream {
    pub(super) events: VecDeque<ScriptedEvent>,
    pub(super) then: Option<StreamEnd>,
}

#[async_trait]
impl RuntimeEventStream for ScriptedStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        if let Some(event) = self.events.pop_front() {
            return event.map(Some);
        }

        if matches!(self.then, Some(StreamEnd::Stall)) {
            return std::future::pending().await;
        }

        match self.then.take() {
            Some(StreamEnd::Hang(hang)) => hang.wait().await,
            Some(StreamEnd::Panic) => panic!("scripted stream panic"),
            Some(StreamEnd::Close | StreamEnd::Stall) | None => Ok(None),
        }
    }
}

pub(super) struct RecordingServingState {
    pub(super) journal: Journal,
    pub(super) statuses: Mutex<Vec<DeploymentRuntimeStatus>>,
    pub(super) status_gate: Mutex<Option<Gate>>,
    pub(super) status_error: Mutex<Option<ServingStateError>>,
    pub(super) admission_error: Mutex<Option<AdmissionError>>,
    pub(super) finalizations: Mutex<VecDeque<FinalizationResult>>,
    pub(super) finalized: Mutex<Vec<Value>>,
}

impl RecordingServingState {
    pub(super) fn serving(journal: Journal, deployments: &[GatewayModelDeployment]) -> Self {
        let statuses = deployments
            .iter()
            .map(|deployment| healthy_status(deployment, Utc::now()))
            .collect();

        Self {
            journal,
            statuses: Mutex::new(statuses),
            status_gate: Mutex::new(None),
            status_error: Mutex::new(None),
            admission_error: Mutex::new(None),
            finalizations: Mutex::new(VecDeque::new()),
            finalized: Mutex::new(Vec::new()),
        }
    }
}

#[async_trait]
impl ServingState for RecordingServingState {
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

    async fn private_model_exists(
        &self,
        _workspace_id: Uuid,
        _name: &str,
    ) -> Result<bool, ServingStateError> {
        Ok(false)
    }

    async fn private_adapter(
        &self,
        _workspace_id: Uuid,
        _name: &str,
    ) -> Result<Option<crate::PrivateAdapter>, ServingStateError> {
        Ok(None)
    }

    async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
        Ok(Vec::new())
    }

    async fn deployment_statuses(
        &self,
        _release_digest: &str,
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError> {
        let gate = self.status_gate.lock().unwrap().take();
        if let Some(gate) = gate {
            gate.pass().await;
        }

        match self.status_error.lock().unwrap().take() {
            Some(error) => Err(error),
            None => Ok(self.statuses.lock().unwrap().clone()),
        }
    }

    async fn admit(
        &self,
        generation_id: Uuid,
        _organization_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
    ) -> Result<AdmissionLease, AdmissionError> {
        self.journal.push(Step::Admit);

        match self.admission_error.lock().unwrap().take() {
            Some(error) => Err(error),
            None => AdmissionLease::new(generation_id, received_at, admitted_at, config),
        }
    }

    async fn finalize(
        &self,
        _generation_id: Uuid,
        _organization_id: Uuid,
        properties: &GenerationProperties,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        self.journal.push(Step::Finalize);

        let outcome = self.finalizations.lock().unwrap().pop_front().map_or(
            Ok(FinalizationOutcome::Settled),
            FinalizationResult::into_outcome,
        );
        if matches!(outcome, Ok(FinalizationOutcome::Settled)) {
            self.finalized
                .lock()
                .unwrap()
                .push(serde_json::to_value(properties).unwrap());
        }

        outcome
    }
}

pub(super) fn qualified_request(deployment_count: u128) -> QualifiedRequest {
    let template = deployment(0);
    let model_deployments = (1..=deployment_count).map(deployment).collect();

    QualifiedRequest {
        is_verification: false,
        adapter: None,
        metadata: RequestMetadata {
            generation_id: Uuid::now_v7(),
            received_at: Utc::now(),
        },
        identity: AuthenticatedIdentity {
            api_key_id: Uuid::now_v7(),
            organization_id: Uuid::now_v7(),
            workspace_id: Uuid::now_v7(),
        },
        local: Some(LocalCapacity {
            release_digest: template.served_release_digest().unwrap(),
            deployment: template,
            deployments: model_deployments,
        }),
        base: None,
        external: None,
        max_context_tokens: 8_192,
        max_prompt_tokens: 7_168,
        effective_output_tokens: 1_024,
        pricing: token_prices(2, 1, 3),
        request: InferenceRequest::parse(
            br#"{"model":"model-a","messages":[{"role":"user","content":"hello"}]}"#,
        )
        .unwrap(),
    }
}

pub(super) const OPENROUTER_MODEL: &str = "author/model-a";

/// A mapped model with `deployment_count` local deployments.
pub(super) fn mapped_request(deployment_count: u128) -> QualifiedRequest {
    let mut request = qualified_request(deployment_count.max(1));
    if deployment_count == 0 {
        request.local = None;
    }
    request.external = Some(ExternalModel::openrouter(OPENROUTER_MODEL));

    request
}

pub(super) fn streaming_request(deployment_count: u128) -> QualifiedRequest {
    let mut request = qualified_request(deployment_count);
    request.request.stream = true;

    request
}

pub(super) fn usage(input: u64, cached: u64, output: u64) -> NormalizedUsage {
    NormalizedUsage::new(input, cached, 0, output, 0).unwrap()
}

pub(super) fn completion() -> Script {
    Script::Complete(RuntimeCompletion::from_normalized_parts(
        json!({"id": "chatcmpl-1"}),
        "stop".to_owned(),
        usage(10, 4, 5),
    ))
}

/// Distinct from `completion()` so a test can tell which capacity was billed.
pub(super) fn external_completion() -> Script {
    Script::Complete(
        RuntimeCompletion::from_normalized_parts(
            json!({"id": "chatcmpl-external", "usage": {"prompt_tokens": 20}}),
            "stop".to_owned(),
            usage(20, 0, 7),
        )
        .with_upstream_cost(5_000_000),
    )
}

pub(super) fn failure(kind: RuntimeFailureKind) -> Script {
    Script::Fail(RuntimeFailure::new(kind))
}

pub(super) fn content(text: &str, usage: Option<NormalizedUsage>) -> ScriptedEvent {
    Ok(RuntimeStreamEvent::Chunk(
        RuntimeStreamChunk::from_normalized_parts(
            json!({"id":"chunk-1","choices":[{"delta":{"content":text}}]}),
            usage,
            None,
            true,
            false,
        ),
    ))
}

pub(super) fn finish(reason: &str) -> ScriptedEvent {
    Ok(RuntimeStreamEvent::Chunk(
        RuntimeStreamChunk::from_normalized_parts(
            json!({"id":"chunk-1","choices":[{"delta":{},"finish_reason":reason}]}),
            None,
            Some(reason.to_owned()),
            false,
            false,
        ),
    ))
}

pub(super) fn terminal_usage(usage: NormalizedUsage) -> ScriptedEvent {
    let (input, output) = (usage.input_tokens(), usage.output_tokens());

    Ok(RuntimeStreamEvent::Chunk(
        RuntimeStreamChunk::from_normalized_parts(
            json!({"id":"chunk-1","choices":[],"usage":{
                "prompt_tokens":input,"completion_tokens":output,"total_tokens":input + output
            }}),
            Some(usage),
            None,
            false,
            true,
        ),
    ))
}

pub(super) fn successful_stream() -> Script {
    Script::Stream(vec![
        content("hi", Some(usage(10, 0, 1))),
        finish("stop"),
        terminal_usage(usage(10, 0, 2)),
        Ok(RuntimeStreamEvent::Done),
    ])
}

pub(super) struct Harness {
    pub(super) service: CompletionService,
    pub(super) state: Arc<RecordingServingState>,
    pub(super) journal: Journal,
    pub(super) request: QualifiedRequest,
    pub(super) external: Arc<ScriptedExternal>,
}

impl Harness {
    pub(super) fn new(
        request: QualifiedRequest,
        scripts: impl IntoIterator<Item = Script>,
    ) -> Self {
        let journal = Journal::default();
        let deployments = request
            .local
            .as_ref()
            .map_or_else(Vec::new, |local| local.deployments.clone());
        let state = Arc::new(RecordingServingState::serving(
            journal.clone(),
            &deployments,
        ));
        let runtime = Arc::new(ScriptedRuntime::new(scripts, journal.clone()));
        let service = CompletionService::new(
            state.clone(),
            runtime,
            ModelTokenizer::new().unwrap(),
            Arc::new(GatewayConfig::for_tests()),
        );

        let external = Arc::new(ScriptedExternal {
            scripts: Mutex::new(VecDeque::new()),
            journal: journal.clone(),
            requests: Mutex::new(Vec::new()),
        });

        Self {
            service: service.with_external_capacity(external.clone()),
            state,
            journal,
            request,
            external,
        }
    }

    /// Scripts OpenRouter's responses, in the order it receives requests.
    pub(super) fn openrouter(self, scripts: impl IntoIterator<Item = Script>) -> Self {
        self.external.scripts.lock().unwrap().extend(scripts);

        self
    }

    /// Every local deployment reports this status instead of a healthy one.
    pub(super) fn local_status(self, change: impl Fn(&mut DeploymentRuntimeStatus)) -> Self {
        for status in self.state.statuses.lock().unwrap().iter_mut() {
            change(status);
        }

        self
    }

    pub(super) fn finalizing(self, outcomes: impl IntoIterator<Item = FinalizationResult>) -> Self {
        *self.state.finalizations.lock().unwrap() = outcomes.into_iter().collect();

        self
    }

    pub(super) async fn complete(&self) -> Result<CompletionResult, GatewayError> {
        match self.service.complete(self.request.clone()).await? {
            CompletionResponse::NonStreaming { result, .. } => Ok(result),
            CompletionResponse::Streaming { .. } => panic!("expected a buffered response"),
        }
    }

    pub(super) async fn open(&self) -> Result<StreamingCompletion, GatewayError> {
        match self.service.complete(self.request.clone()).await? {
            CompletionResponse::Streaming { result, .. } => Ok(result),
            CompletionResponse::NonStreaming { .. } => panic!("expected a streaming response"),
        }
    }

    pub(super) async fn stream(&self) -> Result<Vec<StreamItem>, GatewayError> {
        Ok(self.open().await?.into_stream().collect().await)
    }

    pub(super) fn deployment_ids(&self) -> Vec<Uuid> {
        self.request
            .local_capacity()
            .deployments
            .iter()
            .map(|deployment| deployment.id)
            .collect()
    }

    pub(super) fn finalized(&self) -> Vec<Value> {
        self.state.finalized.lock().unwrap().clone()
    }

    pub(super) fn only_finalized(&self) -> Value {
        let finalized = self.finalized();
        assert_eq!(finalized.len(), 1, "{finalized:?}");

        finalized.into_iter().next().unwrap()
    }

    pub(super) fn metric(&self, name: &str, label: &str) -> u64 {
        self.service
            .metrics()
            .sample(name, label)
            .map_or(0, |value| u64::try_from(value).unwrap())
    }

    pub(super) async fn drained(&self) {
        tokio::time::timeout(Duration::from_secs(5), self.service.wait_for_drain())
            .await
            .expect("every generation task ends");
    }
}

pub(super) enum FinalizationResult {
    Unconfirmed,
    AlreadyAbsent,
    Panic,
}

impl FinalizationResult {
    pub(super) fn into_outcome(self) -> Result<FinalizationOutcome, FinalizationError> {
        match self {
            Self::Unconfirmed => Err(FinalizationError::UnknownScriptResult(99)),
            Self::AlreadyAbsent => Ok(FinalizationOutcome::AlreadyAbsent),
            Self::Panic => panic!("scripted finalization panic"),
        }
    }
}

pub(super) fn logged<'a>(events: &'a [Value], phase: &str) -> Vec<&'a Value> {
    events
        .iter()
        .filter(|event| event["fields"]["phase"] == phase)
        .collect()
}

impl QualifiedRequest {
    pub(super) fn streamed(mut self) -> Self {
        self.request.stream = true;

        self
    }
}
