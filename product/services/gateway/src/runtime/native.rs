//! Native token transport. The gateway renders and tokenizes the prompt, sends
//! token IDs, and decodes the output token IDs it receives back into text.

use async_trait::async_trait;
use chrono::Utc;
use reqwest::{header, Response};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use uuid::Uuid;

use super::{
    chat::{
        valid_finish_reason, Choice, NormalizedCompletionResponse, NormalizedStreamResponse,
        PublicUsage, StreamChoice,
    },
    client::{
        next_message, open_events, read_completion_body, rejected_response, send, Call,
        RuntimeEvents,
    },
    ChunkUsage, ProtocolViolation, RuntimeCompletion, RuntimeEventStream, RuntimeFailure,
    RuntimeFailureKind, RuntimeStreamChunk, RuntimeStreamEvent, SglangClient,
};
use crate::{tokenizer::TokenDecoder, InferenceRequest, NormalizedUsage};

const TOKEN_COMPLETIONS: &str = "v1/token-completions";

/// Native decoding is greedy, so any sampling parameter would be silently ignored.
const SAMPLING_PARAMETERS: &[&str] = &[
    "top_p",
    "top_k",
    "min_p",
    "seed",
    "frequency_penalty",
    "presence_penalty",
    "repetition_penalty",
];

impl SglangClient {
    pub(super) async fn complete_native(
        &self,
        call: Call<'_>,
        input_ids: &[u32],
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let requested_model = call.request.model.clone();
        let accepted = self.send_native(call, input_ids, false).await?;

        let body = read_completion_body(accepted.response).await?;
        let completion: NativeTokenResponse =
            serde_json::from_slice(&body).map_err(|_| ProtocolViolation::Json)?;

        completion
            .into_runtime_completion(accepted.decoder, requested_model, accepted.bounds)
            .await
    }

    pub(super) async fn stream_native(
        &self,
        call: Call<'_>,
        input_ids: &[u32],
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let requested_model = call.request.model.clone();
        let accepted = self.send_native(call, input_ids, true).await?;

        Ok(Box::new(NativeEventStream {
            events: open_events(accepted.response)?,
            decoder: accepted.decoder,
            requested_model,
            identity: ResponseIdentity::new(),
            bounds: accepted.bounds,
            output_tokens: 0,
            last_usage: NormalizedUsage::zero(),
            phase: Phase::Streaming { sent_role: false },
        }))
    }

    async fn send_native(
        &self,
        call: Call<'_>,
        input_ids: &[u32],
        stream: bool,
    ) -> Result<Accepted, RuntimeFailure> {
        let native = NativeRequest::new(&call.request, input_ids, call.output_tokens, stream)?;
        let decoder = self
            .tokenizer
            .decoder(&call.deployment.release)
            .await
            .map_err(|_| RuntimeFailure::tokenizer(RuntimeFailureKind::Unavailable))?;

        let accept = if stream {
            "text/event-stream"
        } else {
            "application/json"
        };
        // The native runtime's deliberately small HTTP/1.1 parser requires a
        // Content-Length body, so this must stay a byte body, not `one_shot_body`.
        let upstream = self
            .post(call.deployment, TOKEN_COMPLETIONS, native.body)
            .header(header::ACCEPT, accept);
        let response = send(upstream).await?;
        let status = response.status();
        if !status.is_success() {
            return Err(rejected_response(response).await);
        }

        Ok(Accepted {
            response,
            bounds: native.bounds,
            decoder,
        })
    }
}

struct Accepted {
    response: Response,
    bounds: TokenBounds,
    decoder: TokenDecoder,
}

struct NativeRequest {
    body: Vec<u8>,
    bounds: TokenBounds,
}

#[derive(Clone, Copy)]
struct TokenBounds {
    input_tokens: usize,
    max_tokens: usize,
}

impl NativeRequest {
    fn new(
        request: &InferenceRequest,
        input_ids: &[u32],
        effective_output_tokens: u64,
        stream: bool,
    ) -> Result<Self, RuntimeFailure> {
        if let Some(parameter) = sampling_parameter(request) {
            return Err(RuntimeFailure::invalid_parameter(parameter));
        }

        let max_tokens = usize::try_from(effective_output_tokens)
            .map_err(|_| RuntimeFailure::invalid_parameter("max_tokens"))?;
        let body = serde_json::to_vec(&NativeTokenRequest {
            input_ids,
            max_tokens,
            stream,
            priority: request.service_tier.runtime_priority(),
        })
        .map_err(|_| ProtocolViolation::Json)?;

        Ok(Self {
            body,
            bounds: TokenBounds {
                input_tokens: input_ids.len(),
                max_tokens,
            },
        })
    }
}

fn sampling_parameter(request: &InferenceRequest) -> Option<&'static str> {
    let sampled_temperature = request
        .parameters
        .get("temperature")
        .is_some_and(|value| value.as_f64() != Some(0.0));
    if sampled_temperature {
        return Some("temperature");
    }

    SAMPLING_PARAMETERS
        .iter()
        .copied()
        .find(|name| request.parameters.contains_key(*name))
}

