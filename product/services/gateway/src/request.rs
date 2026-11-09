use serde::Deserialize;
use serde_json::{Map, Value};
use validator::Validate;

use crate::{json::strict_json, GatewayError, ServiceTier};

const MAX_SAFE_JSON_INTEGER: u64 = 9_007_199_254_740_991;

fn strict_object(body: &[u8]) -> Result<Map<String, Value>, GatewayError> {
    match strict_json(body) {
        Ok(Value::Object(fields)) => Ok(fields),
        _ => Err(GatewayError::invalid_request(None)),
    }
}

pub struct RequestTarget {
    pub request: Value,
    pub model: String,
}

pub fn parse_target(body: &[u8]) -> Result<RequestTarget, GatewayError> {
    let fields = strict_object(body)?;

    let Some(Value::String(model)) = fields.get("model") else {
        return Err(GatewayError::invalid_request(Some("model")));
    };

    if model.is_empty() {
        return Err(GatewayError::invalid_request(Some("model")));
    }

    Ok(RequestTarget {
        model: model.clone(),
        request: Value::Object(fields),
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RequestKind {
    Chat,
    SystemOne,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
pub struct InferenceRequest {
    #[validate(length(min = 1, max = 300))]
    pub model: String,
    #[validate(length(min = 1))]
    pub messages: Vec<Value>,
    #[serde(default)]
    pub stream: bool,
    #[serde(default)]
    pub service_tier: ServiceTier,
    #[validate(length(min = 1, max = 256))]
    pub session_id: Option<String>,
    #[validate(range(min = 1_u64, max = MAX_SAFE_JSON_INTEGER))]
    pub max_completion_tokens: Option<u64>,
    #[validate(range(min = 1_u64, max = MAX_SAFE_JSON_INTEGER))]
    pub max_tokens: Option<u64>,
    #[serde(flatten)]
    pub parameters: Map<String, Value>,
    #[serde(skip)]
    pub(crate) encoded_input_ids: Option<Vec<u32>>,
    #[serde(skip)]
    pub(crate) runtime_model_name: Option<String>,
    #[serde(skip)]
    pub(crate) decision: Option<crate::systemone::SystemOneRequest>,
    /// Moonshot Partial Mode: the final assistant message is a prefix the
    /// model continues. Set by the coordinator for models that support it.
    #[serde(skip)]
    pub(crate) continue_final_message: bool,
    /// The caller set no output limit and the model lets its runtime use the
    /// remaining context, up to the runtime's own maximum, instead of the
    /// catalog default. Set by the coordinator.
    #[serde(skip)]
    pub(crate) open_output_limit: bool,
}

impl InferenceRequest {
    pub fn parse_kind(body: &[u8], kind: RequestKind) -> Result<Self, GatewayError> {
        match kind {
            RequestKind::Chat => Self::parse(body),
            RequestKind::SystemOne => Self::parse_decision(body),
        }
    }

    fn parse_decision(body: &[u8]) -> Result<Self, GatewayError> {
        let decision = crate::systemone::SystemOneRequest::parse(body)?;

        Ok(Self {
            model: decision.model.clone(),
            messages: Vec::new(),
            stream: false,
            service_tier: decision.service_tier,
            session_id: decision.session_id.clone(),
            max_completion_tokens: None,
            max_tokens: None,
            parameters: Map::new(),
            encoded_input_ids: None,
            runtime_model_name: None,
            decision: Some(decision),
            continue_final_message: false,
            open_output_limit: false,
        })
    }

    pub fn parse(body: &[u8]) -> Result<Self, GatewayError> {
        let request = Self::deserialize(Value::Object(strict_object(body)?))
            .map_err(|_| GatewayError::invalid_request(None))?;
        request.validate_request()?;

        Ok(request)
    }

    /// Whether the request asks for Moonshot Partial Mode: `partial: true` on
    /// a final assistant message whose content is the text to continue.
    /// `partial` anywhere else, or with any other value, is invalid.
    pub(crate) fn partial_mode(&self) -> Result<bool, GatewayError> {
        let invalid = || GatewayError::invalid_request(Some("messages"));
        let last = self.messages.len().saturating_sub(1);
        let mut partial = false;
        for (index, message) in self.messages.iter().enumerate() {
            let Some(value) = message.get("partial") else {
                continue;
            };
            match value {
                Value::Bool(false) => {}
                Value::Bool(true)
                    if index == last
                        && message.get("role") == Some(&Value::from("assistant"))
                        && message
                            .get("content")
                            .and_then(Value::as_str)
                            .is_some_and(|content| !content.is_empty()) =>
                {
                    partial = true;
                }
                _ => return Err(invalid()),
            }
        }

        Ok(partial)
    }

    pub fn output_token_limit(&self) -> Option<OutputTokenLimit> {
        self.max_completion_tokens
            .map(OutputTokenLimit::MaxCompletionTokens)
            .or_else(|| self.max_tokens.map(OutputTokenLimit::MaxTokens))
    }

    pub(crate) fn into_upstream_body_for_model(
        self,
        effective_output_tokens: u64,
        runtime_model_name: Option<&str>,
    ) -> Value {
        let limit_name = self
            .output_token_limit()
            .map_or("max_completion_tokens", OutputTokenLimit::parameter_name);

        let Self {
            model,
            messages,
            stream,
            service_tier,
            session_id: _,
            max_completion_tokens: _,
            max_tokens: _,
            mut parameters,
            encoded_input_ids: _,
            runtime_model_name: _,
            decision: _,
            continue_final_message,
            open_output_limit,
        } = self;

        let mut messages = messages;
        for message in &mut messages {
            if let Some(fields) = message.as_object_mut() {
                fields.remove("partial");
            }
        }
        if continue_final_message {
            // SGLang continues the final assistant message as the response.
            // Kimi's template would otherwise open the think channel first,
            // and the prefix would land in the reasoning.
            parameters.insert("continue_final_message".to_owned(), Value::Bool(true));
            parameters.insert(
                "chat_template_kwargs".to_owned(),
                serde_json::json!({"thinking": false}),
            );
        }

        parameters.insert(
            "model".to_owned(),
            Value::String(runtime_model_name.unwrap_or(&model).to_owned()),
        );
        parameters.insert("messages".to_owned(), Value::Array(messages));
        parameters.insert("stream".to_owned(), Value::Bool(stream));
        parameters.insert(
            "priority".to_owned(),
            Value::from(service_tier.runtime_priority()),
        );

        if stream {
            parameters.insert(
                "stream_options".to_owned(),
                serde_json::json!({
                    "include_usage": true,
                    "continuous_usage_stats": true
                }),
            );
        }

        if !open_output_limit {
            parameters.insert(limit_name.to_owned(), Value::from(effective_output_tokens));
        }

        Value::Object(parameters)
    }

    /// The OpenRouter body has no runtime priority or private usage options:
    /// OpenRouter always reports usage once, in its final frame.
    pub(crate) fn into_external_body(
        self,
        effective_output_tokens: u64,
        model_id: &str,
    ) -> Map<String, Value> {
        let limit_name = self
            .output_token_limit()
            .map_or("max_completion_tokens", OutputTokenLimit::parameter_name);

        let Self {
            messages,
            stream,
            mut parameters,
            open_output_limit,
            ..
        } = self;

        parameters.insert("model".to_owned(), Value::String(model_id.to_owned()));
        parameters.insert("messages".to_owned(), Value::Array(messages));
        parameters.insert("stream".to_owned(), Value::Bool(stream));
        if !open_output_limit {
            parameters.insert(limit_name.to_owned(), Value::from(effective_output_tokens));
        }

        parameters
    }

    fn validate_request(&self) -> Result<(), GatewayError> {
        <Self as Validate>::validate(self).map_err(|_| GatewayError::invalid_request(None))?;

        if self.max_completion_tokens.is_some() && self.max_tokens.is_some() {
            return Err(GatewayError::invalid_request(Some("max_completion_tokens")));
        }

        if self.parameters.contains_key("priority") {
            return Err(GatewayError::invalid_request(Some("priority")));
        }

        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OutputTokenLimit {
    MaxCompletionTokens(u64),
    MaxTokens(u64),
}

impl OutputTokenLimit {
    pub fn value(self) -> u64 {
        match self {
            Self::MaxCompletionTokens(value) | Self::MaxTokens(value) => value,
        }
    }

    pub fn parameter_name(self) -> &'static str {
        match self {
            Self::MaxCompletionTokens(_) => "max_completion_tokens",
            Self::MaxTokens(_) => "max_tokens",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_target_body_names_exactly_one_model() {
        let target = parse_target(br#"{"model":"claude-sonnet-5","max_tokens":16}"#).unwrap();
        assert_eq!(target.model, "claude-sonnet-5");
        assert_eq!(target.request["max_tokens"], 16);

        for body in [
            &br#"{"max_tokens":16}"#[..],
            &br#"{"model":""}"#[..],
            &br#"{"model":null}"#[..],
            &br#"{"model":["claude-sonnet-5"]}"#[..],
            &br#"{"model":"claude-sonnet-5","model":"claude-opus-5"}"#[..],
            &br#"not json"#[..],
            &br#"["claude-sonnet-5"]"#[..],
        ] {
            assert!(
                parse_target(body).is_err(),
                "expected a local rejection for {}",
                String::from_utf8_lossy(body)
            );
        }
    }

    #[test]
    fn parses_the_gateway_owned_fields_and_preserves_other_values() {
        let request = InferenceRequest::parse(
            br#"{
                "model":"mlx-community/qwen3-0.6b-4bit",
                "messages":[{"role":"user","content":"hello"}],
                "temperature":0.25,
                "tools":[{"type":"function","function":{"name":"weather"}}]
            }"#,
        )
        .expect("request should parse");

        assert!(!request.stream);
        assert_eq!(request.service_tier, ServiceTier::Default);
        assert_eq!(request.output_token_limit(), None);
        assert_eq!(request.parameters["temperature"], 0.25);
        assert_eq!(request.parameters["tools"][0]["type"], "function");
        assert_eq!(request.messages[0]["content"], "hello");
    }

    #[test]
    fn parses_service_tiers_and_rejects_priority_overrides() {
        for (value, expected) in [
            ("flex", ServiceTier::Flex),
            ("default", ServiceTier::Default),
            ("fast", ServiceTier::Fast),
        ] {
            let body =
                format!(r#"{{"model":"model-a","messages":[{{}}],"service_tier":"{value}"}}"#);
            assert_eq!(
                InferenceRequest::parse(body.as_bytes())
                    .unwrap()
                    .service_tier,
                expected
            );
        }
        assert!(InferenceRequest::parse(
            br#"{"model":"model-a","messages":[{}],"service_tier":"slow"}"#
        )
        .is_err());
        assert_eq!(
            InferenceRequest::parse(br#"{"model":"model-a","messages":[{}],"priority":-100}"#),
            Err(GatewayError::invalid_request(Some("priority")))
        );
    }

    #[test]
    fn rejects_duplicate_or_conflicting_gateway_fields() {
        let duplicate = br#"{
            "model":"model-a",
            "model":"model-b",
            "messages":[{}]
        }"#;
        assert_eq!(
            InferenceRequest::parse(duplicate),
            Err(GatewayError::invalid_request(None))
        );

        let conflicting = br#"{
            "model":"model-a",
            "messages":[{}],
            "max_tokens":10,
            "max_completion_tokens":10
        }"#;
        assert_eq!(
            InferenceRequest::parse(conflicting),
            Err(GatewayError::invalid_request(Some("max_completion_tokens")))
        );
    }

    #[test]
    fn rejects_invalid_gateway_owned_fields() {
        for body in [
            br#"{"messages":[{}]}"#.as_slice(),
            br#"{"model":"model-a","messages":[]}"#.as_slice(),
            br#"{"model":"model-a","messages":[{}],"stream":"yes"}"#.as_slice(),
            br#"{"model":"model-a","messages":[{}],"max_tokens":0}"#.as_slice(),
        ] {
            assert!(InferenceRequest::parse(body).is_err());
        }
    }

    #[test]
    fn builds_a_new_upstream_body_without_losing_qualified_fields() {
        let request = InferenceRequest::parse(
            br#"{
                "model":"model-a",
                "messages":[{"role":"user","content":"hello"}],
                "max_tokens":32,
                "temperature":0.25,
                "tools":[{"type":"function","function":{"name":"weather"}}]
            }"#,
        )
        .unwrap();

        let body = request.into_upstream_body_for_model(32, None);

        assert_eq!(body["model"], "model-a");
        assert_eq!(body["messages"][0]["content"], "hello");
        assert_eq!(body["stream"], false);
        assert_eq!(body["priority"], 0);
        assert_eq!(body["max_tokens"], 32);
        assert!(body.get("max_completion_tokens").is_none());
        assert_eq!(body["temperature"], 0.25);
        assert_eq!(body["tools"][0]["function"]["name"], "weather");
    }

    #[test]
    fn injects_the_trusted_runtime_priority() {
        for (tier, priority) in [("fast", -10), ("default", 0), ("flex", 10)] {
            let body =
                format!(r#"{{"model":"model-a","messages":[{{}}],"service_tier":"{tier}"}}"#);
            let upstream = InferenceRequest::parse(body.as_bytes())
                .unwrap()
                .into_upstream_body_for_model(32, None);
            assert_eq!(upstream["priority"], priority);
            assert!(upstream.get("service_tier").is_none());
        }
    }

    #[test]
    fn replaces_only_the_private_runtime_model_name() {
        let request = InferenceRequest::parse(
            br#"{"model":"public/model","messages":[{"role":"user","content":"hello"}]}"#,
        )
        .unwrap();

        let body = request.into_upstream_body_for_model(32, Some("runtime-model"));

        assert_eq!(body["model"], "runtime-model");
        assert_eq!(body["messages"][0]["content"], "hello");
    }

    #[test]
    fn materializes_the_qualified_default_output_ceiling() {
        let request = InferenceRequest::parse(
            br#"{"model":"model-a","messages":[{"role":"user","content":"hello"}]}"#,
        )
        .unwrap();

        let body = request.into_upstream_body_for_model(1_024, None);

        assert_eq!(body["max_completion_tokens"], 1_024);
    }

    #[test]
    fn an_external_body_keeps_qualified_fields_and_drops_runtime_controls() {
        let request = InferenceRequest::parse(
            br#"{
                "model":"public/model",
                "messages":[{"role":"user","content":"hello"}],
                "stream":true,
                "service_tier":"fast",
                "session_id":"customer-session",
                "max_tokens":32,
                "temperature":0.25
            }"#,
        )
        .unwrap();

        let body = request.into_external_body(32, "author/model");

        assert_eq!(body["model"], "author/model");
        assert_eq!(body["messages"][0]["content"], "hello");
        assert_eq!(body["stream"], true);
        assert_eq!(body["max_tokens"], 32);
        assert_eq!(body["temperature"], 0.25);
        for field in [
            "priority",
            "stream_options",
            "service_tier",
            "session_id",
            "max_completion_tokens",
        ] {
            assert!(!body.contains_key(field), "{field}");
        }

        let defaulted = InferenceRequest::parse(br#"{"model":"m","messages":[{}]}"#)
            .unwrap()
            .into_external_body(1_024, "author/model");
        assert_eq!(defaulted["max_completion_tokens"], 1_024);
    }

    #[test]
    fn streaming_always_requests_continuous_authoritative_usage() {
        let request = InferenceRequest::parse(
            br#"{
                "model":"model-a",
                "messages":[{"role":"user","content":"hello"}],
                "stream":true
            }"#,
        )
        .unwrap();

        let body = request.into_upstream_body_for_model(128, None);

        assert_eq!(body["stream_options"]["include_usage"], true);
        assert_eq!(body["stream_options"]["continuous_usage_stats"], true);
    }

    #[test]
    fn partial_mode_is_a_nonempty_final_assistant_prefix() {
        let parse = |messages: &str| {
            InferenceRequest::parse(format!(r#"{{"model":"m","messages":{messages}}}"#).as_bytes())
                .unwrap()
                .partial_mode()
        };

        let prefix = r#"[{"role":"user","content":"hi"},{"role":"assistant","content":"Once","partial":true}]"#;
        assert!(parse(prefix).unwrap());
        assert!(!parse(r#"[{"role":"user","content":"hi"}]"#).unwrap());
        assert!(!parse(
            r#"[{"role":"user","content":"hi"},{"role":"assistant","content":"x","partial":false}]"#
        )
        .unwrap());

        for invalid in [
            r#"[{"role":"assistant","content":"x","partial":true},{"role":"user","content":"hi"}]"#,
            r#"[{"role":"user","content":"hi","partial":true}]"#,
            r#"[{"role":"assistant","content":"","partial":true}]"#,
            r#"[{"role":"assistant","content":[{"type":"text","text":"x"}],"partial":true}]"#,
            r#"[{"role":"assistant","content":"x","partial":"true"}]"#,
        ] {
            assert!(parse(invalid).is_err(), "{invalid}");
        }
    }

    #[test]
    fn partial_mode_continues_the_final_message_without_thinking() {
        let body = br#"{"model":"m","messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"Once","partial":true}]}"#;

        let mut request = InferenceRequest::parse(body).unwrap();
        request.continue_final_message = true;
        let upstream = request.into_upstream_body_for_model(32, None);
        assert_eq!(upstream["continue_final_message"], true);
        assert_eq!(upstream["chat_template_kwargs"]["thinking"], false);
        assert_eq!(upstream["messages"][1]["content"], "Once");
        assert!(upstream["messages"][1].get("partial").is_none());

        let ignored = InferenceRequest::parse(body)
            .unwrap()
            .into_upstream_body_for_model(32, None);
        assert!(ignored.get("continue_final_message").is_none());
        assert!(ignored.get("chat_template_kwargs").is_none());
        assert!(ignored["messages"][1].get("partial").is_none());

        let external = InferenceRequest::parse(body)
            .unwrap()
            .into_external_body(32, "author/model");
        assert_eq!(external["messages"][1]["partial"], true);
        assert!(!external.contains_key("continue_final_message"));
    }

    #[test]
    fn an_open_output_limit_leaves_the_limit_to_the_runtime() {
        let mut request = InferenceRequest::parse(
            br#"{"model":"m","messages":[{"role":"user","content":"hi"}]}"#,
        )
        .unwrap();
        request.open_output_limit = true;

        let upstream = request.clone().into_upstream_body_for_model(131_072, None);
        assert!(upstream.get("max_completion_tokens").is_none());
        assert!(upstream.get("max_tokens").is_none());

        let external = request.into_external_body(131_072, "author/model");
        assert!(!external.contains_key("max_completion_tokens"));
        assert!(!external.contains_key("max_tokens"));
    }
}
