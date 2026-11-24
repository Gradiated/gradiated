use std::sync::LazyLock;

use axum::response::{IntoResponse, Response};
use serde::Serialize;
use serde_json::Value;
use switchyard_translation::{
    StreamTranslationState, TranslationEngine, TranslationError, TranslationPolicy, WireFormat,
};

use crate::{
    diagnostics::{limited_error, limited_warn},
    error::GatewayError,
};

static ENGINE: LazyLock<TranslationEngine> = LazyLock::new(TranslationEngine::default);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Protocol {
    OpenAiChat,
    AnthropicMessages,
    OpenAiResponses,
}

#[derive(Clone, Debug, PartialEq)]
pub enum StreamItem {
    Chunk(Value),
    Error(GatewayError),
    Done,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Frame {
    pub event: Option<String>,
    pub data: String,
}

impl Frame {
    fn value(event: Option<&str>, value: &Value) -> Self {
        Self {
            event: event.map(ToOwned::to_owned),
            data: value.to_string(),
        }
    }

    fn error(event: Option<&str>, envelope: &impl Serialize) -> Self {
        Self {
            event: event.map(ToOwned::to_owned),
            data: serde_json::to_string(envelope)
                .expect("public error envelopes hold only strings"),
        }
    }

    fn raw(data: &str) -> Self {
        Self {
            event: None,
            data: data.to_owned(),
        }
    }
}

impl Protocol {
    fn wire(self) -> WireFormat {
        match self {
            Self::OpenAiChat => WireFormat::OpenAiChat,
            Self::AnthropicMessages => WireFormat::AnthropicMessages,
            Self::OpenAiResponses => WireFormat::OpenAiResponses,
        }
    }

    /// Local validation that must run before identity, so an unsupported request
    /// is refused in the caller's own error envelope.
    pub fn validate_request(self, request: &Value) -> Result<(), GatewayError> {
        if self == Self::OpenAiResponses {
            if let Some(field) = unsupported_responses_state(request) {
                return Err(GatewayError::invalid_request(Some(field)));
            }
        }

        Ok(())
    }

    pub fn translate_request(self, body: &Value) -> Result<Vec<u8>, GatewayError> {
        match self {
            Self::OpenAiChat => {
                serde_json::to_vec(body).map_err(|_| GatewayError::invalid_request(None))
            }
            Self::AnthropicMessages | Self::OpenAiResponses => {
                let output = ENGINE
                    .translate_request(
                        self.wire(),
                        WireFormat::OpenAiChat,
                        body,
                        &TranslationPolicy::default(),
                    )
                    .map_err(|error| {
                        limited_warn!(
                            protocol = ?self,
                            error_code = error.kind(),
                            "request translation failed"
                        );
                        GatewayError::invalid_request(None)
                    })?;

                let mut body = output.body;
                without_reasoning_details(&mut body);
                serde_json::to_vec(&body).map_err(|_| GatewayError::invalid_request(None))
            }
        }
    }

    pub fn translate_response(self, mut response: Value) -> Result<Value, GatewayError> {
        if self == Self::OpenAiChat {
            return Ok(response);
        }

        without_reasoning(&mut response);

        let mut body = ENGINE
            .translate_response(
                WireFormat::OpenAiChat,
                self.wire(),
                &response,
                &TranslationPolicy::default(),
            )
            .map(|output| output.body)
            .map_err(|error| self.completed_translation_failed(&error))?;

        if self == Self::AnthropicMessages {
            without_empty_text(&mut body);
        }

        self.copy_usage(&mut body, response.get("usage"));

        Ok(body)
    }

    pub fn stream_renderer(self) -> StreamRenderer {
        match self {
            Self::OpenAiChat => StreamRenderer::Passthrough,
            Self::AnthropicMessages | Self::OpenAiResponses => StreamRenderer::Translated {
                protocol: self,
                usage: None,
                state: Box::new(StreamTranslationState::new(
                    WireFormat::OpenAiChat,
                    self.wire(),
                )),
            },
        }
    }

    pub fn error_response(self, error: GatewayError) -> Response {
        match self {
            Self::OpenAiChat | Self::OpenAiResponses => error.into_response(),
            Self::AnthropicMessages => error.response_with(error.anthropic_envelope()),
        }
    }

