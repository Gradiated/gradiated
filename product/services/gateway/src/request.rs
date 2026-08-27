use std::fmt;

use serde::{
    de::{self, MapAccess, Visitor},
    Deserialize, Deserializer,
};
use serde_json::{Map, Value};
use validator::Validate;

use crate::GatewayError;

#[derive(Clone, Debug, Deserialize, PartialEq, Validate)]
pub struct ChatCompletionRequest {
    #[validate(length(min = 1, max = 200))]
    pub model: String,
    #[validate(length(min = 1))]
    pub messages: Vec<Value>,
    #[serde(default)]
    pub stream: bool,
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
}

impl ChatCompletionRequest {
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
            session_id: _,
            max_completion_tokens,
            max_tokens,
            mut parameters,
            encoded_input_ids: _,
        } = self;

        parameters.insert(
            "model".to_owned(),
            Value::String(runtime_model_name.unwrap_or(&model).to_owned()),
        );
        parameters.insert("messages".to_owned(), Value::Array(messages));
        parameters.insert("stream".to_owned(), Value::Bool(stream));
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

struct UniqueJsonObject(Map<String, Value>);

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
        let request = ChatCompletionRequest::parse(
            br#"{
                "model":"mlx-community/qwen3-0.6b-4bit",
                "messages":[{"role":"user","content":"hello"}],
                "temperature":0.25,
                "tools":[{"type":"function","function":{"name":"weather"}}]
            }"#,
        )
        .expect("request should parse");

        assert!(!request.stream);
        assert_eq!(request.output_token_limit(), None);
        assert_eq!(request.parameters["temperature"], 0.25);
        assert_eq!(request.parameters["tools"][0]["type"], "function");
        assert_eq!(request.messages[0]["content"], "hello");
    }

    #[test]
    fn rejects_duplicate_or_conflicting_gateway_fields() {
        let duplicate = br#"{
            "model":"model-a",
            "model":"model-b",
            "messages":[{}]
        }"#;
        assert_eq!(
            ChatCompletionRequest::parse(duplicate),
            Err(GatewayError::invalid_request(None))
        );

        let conflicting = br#"{
            "model":"model-a",
            "messages":[{}],
            "max_tokens":10,
            "max_completion_tokens":10
        }"#;
        assert_eq!(
            ChatCompletionRequest::parse(conflicting),
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
            assert!(ChatCompletionRequest::parse(body).is_err());
        }
    }

    #[test]
    fn builds_a_new_upstream_body_without_losing_qualified_fields() {
        let request = ChatCompletionRequest::parse(
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
        assert_eq!(body["max_tokens"], 32);
        assert!(body.get("max_completion_tokens").is_none());
        assert_eq!(body["temperature"], 0.25);
        assert_eq!(body["tools"][0]["function"]["name"], "weather");
    }

    #[test]
    fn replaces_only_the_private_runtime_model_name() {
        let request = ChatCompletionRequest::parse(
            br#"{"model":"public/model","messages":[{"role":"user","content":"hello"}]}"#,
        )
        .unwrap();

        let body = request.into_upstream_body_for_model(32, Some("runtime-model"));

        assert_eq!(body["model"], "runtime-model");
        assert_eq!(body["messages"][0]["content"], "hello");
    }

    #[test]
    fn materializes_the_qualified_default_output_ceiling() {
        let request = ChatCompletionRequest::parse(
            br#"{"model":"model-a","messages":[{"role":"user","content":"hello"}]}"#,
        )
        .unwrap();

        let body = request.into_upstream_body_for_model(1_024, None);

        assert_eq!(body["max_completion_tokens"], 1_024);
    }

    #[test]
    fn streaming_always_requests_continuous_authoritative_usage() {
        let request = ChatCompletionRequest::parse(
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
