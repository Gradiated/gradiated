use std::fmt;

use serde::{
    de::{self, MapAccess, Visitor},
    Deserialize, Deserializer,
};
use serde_json::{Map, Value};
use validator::Validate;

use crate::{GatewayError, ServiceTier};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RequestKind {
    Chat,
    SystemOne,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
pub struct InferenceRequest {
    #[validate(length(min = 1, max = 200))]
    pub model: String,
    #[validate(length(min = 1))]
    pub messages: Vec<Value>,
    #[serde(default)]
    pub stream: bool,
    #[serde(default)]
    pub service_tier: ServiceTier,
    #[validate(length(min = 1, max = 256))]
    pub session_id: Option<String>,
    #[validate(range(min = 1_u64, max = 9_007_199_254_740_991_u64))]
    pub max_completion_tokens: Option<u64>,
    #[validate(range(min = 1_u64, max = 9_007_199_254_740_991_u64))]
    pub max_tokens: Option<u64>,
    #[serde(flatten)]
    pub parameters: Map<String, Value>,
    #[serde(skip)]
    pub(crate) encoded_input_ids: Option<Vec<u32>>,
    #[serde(skip)]
    pub(crate) decision: Option<crate::systemone::SystemOneRequest>,
}

impl InferenceRequest {
    pub fn parse_kind(body: &[u8], kind: RequestKind) -> Result<Self, GatewayError> {
        if kind == RequestKind::Chat {
            return Self::parse(body);
        }
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
            decision: Some(decision),
        })
    }
    pub fn parse(body: &[u8]) -> Result<Self, GatewayError> {
        let UniqueJsonObject(fields) =
            serde_json::from_slice(body).map_err(|_| GatewayError::invalid_request(None))?;
        let request = Self::deserialize(Value::Object(fields))
            .map_err(|_| GatewayError::invalid_request(None))?;
        request.validate_request()?;
        Ok(request)
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
        let Self {
            model,
            messages,
            stream,
            service_tier,
            session_id: _,
            max_completion_tokens,
            max_tokens,
            mut parameters,
            encoded_input_ids: _,
            decision: _,
        } = self;

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
        match (max_completion_tokens, max_tokens) {
            (Some(_), None) => {
                parameters.insert(
                    "max_completion_tokens".to_owned(),
                    Value::from(effective_output_tokens),
                );
            }
            (None, Some(_)) => {
                parameters.insert(
                    "max_tokens".to_owned(),
                    Value::from(effective_output_tokens),
                );
            }
            (None, None) => {
                parameters.insert(
                    "max_completion_tokens".to_owned(),
                    Value::from(effective_output_tokens),
                );
            }
            (Some(_), Some(_)) => {
                debug_assert!(false, "validated requests contain one output-token field");
            }
        }

        Value::Object(parameters)
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

pub(crate) struct UniqueJsonObject(pub(crate) Map<String, Value>);

impl<'de> Deserialize<'de> for UniqueJsonObject {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_map(UniqueJsonObjectVisitor)
    }
}

struct UniqueJsonObjectVisitor;

impl<'de> Visitor<'de> for UniqueJsonObjectVisitor {
    type Value = UniqueJsonObject;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON object with unique top-level fields")
    }

    fn visit_map<A>(self, mut values: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut fields = Map::new();
        while let Some((name, value)) = values.next_entry::<String, Value>()? {
            if fields.contains_key(&name) {
                return Err(de::Error::custom(format_args!(
                    "duplicate top-level field `{name}`"
                )));
            }
            fields.insert(name, value);
        }
        Ok(UniqueJsonObject(fields))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