    fn completed_translation_failed(self, error: &TranslationError) -> GatewayError {
        limited_error!(
            protocol = ?self,
            error_code = error.kind(),
            "response translation failed"
        );

        GatewayError::RuntimeUnavailable
    }

    fn error_frame(self, error: &GatewayError) -> Frame {
        match self {
            Self::OpenAiChat => Frame::error(None, &error.envelope()),
            Self::AnthropicMessages => Frame::error(Some("error"), &error.anthropic_envelope()),
            Self::OpenAiResponses => Frame::error(Some("error"), &error.responses_stream_error()),
        }
    }

    fn translated_frames(
        self,
        events: Result<Vec<Value>, TranslationError>,
        usage: Option<&Value>,
    ) -> Vec<Frame> {
        match events {
            Ok(events) => events
                .into_iter()
                .map(|mut event| {
                    match event["type"].as_str() {
                        Some("message_delta") => self.copy_usage(&mut event, usage),
                        Some("response.completed" | "response.incomplete") => {
                            self.copy_usage(&mut event["response"], usage)
                        }
                        _ => {}
                    }

                    self.named_frame(&event)
                })
                .collect(),
            Err(error) => vec![self.error_frame(&self.completed_translation_failed(&error))],
        }
    }

    fn copy_usage(self, response: &mut Value, chat_usage: Option<&Value>) {
        copy_usage_cost(response, chat_usage.and_then(|usage| usage.get("cost")));
        if self == Self::AnthropicMessages {
            if let (Some(usage), Some(reasoning)) = (
                response.get_mut("usage").and_then(Value::as_object_mut),
                chat_usage
                    .and_then(|usage| usage.pointer("/completion_tokens_details/reasoning_tokens"))
                    .and_then(Value::as_u64)
                    .filter(|tokens| *tokens > 0),
            ) {
                usage.insert(
                    "output_tokens_details".to_owned(),
                    serde_json::json!({"thinking_tokens": reasoning}),
                );
            }
        }

        if self != Self::OpenAiResponses {
            return;
        }

        if let (Some(details), Some(writes)) = (
            response
                .pointer_mut("/usage/input_tokens_details")
                .and_then(Value::as_object_mut),
            chat_usage.and_then(|usage| usage.pointer("/prompt_tokens_details/cache_write_tokens")),
        ) {
            details.insert("cache_write_tokens".to_owned(), writes.clone());
        }
    }

