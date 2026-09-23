//! Native token transport. The gateway renders and tokenizes the prompt, sends
//! token IDs, and decodes the output token IDs it receives back into text.

use std::{collections::VecDeque, time::Duration};

use async_trait::async_trait;
use chrono::Utc;
use reqwest::header;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use uuid::Uuid;

use super::{
    chat::{
        NormalizedChoice, NormalizedCompletionResponse, NormalizedStreamChoice,
        NormalizedStreamResponse, PublicUsage,
    },
    client::{next_message, open_events, read_bounded_body, send, RuntimeEvents},
    RuntimeCompletion, RuntimeEventStream, RuntimeFailure, RuntimeFailureKind, RuntimeStreamChunk,
    RuntimeStreamEvent, SglangClient,
};
use crate::{
    tokenizer::TokenizerDecodeState, GatewayModelDeployment, InferenceRequest,
    ModelDeploymentRelease, ModelTokenizer, NormalizedUsage,
};

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
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let native = NativeRequest::new(&request, effective_output_tokens, false)?;
        let tokenizer = self.tokenizer()?;

        // The native runtime's deliberately small HTTP/1.1 parser requires a
        // bounded Content-Length body and does not accept chunked request framing.
        let upstream = self
            .post(deployment, TOKEN_COMPLETIONS, native.body)
            .header(header::ACCEPT, "application/json");
        let response = send(upstream, response_header_timeout).await?;
        let status = response.status();
        if !status.is_success() {
            return Err(RuntimeFailure::rejected(status, NormalizedUsage::zero()));
        }

        let body = read_bounded_body(response).await?;
        let completion: NativeTokenResponse =
            serde_json::from_slice(&body).map_err(|_| RuntimeFailure::protocol_violation())?;

        completion
            .into_runtime_completion(tokenizer, &deployment.release, request.model, native.bounds)
            .await
    }

    pub(super) async fn stream_native(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let native = NativeRequest::new(&request, effective_output_tokens, true)?;
        let tokenizer = self.tokenizer()?.clone();

        // Streaming applies to the response; the request body stays
        // length-delimited in both modes.
        let upstream = self
            .post(deployment, TOKEN_COMPLETIONS, native.body)
            .header(header::ACCEPT, "text/event-stream");
        let response = send(upstream, response_header_timeout).await?;
        let status = response.status();
        if !status.is_success() {
            return Err(RuntimeFailure::rejected(status, NormalizedUsage::zero()));
        }

        Ok(Box::new(NativeEventStream {
            events: open_events(response)?,
            tokenizer,
            release: deployment.release.clone(),
            requested_model: request.model,
            response_id: format!("chatcmpl-{}", Uuid::now_v7()),
            created: Utc::now().timestamp().try_into().unwrap_or(0),
            bounds: native.bounds,
            output_tokens: 0,
            decode_state: TokenizerDecodeState::default(),
            pending: VecDeque::new(),
            terminal_received: false,
            done: false,
            sent_role: false,
        }))
    }
}

/// A serialized token request and the bounds its response is checked against.
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
        effective_output_tokens: u64,
        stream: bool,
    ) -> Result<Self, RuntimeFailure> {
        let sampled = request
            .parameters
            .get("temperature")
            .is_some_and(|value| value.as_f64() != Some(0.0))
            || SAMPLING_PARAMETERS
                .iter()
                .any(|name| request.parameters.contains_key(*name));
        if sampled {
            return Err(RuntimeFailure::new(RuntimeFailureKind::InvalidRequest));
        }

        let input_ids = request
            .encoded_input_ids
            .as_deref()
            .ok_or_else(RuntimeFailure::protocol_violation)?;
        let max_tokens = usize::try_from(effective_output_tokens)
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::InvalidRequest))?;
        let body = serde_json::to_vec(&NativeTokenRequest {
            input_ids,
            max_tokens,
            stream,
            priority: request.service_tier.runtime_priority(),
        })
        .map_err(|_| RuntimeFailure::protocol_violation())?;

        Ok(Self {
            body,
            bounds: TokenBounds {
                input_tokens: input_ids.len(),
                max_tokens,
            },
        })
    }
}

