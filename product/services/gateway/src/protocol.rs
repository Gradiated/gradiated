use serde_json::{json, Value};
use switchyard_translation::{
    FormatRegistry, StreamTranslationState, TranslationEngine, TranslationPolicy, WireFormat,
};

use crate::error::GatewayError;

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
    fn json(value: &impl serde::Serialize) -> Self {
        Self {
            event: None,
            data: serde_json::to_string(value).expect("protocol values always serialize"),
        }
    }

    fn named(event: &str, value: &impl serde::Serialize) -> Self {
        Self {
            event: Some(event.to_owned()),
            data: serde_json::to_string(value).expect("protocol values always serialize"),
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
    pub fn label(self) -> &'static str {
        match self {
            Self::OpenAiChat => "chat_completions",
            Self::AnthropicMessages => "messages",
            Self::OpenAiResponses => "responses",
        }
    }

    fn wire(self) -> WireFormat {
        match self {
            Self::OpenAiChat => WireFormat::OpenAiChat,
            Self::AnthropicMessages => WireFormat::AnthropicMessages,
            Self::OpenAiResponses => WireFormat::OpenAiResponses,
        }
    }

    fn engine() -> TranslationEngine {
        TranslationEngine::new(FormatRegistry::with_builtins())
    }

    pub fn translate_request(self, body: &Value) -> Result<Vec<u8>, GatewayError> {
        match self {
            Self::OpenAiChat => {
                serde_json::to_vec(body).map_err(|_| GatewayError::invalid_request(None))
            }
            Self::AnthropicMessages | Self::OpenAiResponses => {
                let mut output = Self::engine()
                    .translate_request(self.wire(), WireFormat::OpenAiChat, body, &policy())
                    .map_err(|_| GatewayError::invalid_request(None))?;
                if let Some(service_tier) = body.get("service_tier") {
                    output
                        .body
                        .as_object_mut()
                        .ok_or_else(|| GatewayError::invalid_request(None))?
                        .insert("service_tier".to_owned(), service_tier.clone());
                }
                serde_json::to_vec(&output.body).map_err(|_| GatewayError::invalid_request(None))
            }
        }
    }

    pub fn translate_response(self, response: Value) -> Result<Value, GatewayError> {
        match self {
            Self::OpenAiChat => Ok(response),
            Self::AnthropicMessages | Self::OpenAiResponses => {
                let output = Self::engine()
                    .translate_response(WireFormat::OpenAiChat, self.wire(), &response, &policy())
                    .map_err(|_| GatewayError::RuntimeUnavailable)?;
                Ok(output.body)
            }
        }
    }

    pub fn stream_renderer(self) -> StreamRenderer {
        StreamRenderer {
            protocol: self,
            engine: Self::engine(),
            state: match self {
                Self::OpenAiChat => None,
                Self::AnthropicMessages | Self::OpenAiResponses => Some(
                    StreamTranslationState::new(WireFormat::OpenAiChat, self.wire()),
                ),
            },
        }
    }

    pub fn error_response(self, error: GatewayError) -> axum::response::Response {
        use axum::{response::IntoResponse, Json};
        let status = error.status();
        match self {
            Self::OpenAiChat | Self::OpenAiResponses => {
                (status, Json(error.envelope())).into_response()
            }
            Self::AnthropicMessages => (status, Json(error.anthropic_envelope())).into_response(),
        }
    }

    fn error_frame(&self, error: &GatewayError) -> Frame {
        match self {
            Self::OpenAiChat => Frame {
                event: None,
                data: serde_json::to_string(&error.envelope())
                    .expect("the bounded public error envelope always serializes"),
            },
            Self::AnthropicMessages => Frame::named("error", &error.anthropic_envelope()),
            Self::OpenAiResponses => Frame::named(
                "error",
                &json!({
                    "type": "error",
                    "code": error.code(),
                    "message": error.message(),
                    "param": error.param(),
                }),
            ),
        }
    }

    fn frame(&self, value: &Value) -> Frame {
        match self {
            Self::OpenAiChat => Frame::json(value),
            Self::AnthropicMessages | Self::OpenAiResponses => {
                let name = value
                    .get("type")
                    .and_then(Value::as_str)
                    .filter(|name| !name.is_empty())
                    .unwrap_or("message");
                Frame::named(name, value)
            }
        }
    }
}

fn policy() -> TranslationPolicy {
    TranslationPolicy::default()
}

pub struct StreamRenderer {
    protocol: Protocol,
    engine: TranslationEngine,
    state: Option<StreamTranslationState>,
}

impl StreamRenderer {
    pub fn render(&mut self, item: StreamItem) -> Vec<Frame> {
        match (&mut self.state, item) {
            (None, StreamItem::Chunk(value)) => vec![self.protocol.frame(&value)],
            (None, StreamItem::Error(error)) => vec![self.protocol.error_frame(&error)],
            (None, StreamItem::Done) => vec![Frame::raw("[DONE]")],
            (Some(state), StreamItem::Chunk(value)) => self
                .engine
                .translate_event(state, WireFormat::OpenAiChat, self.protocol.wire(), &value)
                .unwrap_or_default()
                .iter()
                .map(|event| self.protocol.frame(event))
                .collect(),
            (Some(_), StreamItem::Error(error)) => vec![self.protocol.error_frame(&error)],
            (Some(state), StreamItem::Done) => self
                .engine
                .finish_stream(state, self.protocol.wire())
                .unwrap_or_default()
                .iter()
                .map(|event| self.protocol.frame(event))
                .collect(),
        }
    }
}

pub fn responses_use_unsupported_state(body: &Value) -> bool {
    const STATEFUL_FIELDS: [&str; 3] = ["store", "previous_response_id", "conversation"];
    STATEFUL_FIELDS.iter().any(|field| {
        matches!(
            body.get(field),
            Some(Value::String(_)) | Some(Value::Bool(true))
        )
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
    fn responses_requests_reject_the_stateful_surface() {
        assert!(responses_use_unsupported_state(&json!({"store": true})));
        assert!(responses_use_unsupported_state(
            &json!({"previous_response_id": "resp_1"})
        ));
        assert!(responses_use_unsupported_state(
            &json!({"conversation": "c_1"})
        ));
        assert!(!responses_use_unsupported_state(&json!({"store": false})));
        assert!(!responses_use_unsupported_state(&json!({"input": "hello"})));
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
}