    fn named_frame(self, value: &Value) -> Frame {
        let name = value
            .get("type")
            .and_then(Value::as_str)
            .filter(|name| !name.is_empty())
            .unwrap_or("message");

        Frame::value(Some(name), value)
    }
}

pub enum StreamRenderer {
    Passthrough,
    Translated {
        protocol: Protocol,
        state: Box<StreamTranslationState>,
        usage: Option<Value>,
    },
}

impl StreamRenderer {
    pub fn render(&mut self, item: StreamItem) -> Vec<Frame> {
        match (self, item) {
            (Self::Passthrough, StreamItem::Chunk(value)) => vec![Frame::value(None, &value)],
            (Self::Passthrough, StreamItem::Done) => vec![Frame::raw("[DONE]")],
            (Self::Passthrough, StreamItem::Error(error)) => {
                vec![Protocol::OpenAiChat.error_frame(&error)]
            }
            (Self::Translated { protocol, .. }, StreamItem::Error(error)) => {
                vec![protocol.error_frame(&error)]
            }
            (
                Self::Translated {
                    protocol,
                    state,
                    usage,
                },
                StreamItem::Chunk(mut value),
            ) => {
                if value["usage"].is_object() {
                    *usage = Some(value["usage"].clone());
                }
                without_reasoning(&mut value);

                protocol.translated_frames(
                    ENGINE.translate_event(state, WireFormat::OpenAiChat, protocol.wire(), &value),
                    usage.as_ref(),
                )
            }
            (
                Self::Translated {
                    protocol,
                    state,
                    usage,
                },
                StreamItem::Done,
            ) => protocol
                .translated_frames(ENGINE.finish_stream(state, protocol.wire()), usage.as_ref()),
        }
    }
}

pub(crate) fn set_usage_cost(response: &mut Value, charge_nano_usd: u64) {
    let dollars = charge_nano_usd / 1_000_000_000;
    let nanos = charge_nano_usd % 1_000_000_000;
    let cost: serde_json::Number = format!("{dollars}.{nanos:09}")
        .parse()
        .expect("a nano-USD charge is a valid JSON number");

    copy_usage_cost(response, Some(&Value::Number(cost)));
}

fn copy_usage_cost(response: &mut Value, cost: Option<&Value>) {
    if let (Some(usage), Some(cost)) = (
        response.get_mut("usage").and_then(Value::as_object_mut),
        cost,
    ) {
        usage.insert("cost".to_owned(), cost.clone());
    }
}

/// Anthropic and OpenAI reject reasoning they did not produce, so reasoning goes
/// only to Chat Completions clients. Otherwise a thread cannot move to a provider.
fn without_reasoning(response: &mut Value) {
    let Some(choices) = response.get_mut("choices").and_then(Value::as_array_mut) else {
        return;
    };

    for choice in choices {
        for part in ["message", "delta"] {
            if let Some(fields) = choice.get_mut(part).and_then(Value::as_object_mut) {
                fields.remove("reasoning_content");
                fields.remove("reasoning");
            }
        }
    }
}

/// The translator carries another provider's opaque reasoning state, such as
/// OpenAI's encrypted reasoning, into Chat messages. Our runtimes cannot use it,
/// and it is not ours to forward.
fn without_reasoning_details(body: &mut Value) {
    let Some(messages) = body.get_mut("messages").and_then(Value::as_array_mut) else {
        return;
    };

    for message in messages.iter_mut() {
        if let Some(fields) = message.as_object_mut() {
            fields.remove("reasoning_details");
        }
    }

    // A turn that held only that state would otherwise reach the runtime as an
    // empty, completed assistant turn.
    messages.retain(|message| !is_empty_assistant_turn(message));
}

fn is_empty_assistant_turn(message: &Value) -> bool {
    let blank = |field: &str| match message.get(field) {
        None | Some(Value::Null) => true,
        Some(Value::String(text)) => text.is_empty(),
        Some(Value::Array(items)) => items.is_empty(),
        Some(_) => false,
    };

    message["role"] == "assistant"
        && ["content", "tool_calls", "reasoning", "reasoning_content"]
            .into_iter()
            .all(blank)
}

/// Anthropic rejects empty text blocks when a client sends the turn back.
fn without_empty_text(body: &mut Value) {
    let Some(content) = body.get_mut("content").and_then(Value::as_array_mut) else {
        return;
    };

    content.retain(|block| !(block["type"] == "text" && block["text"] == ""));
}

// The translator drops server-side state it cannot represent, so a stateful request
// would otherwise run without its context.
fn unsupported_responses_state(body: &Value) -> Option<&'static str> {
    const REFERENCES: [&str; 3] = ["previous_response_id", "conversation", "prompt"];
    const FLAGS: [&str; 2] = ["store", "background"];

    let referenced = REFERENCES
        .into_iter()
        .find(|field| !matches!(body.get(field), None | Some(Value::Null)));