#[derive(Serialize)]
struct NativeTokenRequest<'a> {
    input_ids: &'a [u32],
    max_tokens: usize,
    stream: bool,
    priority: i64,
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
        tokenizer: &ModelTokenizer,
        release: &ModelDeploymentRelease,
        requested_model: String,
        bounds: TokenBounds,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        if self.output_ids.len() > bounds.max_tokens || self.finish_reason.is_empty() {
            return Err(RuntimeFailure::protocol_violation());
        }

        let usage = self
            .usage
            .normalize(bounds.input_tokens, self.output_ids.len())?;
        let content = tokenizer
            .decode(release, self.output_ids)
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let created = u64::try_from(Utc::now().timestamp())
            .map_err(|_| RuntimeFailure::protocol_violation())?;

        let response = serde_json::to_value(NormalizedCompletionResponse {
            id: format!("chatcmpl-{}", Uuid::now_v7()),
            object: "chat.completion".to_owned(),
            created,
            model: requested_model,
            choices: vec![NormalizedChoice {
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
        .map_err(|_| RuntimeFailure::protocol_violation())?;

        Ok(RuntimeCompletion {
            response,
            finish_reason: self.finish_reason,
            usage,
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
            return Err(RuntimeFailure::protocol_violation());
        }

        NormalizedUsage::new(
            input_tokens as u64,
            self.cached_input_tokens as u64,
            0,
            output_tokens as u64,
            0,
        )
        .map_err(|_| RuntimeFailure::protocol_violation())
    }
}

#[derive(Deserialize)]
struct NativeStreamTerminal {
    finish_reason: String,
    usage: NativeTokenUsage,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NativeStreamToken {
    token_id: u32,
    usage: NativeTokenUsage,
}

/// Emits one chunk per decoded piece of text, then a finish chunk followed by a
/// usage chunk, then `Done`.
struct NativeEventStream {
    events: RuntimeEvents,
    tokenizer: ModelTokenizer,
    release: ModelDeploymentRelease,
    requested_model: String,
    response_id: String,
    created: u64,
    bounds: TokenBounds,
    output_tokens: usize,
    decode_state: TokenizerDecodeState,
    pending: VecDeque<RuntimeStreamEvent>,
    terminal_received: bool,
    done: bool,
    sent_role: bool,
}

#[async_trait]
impl RuntimeEventStream for NativeEventStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        if let Some(event) = self.pending.pop_front() {
            return Ok(Some(event));
        }

        if self.done {
            return Ok(None);
        }

        loop {
            let Some(data) = next_message(&mut self.events).await? else {
                return Err(RuntimeFailure::protocol_violation());
            };

            if data == "[DONE]" {
                if !self.terminal_received {
                    return Err(RuntimeFailure::protocol_violation());
                }

                self.done = true;
                return Ok(Some(RuntimeStreamEvent::Done));
            }

            let value: Value =
                serde_json::from_str(&data).map_err(|_| RuntimeFailure::protocol_violation())?;
            if value.get("token_id").is_none() {
                return self.terminal(value).map(Some);
            }

            if let Some(chunk) = self.token(value).await? {
                return Ok(Some(RuntimeStreamEvent::Chunk(chunk)));
            }
        }
    }
}

impl NativeEventStream {
    /// Decodes one output token. Returns nothing while the token has not yet
    /// completed any text.
    async fn token(&mut self, value: Value) -> Result<Option<RuntimeStreamChunk>, RuntimeFailure> {
        let token: NativeStreamToken =
            serde_json::from_value(value).map_err(|_| RuntimeFailure::protocol_violation())?;
        if self.terminal_received {
            return Err(RuntimeFailure::protocol_violation());
        }

        self.output_tokens += 1;
        if self.output_tokens > self.bounds.max_tokens {
            return Err(RuntimeFailure::protocol_violation());
        }

        let usage = token
            .usage
            .normalize(self.bounds.input_tokens, self.output_tokens)?;

        let state = std::mem::take(&mut self.decode_state);
        let (state, decoded) = self
            .tokenizer
            .decode_step(&self.release, state, token.token_id)
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        self.decode_state = state;
        let Some(content) = decoded else {
            return Ok(None);
        };

        let mut delta = Map::new();
        if !self.sent_role {
            delta.insert("role".to_owned(), Value::String("assistant".to_owned()));
            self.sent_role = true;
        }
        let usable_output = !content.is_empty();
        delta.insert("content".to_owned(), Value::String(content));

        Ok(Some(RuntimeStreamChunk {
            response: self.response(delta, None),
            usage: Some(usage),
            finish_reason: None,
            usable_output,
            terminal_usage: false,
        }))
    }

    /// Returns the finish chunk and queues the terminal usage chunk behind it.
    fn terminal(&mut self, value: Value) -> Result<RuntimeStreamEvent, RuntimeFailure> {
        let terminal: NativeStreamTerminal =
            serde_json::from_value(value).map_err(|_| RuntimeFailure::protocol_violation())?;
        if self.terminal_received || terminal.finish_reason.is_empty() {
            return Err(RuntimeFailure::protocol_violation());
        }

        let usage = terminal
            .usage
            .normalize(self.bounds.input_tokens, self.output_tokens)?;
        self.terminal_received = true;

        let finish = RuntimeStreamChunk {
            response: self.response(Map::new(), Some(terminal.finish_reason.clone())),
            usage: None,
            finish_reason: Some(terminal.finish_reason),
            usable_output: false,
            terminal_usage: false,
        };
        let terminal_usage = RuntimeStreamChunk {
            response: self.usage_response(usage),
            usage: Some(usage),
            finish_reason: None,
            usable_output: false,
            terminal_usage: true,
        };
        self.pending
            .push_back(RuntimeStreamEvent::Chunk(terminal_usage));

        Ok(RuntimeStreamEvent::Chunk(finish))
    }

    fn response(&self, delta: Map<String, Value>, finish_reason: Option<String>) -> Value {
        self.envelope(
            vec![NormalizedStreamChoice {
                index: 0,
                delta,
                logprobs: None,
                finish_reason,
            }],
            None,
        )
    }

    fn usage_response(&self, usage: NormalizedUsage) -> Value {
        self.envelope(Vec::new(), Some(usage.into()))
    }

    fn envelope(&self, choices: Vec<NormalizedStreamChoice>, usage: Option<PublicUsage>) -> Value {
        serde_json::to_value(NormalizedStreamResponse {
            id: self.response_id.clone(),
            object: "chat.completion.chunk".to_owned(),
            created: self.created,
            model: self.requested_model.clone(),
            choices,
            usage,
        })
        .expect("normalized native stream response is serializable")
    }
}