#[derive(Serialize)]
struct NativeTokenRequest<'a> {
    input_ids: &'a [u32],
    max_tokens: usize,
    stream: bool,
    priority: i64,
}

struct ResponseIdentity {
    id: String,
    created: u64,
}

impl ResponseIdentity {
    fn new() -> Self {
        Self {
            id: format!("chatcmpl-{}", Uuid::now_v7()),
            created: u64::try_from(Utc::now().timestamp()).unwrap_or_default(),
        }
    }
}

#[derive(Deserialize)]
struct NativeTokenResponse {
    output_ids: Vec<u32>,
    usage: NativeTokenUsage,
    finish_reason: String,
}

impl NativeTokenResponse {
    async fn into_runtime_completion(
        self,
        decoder: TokenDecoder,
        requested_model: String,
        bounds: TokenBounds,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        if self.output_ids.len() > bounds.max_tokens {
            return Err(ProtocolViolation::TokenBounds.into());
        }

        if !valid_finish_reason(&self.finish_reason) {
            return Err(ProtocolViolation::FinishReason.into());
        }

        let usage = self
            .usage
            .normalize(bounds.input_tokens, self.output_ids.len())?;
        let content = decoder.decode(self.output_ids).await.map_err(|_| {
            RuntimeFailure::tokenizer(RuntimeFailureKind::Interrupted).or_usage(usage)
        })?;

        let identity = ResponseIdentity::new();
        let response = serde_json::to_value(NormalizedCompletionResponse {
            id: identity.id,
            object: "chat.completion".to_owned(),
            created: identity.created,
            model: requested_model,
            choices: vec![Choice {
                index: 0,
                message: Map::from_iter([
                    ("role".to_owned(), Value::String("assistant".to_owned())),
                    ("content".to_owned(), Value::String(content)),
                ]),
                logprobs: None,
                finish_reason: self.finish_reason.clone(),
            }],
            usage: usage.into(),
        })
        .map_err(|_| ProtocolViolation::Json)?;

        Ok(RuntimeCompletion {
            response,
            finish_reason: self.finish_reason,
            usage,
            upstream_cost_nano_usd: None,
        })
    }
}

#[derive(Deserialize)]
struct NativeTokenUsage {
    input_tokens: usize,
    cached_input_tokens: usize,
    output_tokens: usize,
}

impl NativeTokenUsage {
    /// The runtime's counters must match the tokens the gateway sent and
    /// received, because settlement bills from them.
    fn normalize(
        &self,
        input_tokens: usize,
        output_tokens: usize,
    ) -> Result<NormalizedUsage, RuntimeFailure> {
        if self.input_tokens != input_tokens
            || self.cached_input_tokens > self.input_tokens
            || self.output_tokens != output_tokens
        {
            return Err(ProtocolViolation::Usage.into());
        }

        NormalizedUsage::new(
            input_tokens as u64,
            self.cached_input_tokens as u64,
            0,
            output_tokens as u64,
            0,
        )
        .map_err(|_| ProtocolViolation::Usage.into())
    }
}

// Without deny_unknown_fields, a frame carrying both token_id and
// finish_reason would parse as a terminal frame and drop its token.
#[derive(Deserialize)]
#[serde(untagged)]
enum NativeFrame {
    Token(TokenFrame),
    Terminal(TerminalFrame),
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TokenFrame {
    token_id: u32,
    usage: NativeTokenUsage,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TerminalFrame {
    finish_reason: String,
    usage: NativeTokenUsage,
}

enum Phase {
    Streaming { sent_role: bool },
    Finished(RuntimeStreamChunk),
    AwaitingDone,
    Done,
}

struct NativeEventStream {
    events: RuntimeEvents,
    decoder: TokenDecoder,
    requested_model: String,
    identity: ResponseIdentity,
    bounds: TokenBounds,
    output_tokens: usize,
    last_usage: NormalizedUsage,
    phase: Phase,
}

#[async_trait]
impl RuntimeEventStream for NativeEventStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        let event = self.advance().await;

        event.map_err(|failure| failure.or_usage(self.last_usage))
    }
}