    referenced.or_else(|| {
        FLAGS.into_iter().find(|field| {
            !matches!(
                body.get(field),
                None | Some(Value::Null) | Some(Value::Bool(false))
            )
        })
    })
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn chat_chunks() -> Vec<StreamItem> {
        vec![
            StreamItem::Chunk(json!({
                "id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"model-a",
                "choices":[{"index":0,"delta":{"role":"assistant","content":"hi"},"logprobs":null,"finish_reason":null}]
            })),
            StreamItem::Chunk(json!({
                "id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"model-a",
                "choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"stop"}]
            })),
            StreamItem::Chunk(json!({
                "id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"model-a",
                "choices":[],
                "usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12,
                    "prompt_tokens_details":{"cached_tokens":0},"completion_tokens_details":{"reasoning_tokens":0}}
            })),
            StreamItem::Done,
        ]
    }

    fn chat_completion() -> Value {
        json!({
            "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "model-a",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "logprobs": null, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
                "prompt_tokens_details": {"cached_tokens": 0}, "completion_tokens_details": {"reasoning_tokens": 0}}
        })
    }

    #[test]
    fn buffered_cost_survives_every_protocol_translation() {
        for protocol in [
            Protocol::OpenAiChat,
            Protocol::AnthropicMessages,
            Protocol::OpenAiResponses,
        ] {
            for charge in [0, 1, 1_234_567_890] {
                let mut response = chat_completion();
                set_usage_cost(&mut response, charge);
                let cost = response["usage"]["cost"].clone();

                let translated = protocol.translate_response(response).unwrap();
                assert_eq!(translated["usage"]["cost"], cost, "{protocol:?}");
                assert!(translated["usage"].is_object());
            }
        }
    }

    #[test]
    fn streaming_cost_survives_every_protocol_translation_only_in_terminal_usage() {
        for protocol in [
            Protocol::OpenAiChat,
            Protocol::AnthropicMessages,
            Protocol::OpenAiResponses,
        ] {
            let mut renderer = protocol.stream_renderer();
            let frames = chat_chunks()
                .into_iter()
                .flat_map(|mut item| {
                    if let StreamItem::Chunk(value) = &mut item {
                        set_usage_cost(value, 1_234_567_890);
                    }

                    renderer.render(item)
                })
                .collect::<Vec<_>>();
            let values = frames
                .iter()
                .filter_map(|frame| serde_json::from_str::<Value>(&frame.data).ok())
                .collect::<Vec<_>>();
            let costs = values
                .iter()
                .filter_map(|value| {
                    value
                        .pointer("/usage/cost")
                        .or_else(|| value.pointer("/response/usage/cost"))
                })
                .collect::<Vec<_>>();
            assert_eq!(costs, vec![&json!(1.23456789)], "{protocol:?}");
        }
    }

    #[test]
    fn responses_without_pricing_remain_without_cost() {
        for protocol in [
            Protocol::OpenAiChat,
            Protocol::AnthropicMessages,
            Protocol::OpenAiResponses,
        ] {
            let response = protocol.translate_response(chat_completion()).unwrap();
            assert!(response["usage"].get("cost").is_none());
        }
    }

    #[test]
    fn chat_stream_frames_data_only_and_terminates_with_done() {
        let mut renderer = Protocol::OpenAiChat.stream_renderer();
        let frames = chat_chunks()
            .into_iter()
            .flat_map(|item| renderer.render(item))
            .collect::<Vec<_>>();
        assert_eq!(frames.len(), 4);
        assert!(frames.iter().all(|frame| frame.event.is_none()));
        assert_eq!(frames[3].data, "[DONE]");
    }

    #[test]
    fn messages_stream_emits_the_anthropic_event_sequence() {
        let mut renderer = Protocol::AnthropicMessages.stream_renderer();
        let frames = chat_chunks()
            .into_iter()
            .flat_map(|item| renderer.render(item))
            .collect::<Vec<_>>();
        let events = frames
            .iter()
            .map(|frame| frame.event.as_deref().expect("anthropic frames are named"))
            .collect::<Vec<_>>();
        assert_eq!(
            events,
            [
                "message_start",
                "content_block_start",
                "content_block_delta",
                "content_block_stop",
                "message_delta",
                "message_stop",
            ]
        );
        let start = serde_json::from_str::<Value>(&frames[0].data).unwrap();
        assert_eq!(start["message"]["role"], "assistant");
        assert_eq!(start["message"]["model"], "model-a");
        let delta = serde_json::from_str::<Value>(&frames[2].data).unwrap();
        assert_eq!(delta["delta"]["type"], "text_delta");
        assert_eq!(delta["delta"]["text"], "hi");
        let message_delta = serde_json::from_str::<Value>(&frames[4].data).unwrap();
        assert_eq!(message_delta["delta"]["stop_reason"], "end_turn");
        assert_eq!(message_delta["usage"]["input_tokens"], 10);
        assert_eq!(message_delta["usage"]["output_tokens"], 2);
    }

    #[test]
    fn responses_stream_emits_the_responses_event_sequence() {
        let mut renderer = Protocol::OpenAiResponses.stream_renderer();
        let frames = chat_chunks()
            .into_iter()
            .flat_map(|item| renderer.render(item))
            .collect::<Vec<_>>();
        let events = frames
            .iter()
            .map(|frame| frame.event.as_deref().expect("responses frames are named"))
            .collect::<Vec<_>>();
        assert_eq!(events.first(), Some(&"response.created"));
        assert_eq!(events.last(), Some(&"response.completed"));
        assert!(events.contains(&"response.output_text.delta"));
        let completed = serde_json::from_str::<Value>(&frames.last().unwrap().data).unwrap();
        assert_eq!(completed["response"]["model"], "model-a");
        assert_eq!(completed["response"]["usage"]["input_tokens"], 10);
        assert_eq!(completed["response"]["usage"]["output_tokens"], 2);
    }

    #[test]
    fn error_frames_use_the_protocol_envelopes() {
        let mut chat = Protocol::OpenAiChat.stream_renderer();
        let chat_frame = chat
            .render(StreamItem::Error(GatewayError::InvalidApiKey))
            .remove(0);
        let chat_body = serde_json::from_str::<Value>(&chat_frame.data).unwrap();
        assert_eq!(chat_body["error"]["type"], "authentication_error");
        assert_eq!(chat_body["error"]["code"], "invalid_api_key");

        let mut messages = Protocol::AnthropicMessages.stream_renderer();
        let messages_frame = messages
            .render(StreamItem::Error(GatewayError::InvalidApiKey))
            .remove(0);
        assert_eq!(messages_frame.event.as_deref(), Some("error"));
        let messages_body = serde_json::from_str::<Value>(&messages_frame.data).unwrap();
        assert_eq!(messages_body["type"], "error");
        assert_eq!(messages_body["error"]["type"], "authentication_error");

        let mut responses = Protocol::OpenAiResponses.stream_renderer();
        let responses_frame = responses
            .render(StreamItem::Error(GatewayError::InvalidApiKey))
            .remove(0);
        assert_eq!(responses_frame.event.as_deref(), Some("error"));
        let responses_body = serde_json::from_str::<Value>(&responses_frame.data).unwrap();
        assert_eq!(responses_body["type"], "error");
        assert_eq!(responses_body["code"], "invalid_api_key");
    }

    #[test]
    fn messages_requests_translate_into_chat_completions_bodies() {
        let body = json!({
            "model": "model-a",
            "max_tokens": 32,
            "temperature": 0.5,
            "service_tier": "flex",
            "system": "be brief",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hello"}]},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "weather", "input": {"city": "Oslo"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": "21C"}]}]}
            ],
            "tools": [{"name": "weather", "description": "look up weather", "input_schema": {"type": "object"}}]
        });
        let translated = serde_json::from_slice::<Value>(
            &Protocol::AnthropicMessages
                .translate_request(&body)
                .unwrap(),
        )
        .unwrap();
        assert_eq!(translated["model"], "model-a");
        assert_eq!(translated["max_completion_tokens"], 32);
        assert_eq!(translated["temperature"], 0.5);
        assert_eq!(translated["service_tier"], "flex");
        assert_eq!(translated["messages"][0]["role"], "system");
        assert_eq!(translated["messages"][0]["content"], "be brief");
        assert_eq!(translated["messages"][1]["role"], "user");
        assert_eq!(translated["messages"][2]["role"], "assistant");
        assert_eq!(translated["messages"][2]["tool_calls"][0]["id"], "toolu_1");
        assert_eq!(translated["messages"][3]["role"], "tool");
        assert_eq!(translated["messages"][3]["tool_call_id"], "toolu_1");
        assert_eq!(translated["tools"][0]["type"], "function");
    }

    #[test]
    fn responses_requests_translate_into_chat_completions_bodies() {
        let body = json!({
            "model": "model-a",
            "max_output_tokens": 64,
            "instructions": "be brief",
            "input": "hello",
            "stream": true,
            "service_tier": "fast"
        });
        let translated = serde_json::from_slice::<Value>(
            &Protocol::OpenAiResponses.translate_request(&body).unwrap(),
        )
        .unwrap();
        assert_eq!(translated["model"], "model-a");
        assert_eq!(translated["max_completion_tokens"], 64);
        assert_eq!(translated["messages"][0]["role"], "system");
        assert_eq!(translated["messages"][0]["content"], "be brief");
        assert_eq!(translated["messages"][1]["role"], "user");
        assert_eq!(translated["messages"][1]["content"], "hello");
        assert_eq!(translated["stream"], true);
        assert_eq!(translated["service_tier"], "fast");
    }

    #[test]
    fn responses_requests_drop_another_providers_encrypted_reasoning() {
        let body = json!({
            "model": "model-a",
            "input": [
                {"role": "user", "content": "hello"},
                {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "gAAAA-secret"},
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]},
                {"role": "user", "content": "again"}
            ]
        });
        let translated = serde_json::from_slice::<Value>(
            &Protocol::OpenAiResponses.translate_request(&body).unwrap(),
        )
        .unwrap();
        assert!(!translated.to_string().contains("gAAAA-secret"));
        assert_eq!(translated["messages"][1]["role"], "assistant");
        assert_eq!(translated["messages"][1]["content"], "hi");
    }

    #[test]
    fn responses_requests_drop_turns_that_held_only_encrypted_reasoning() {
        let body = json!({
            "model": "model-a",
            "input": [
                {"role": "user", "content": "hello"},
                {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "gAAAA-secret"},
                {"role": "user", "content": "again"}
            ]
        });
        let translated = serde_json::from_slice::<Value>(
            &Protocol::OpenAiResponses.translate_request(&body).unwrap(),
        )
        .unwrap();
        assert_eq!(
            translated["messages"],
            json!([
                {"role": "user", "content": "hello"},
                {"role": "user", "content": "again"}
            ])
        );
    }

    #[test]
    fn responses_requests_reject_the_stateful_surface() {
        for (body, field) in [
            (json!({"store": true}), Some("store")),
            (
                json!({"previous_response_id": "resp_1"}),
                Some("previous_response_id"),
            ),
            (json!({"conversation": "c_1"}), Some("conversation")),
            (
                json!({"conversation": {"id": "conv_1"}}),
                Some("conversation"),
            ),
            (json!({"prompt": {"id": "pmpt_1"}}), Some("prompt")),
            (json!({"background": true}), Some("background")),
            (json!({"store": "yes"}), Some("store")),
            (json!({"store": false}), None),
            (json!({"background": false, "conversation": null}), None),
            (json!({"input": "hello"}), None),
        ] {
            assert_eq!(unsupported_responses_state(&body), field, "{body}");
        }
    }

    #[test]
    fn an_untranslatable_request_is_an_invalid_request() {
        for protocol in [Protocol::AnthropicMessages, Protocol::OpenAiResponses] {
            assert_eq!(
                protocol.translate_request(&json!([])),
                Err(GatewayError::invalid_request(None)),
                "{protocol:?}"
            );
        }
    }

    #[test]
    fn an_untranslatable_completion_is_a_runtime_failure() {
        assert_eq!(
            Protocol::AnthropicMessages.translate_response(json!([])),
            Err(GatewayError::RuntimeUnavailable)
        );
    }

    #[test]
    fn chat_responses_pass_through_and_other_responses_translate() {
        let chat = chat_completion();
        assert_eq!(
            Protocol::OpenAiChat
                .translate_response(chat.clone())
                .unwrap(),
            chat
        );

        let anthropic = Protocol::AnthropicMessages
            .translate_response(chat.clone())
            .unwrap();
        assert_eq!(anthropic["type"], "message");
        assert_eq!(anthropic["role"], "assistant");
        assert_eq!(anthropic["content"][0]["type"], "text");
        assert_eq!(anthropic["content"][0]["text"], "hi");
        assert_eq!(anthropic["stop_reason"], "end_turn");
        assert_eq!(anthropic["usage"]["input_tokens"], 10);
        assert_eq!(anthropic["usage"]["output_tokens"], 2);

        let responses = Protocol::OpenAiResponses.translate_response(chat).unwrap();
        assert_eq!(responses["object"], "response");
        assert_eq!(responses["status"], "completed");
        assert_eq!(responses["output"][0]["content"][0]["type"], "output_text");
        assert_eq!(responses["output"][0]["content"][0]["text"], "hi");
        assert_eq!(responses["usage"]["input_tokens"], 10);
    }

    const REASONING: &str = "private chain of thought";

    fn tool_call_with_reasoning() -> Value {
        json!({
            "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "model-a",
            "choices": [{"index": 0, "logprobs": null, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": null, "reasoning_content": REASONING, "reasoning": REASONING,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]
            }}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17,
                "completion_tokens_details": {"reasoning_tokens": 5}}
        })
    }

    fn streamed_tool_call_with_reasoning() -> Vec<StreamItem> {
        let chunk = |delta: Value, finish: Value| {
            StreamItem::Chunk(json!({
                "id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1, "model": "model-a",
                "choices": [{"index": 0, "delta": delta, "logprobs": null, "finish_reason": finish}]
            }))
        };

        vec![
            chunk(json!({"role": "assistant", "content": null}), Value::Null),
            chunk(json!({"reasoning_content": REASONING}), Value::Null),
            chunk(json!({"reasoning": REASONING}), Value::Null),
            chunk(
                json!({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"}}]}),
                Value::Null,
            ),
            chunk(json!({}), json!("tool_calls")),
            StreamItem::Done,
        ]
    }

    fn streamed(protocol: Protocol) -> String {
        let mut renderer = protocol.stream_renderer();

        streamed_tool_call_with_reasoning()
            .into_iter()
            .flat_map(|item| renderer.render(item))
            .map(|frame| frame.data)
            .collect::<Vec<_>>()
            .join("\n")
    }

    #[test]
    fn reasoning_never_reaches_messages_or_responses_clients() {
        for protocol in [Protocol::AnthropicMessages, Protocol::OpenAiResponses] {
            let buffered = protocol
                .translate_response(tool_call_with_reasoning())
                .unwrap()
                .to_string();

            for output in [buffered, streamed(protocol)] {
                assert!(!output.contains(REASONING), "{protocol:?}: {output}");
                assert!(!output.contains(r#""thinking""#), "{protocol:?}: {output}");
                assert!(!output.contains(r#""reasoning""#), "{protocol:?}: {output}");
                assert!(output.contains("read_file"), "{protocol:?}: {output}");
            }
        }
    }

    #[test]
    fn chat_clients_keep_reasoning_content() {
        let response = Protocol::OpenAiChat
            .translate_response(tool_call_with_reasoning())
            .unwrap();

        assert_eq!(
            response["choices"][0]["message"]["reasoning_content"],
            REASONING
        );
        assert!(streamed(Protocol::OpenAiChat).contains(REASONING));
    }

    #[test]
    fn a_messages_tool_call_carries_no_empty_text_block() {
        let response = Protocol::AnthropicMessages
            .translate_response(tool_call_with_reasoning())
            .unwrap();

        assert_eq!(
            response["content"],
            json!([{"type": "tool_use", "id": "call_1", "name": "read_file", "input": {}}])
        );
        assert_eq!(response["stop_reason"], "tool_use");
    }

    #[test]
    fn a_messages_turn_with_only_reasoning_has_empty_content() {
        let mut completion = tool_call_with_reasoning();
        completion["choices"][0]["message"]["tool_calls"] = Value::Null;
        completion["choices"][0]["finish_reason"] = json!("length");

        let response = Protocol::AnthropicMessages
            .translate_response(completion)
            .unwrap();

        assert_eq!(response["content"], json!([]));
    }

    #[test]
    fn messages_text_beside_a_tool_call_is_kept() {
        let mut completion = tool_call_with_reasoning();
        completion["choices"][0]["message"]["content"] = json!("Reading it now.");

        let response = Protocol::AnthropicMessages
            .translate_response(completion)
            .unwrap();

        assert_eq!(
            response["content"][0],
            json!({"type": "text", "text": "Reading it now."})
        );
        assert_eq!(response["content"][1]["type"], "tool_use");
    }

    #[test]
    fn reasoning_tokens_still_count_in_usage() {
        let response = Protocol::OpenAiResponses
            .translate_response(tool_call_with_reasoning())
            .unwrap();

        assert_eq!(response["usage"]["output_tokens"], 7);
        assert_eq!(
            response["usage"]["output_tokens_details"]["reasoning_tokens"],
            5
        );
    }
}