impl NativeEventStream {
    async fn advance(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        loop {
            match std::mem::replace(&mut self.phase, Phase::Done) {
                Phase::Done => return Ok(None),
                Phase::Finished(usage) => {
                    self.phase = Phase::AwaitingDone;
                    return Ok(Some(RuntimeStreamEvent::Chunk(usage)));
                }
                Phase::AwaitingDone => {
                    let data = next_message(&mut self.events).await?;
                    if data.as_deref() != Some("[DONE]") {
                        return Err(ProtocolViolation::FrameOrder.into());
                    }

                    return Ok(Some(RuntimeStreamEvent::Done));
                }
                Phase::Streaming { sent_role } => {
                    let data = next_message(&mut self.events)
                        .await?
                        .filter(|data| data != "[DONE]")
                        .ok_or(ProtocolViolation::FrameOrder)?;
                    if self.output_tokens == 0 {
                        crate::diagnostics::body::record(
                            "runtime_response_first_frame",
                            data.as_bytes(),
                            Some(200),
                        );
                    }
                    let frame: NativeFrame = serde_json::from_str(&data).map_err(|_| {
                        crate::diagnostics::body::record(
                            "runtime_response_invalid_frame",
                            data.as_bytes(),
                            Some(200),
                        );
                        ProtocolViolation::Json
                    })?;
                    if matches!(frame, NativeFrame::Terminal(_)) {
                        crate::diagnostics::body::record(
                            "runtime_response_terminal_frame",
                            data.as_bytes(),
                            Some(200),
                        );
                    }

                    match frame {
                        NativeFrame::Token(token) => {
                            self.phase = Phase::Streaming { sent_role };

                            if let Some(content) = self.decode(token).inspect_err(|_| {
                                crate::diagnostics::body::record(
                                    "runtime_response_invalid_frame",
                                    data.as_bytes(),
                                    Some(200),
                                );
                            })? {
                                let chunk = self.content_chunk(content, !sent_role)?;
                                self.phase = Phase::Streaming { sent_role: true };
                                return Ok(Some(RuntimeStreamEvent::Chunk(chunk)));
                            }
                        }
                        NativeFrame::Terminal(terminal) => {
                            let (finish, usage) = self.finish(terminal).inspect_err(|_| {
                                crate::diagnostics::body::record(
                                    "runtime_response_invalid_frame",
                                    data.as_bytes(),
                                    Some(200),
                                );
                            })?;
                            self.phase = Phase::Finished(usage);
                            return Ok(Some(RuntimeStreamEvent::Chunk(finish)));
                        }
                    }
                }
            }
        }
    }

    fn decode(&mut self, token: TokenFrame) -> Result<Option<String>, RuntimeFailure> {
        self.output_tokens += 1;
        if self.output_tokens > self.bounds.max_tokens {
            return Err(ProtocolViolation::TokenBounds.into());
        }

        self.last_usage = token
            .usage
            .normalize(self.bounds.input_tokens, self.output_tokens)?;

        self.decoder
            .step(token.token_id)
            .map_err(|_| RuntimeFailure::tokenizer(RuntimeFailureKind::Interrupted))
    }

    fn content_chunk(
        &self,
        content: String,
        with_role: bool,
    ) -> Result<RuntimeStreamChunk, RuntimeFailure> {
        let mut delta = Map::new();
        if with_role {
            delta.insert("role".to_owned(), Value::String("assistant".to_owned()));
        }

        let usable_output = !content.is_empty();
        delta.insert("content".to_owned(), Value::String(content));

        Ok(RuntimeStreamChunk {
            response: self.choice_envelope(delta, None)?,
            finish_reason: None,
            usable_output,
            usage: Some(ChunkUsage::Running(self.last_usage)),
            upstream_cost_nano_usd: None,
        })
    }

    fn finish(
        &mut self,
        terminal: TerminalFrame,
    ) -> Result<(RuntimeStreamChunk, RuntimeStreamChunk), RuntimeFailure> {
        if !valid_finish_reason(&terminal.finish_reason) {
            return Err(ProtocolViolation::FinishReason.into());
        }

        let usage = terminal
            .usage
            .normalize(self.bounds.input_tokens, self.output_tokens)?;
        self.last_usage = usage;

        let finish = RuntimeStreamChunk {
            response: self.choice_envelope(Map::new(), Some(terminal.finish_reason.clone()))?,
            finish_reason: Some(terminal.finish_reason),
            usable_output: false,
            usage: None,
            upstream_cost_nano_usd: None,
        };
        let usage = RuntimeStreamChunk {
            response: self.envelope(Vec::new(), Some(usage.into()))?,
            finish_reason: None,
            usable_output: false,
            usage: Some(ChunkUsage::Terminal(usage)),
            upstream_cost_nano_usd: None,
        };

        Ok((finish, usage))
    }

    fn choice_envelope(
        &self,
        delta: Map<String, Value>,
        finish_reason: Option<String>,
    ) -> Result<Value, RuntimeFailure> {
        let choice = StreamChoice {
            index: 0,
            delta,
            logprobs: None,
            finish_reason,
        };

        self.envelope(vec![choice], None)
    }

    fn envelope(
        &self,
        choices: Vec<StreamChoice>,
        usage: Option<PublicUsage>,
    ) -> Result<Value, RuntimeFailure> {
        serde_json::to_value(NormalizedStreamResponse {
            id: self.identity.id.clone(),
            object: "chat.completion.chunk".to_owned(),
            created: self.identity.created,
            model: self.requested_model.clone(),
            choices,
            usage,
        })
        .map_err(|_| ProtocolViolation::Json.into())
    }
}
