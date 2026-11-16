use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use serde_json::{json, Value};
use uuid::Uuid;

use crate::record::{GenerationContent, RecordError, SCHEMA};

#[derive(Deserialize)]
struct Relay {
    generation_id: Uuid,
    workspace_id: Uuid,
    task: Option<String>,
    trace_id: Option<String>,
    session_id: Option<String>,
    provider: String,
    path: String,
    retention_days: u16,
    status: u16,
    outcome: String,
    completed_at: DateTime<Utc>,
    #[serde(default)]
    request: Option<String>,
    #[serde(default)]
    request_base64: Option<String>,
    #[serde(default)]
    request_content_type: Option<String>,
    #[serde(default)]
    request_content_encoding: Option<String>,
    response_content_type: String,
    #[serde(default)]
    response: Option<String>,
    #[serde(default)]
    response_base64: Option<String>,
    #[serde(default)]
    response_content_encoding: Option<String>,
}

/// One HTTP body as the sender saw it: text, or bytes that are not UTF-8.
enum Body {
    Text(String),
    Binary(Vec<u8>),
}

impl Body {
    fn from_bytes(bytes: Vec<u8>) -> Self {
        String::from_utf8(bytes)
            .map(Self::Text)
            .unwrap_or_else(|error| Self::Binary(error.into_bytes()))
    }

    /// Removes the body's content coding. A body that cannot be decoded is
    /// kept as sent, and the coding that still applies is returned with it.
    fn decoded(self, coding: Option<&str>, accept_partial: bool) -> (Self, Option<String>) {
        let Some(coding) = coding.filter(|coding| {
            !coding.trim().is_empty() && !coding.trim().eq_ignore_ascii_case("identity")
        }) else {
            return (self, None);
        };

        match crate::decode::decode(self.bytes(), coding) {
            Ok(crate::decode::Decoded::Complete(bytes)) => (Self::from_bytes(bytes), None),
            Ok(crate::decode::Decoded::Partial(bytes)) if accept_partial => {
                (Self::from_bytes(bytes), None)
            }
            _ => (self, Some(coding.to_owned())),
        }
    }

    fn from_fields(
        text: Option<String>,
        encoded: Option<String>,
        name: &str,
    ) -> Result<Self, RecordError> {
        match (text, encoded) {
            (Some(text), None) => Ok(Self::Text(text)),
            (None, Some(encoded)) => BASE64
                .decode(encoded)
                .map(Self::Binary)
                .map_err(|_| invalid(&format!("{name}_base64 is not base64"))),
            _ => Err(invalid(&format!(
                "exactly one of {name} and {name}_base64 is required"
            ))),
        }
    }

    fn text(&self) -> Option<&str> {
        match self {
            Self::Text(text) => Some(text),
            Self::Binary(_) => None,
        }
    }

    fn bytes(&self) -> &[u8] {
        match self {
            Self::Text(text) => text.as_bytes(),
            Self::Binary(bytes) => bytes,
        }
    }

    /// Parsed JSON when the body is JSON, the text otherwise, and base64 for bytes.
    fn stored(&self) -> Value {
        match self {
            Self::Text(text) => {
                serde_json::from_str(text).unwrap_or_else(|_| Value::String(text.clone()))
            }
            Self::Binary(bytes) => json!({ "encoding": "base64", "data": BASE64.encode(bytes) }),
        }
    }
}

/// Envelope fields shared by parsed and raw records.
struct Envelope<'a> {
    relay: &'a Relay,
    /// Codings that still apply to the stored bodies because they could not
    /// be removed; such an exchange is kept raw.
    request_coding: Option<String>,
    response_coding: Option<String>,
    hosted: bool,
    started_at: DateTime<Utc>,
    streamed: bool,
}

pub fn normalize(body: &[u8]) -> Result<Vec<u8>, RecordError> {
    let value: Value = serde_json::from_slice(body).map_err(malformed)?;
    let hosted = value["schema"] == "gradiated.hosted/1";
    if !hosted && value["schema"] != "gradiated.relay/1" {
        GenerationContent::parse(body)?;
        return Ok(body.to_vec());
    }

    let mut relay: Relay = serde_json::from_value(value).map_err(malformed)?;
    if relay.generation_id.get_version_num() != 7 {
        return Err(RecordError::GenerationId);
    }
    if !matches!(
        relay.outcome.as_str(),
        "complete" | "error" | "cancelled" | "truncated"
    ) || !(100..=599).contains(&relay.status)
    {
        return Err(invalid("invalid relay outcome or status"));
    }

    let request = Body::from_fields(relay.request.take(), relay.request_base64.take(), "request")?;
    let response = Body::from_fields(
        relay.response.take(),
        relay.response_base64.take(),
        "response",
    )?;
    // Compressed bodies are decoded here, so the proxy forwards the customer's
    // bytes unchanged. A cancelled or failed stream keeps what decoded.
    let (request, request_coding) =
        request.decoded(relay.request_content_encoding.as_deref(), false);
    let (response, response_coding) = response.decoded(
        relay.response_content_encoding.as_deref(),
        relay.outcome != "complete",
    );
    let (seconds, nanos) = relay.generation_id.get_timestamp().unwrap().to_unix();
    let envelope = Envelope {
        relay: &relay,
        request_coding,
        response_coding,
        hosted,
        started_at: DateTime::<Utc>::from_timestamp(seconds as i64, nanos)
            .ok_or_else(|| invalid("invalid generation timestamp"))?,
        streamed: relay
            .response_content_type
            .split(';')
            .next()
            .unwrap_or("")
            .trim()
            .eq_ignore_ascii_case("text/event-stream"),
    };

    // A known protocol is parsed; anything else, including a body that does not
    // parse as its protocol, is kept as the raw HTTP exchange.
    // A body still compressed after decoding is stored as sent, with its coding.
    let encoded = envelope.request_coding.is_some() || envelope.response_coding.is_some();
    // A stream that did not complete can end mid-event; parse the whole events.
    let response_text = response.text().map(|text| {
        if envelope.streamed && relay.outcome != "complete" {
            whole_events(text)
        } else {
            text
        }
    });
    let parsed = known_protocol(&relay.provider, &relay.path)
        .filter(|_| !encoded)
        .zip(request.text().zip(response_text))
        .and_then(|(protocol, (request, response))| {
            parsed(&envelope, protocol, request, response).ok()
        });
    let record = match parsed {
        Some(record) => record,
        None => raw_http(&envelope, &request, &response),
    };
    let bytes = serde_json::to_vec(&record).map_err(malformed)?;
    GenerationContent::parse(&bytes)?;

    Ok(bytes)
}

/// The text up to the end of the last complete server-sent event.
fn whole_events(text: &str) -> &str {
    if text.ends_with("\n\n") || text.ends_with("\r\n\r\n") {
        return text;
    }
    [
        text.rfind("\n\n").map(|end| end + 2),
        text.rfind("\r\n\r\n").map(|end| end + 4),
    ]
    .into_iter()
    .flatten()
    .max()
    .map_or(text, |end| &text[..end])
}

fn known_protocol(provider: &str, path: &str) -> Option<&'static str> {
    match (provider, path.split('?').next()) {
        ("anthropic", Some("/v1/messages" | "/messages")) => Some("anthropic.messages"),
        ("openai", Some("/v1/chat/completions" | "/chat/completions")) => Some("openai.chat"),
        ("openai", Some("/v1/responses" | "/responses")) => Some("openai.responses"),
        _ => None,
    }
}

fn parsed(
    envelope: &Envelope,
    protocol: &'static str,
    request: &str,
    response: &str,
) -> Result<Value, RecordError> {
    let (relay, hosted, streamed) = (envelope.relay, envelope.hosted, envelope.streamed);
    let request: Value = serde_json::from_str(request).map_err(malformed)?;
    let model = request["model"]
        .as_str()
        .ok_or_else(|| invalid("missing model"))?;
    let response: Value = if streamed {
        crate::relay_stream::rebuild(protocol, response)?
    } else {
        serde_json::from_str(response).map_err(malformed)?
    };
    if !response.is_object() {
        return Err(invalid("response must be an object"));
    }
    let canonical = if hosted && protocol == "openai.chat" {
        response.pointer("/choices/0/message").filter(|message| message.is_object()).map(|message| json!({
            "version": 1,
            "messages": request["messages"],
            "tools": request.get("tools").filter(|value| !value.is_null()).cloned().unwrap_or_else(|| json!([])),
            "output": {
                "role": message["role"],
                "content": message.get("content").cloned().unwrap_or(Value::Null),
                "tool_calls": message.get("tool_calls").filter(|value| !value.is_null()).cloned().unwrap_or_else(|| json!([]))
            }
        }))
    } else {
        None
    };
    let limited = match protocol {
        "openai.chat" => {
            response
                .pointer("/choices/0/finish_reason")
                .and_then(Value::as_str)
                == Some("length")
        }
        "anthropic.messages" => response["stop_reason"] == "max_tokens",
        "openai.responses" => {
            response["status"] == "incomplete"
                && response
                    .pointer("/incomplete_details/reason")
                    .and_then(Value::as_str)
                    == Some("max_output_tokens")
        }
        _ => false,
    };
    let outcome = if hosted && limited {
        "truncated"
    } else {
        &relay.outcome
    };
    Ok(json!({
        "schema": SCHEMA,
        "generation_id": relay.generation_id,
        "workspace_id": relay.workspace_id,
        "task": relay.task,
        "trace_id": trace_id(relay),
        "session_id": relay.session_id,
        "external_id": null,
        "provider": if hosted { "gradiated" } else { &relay.provider },
        "protocol": protocol,
        "model": model,
        "source": if hosted { "hosted" } else { "relay" },
        "trainable": hosted,
        "retention_days": relay.retention_days,
        "status": relay.status,
        "outcome": outcome,
        "started_at": envelope.started_at,
        "completed_at": relay.completed_at,
        "streamed": streamed,
        "usage": usage(protocol, &response),
        "raw": { "request": request, "response": response },
        "canonical": canonical
    }))
}

fn trace_id(relay: &Relay) -> String {
    relay
        .trace_id
        .clone()
        .unwrap_or_else(|| relay.generation_id.to_string())
}

/// An exchange the collector does not parse, such as an upload, a transcription
/// or an embedding, stored as the bytes that crossed the wire.
fn raw_http(envelope: &Envelope, request: &Body, response: &Body) -> Value {
    let relay = envelope.relay;
    let request_json = request
        .text()
        .and_then(|text| serde_json::from_str::<Value>(text).ok());
    let model = request_json
        .as_ref()
        .and_then(|value| value["model"].as_str().map(str::to_owned))
        .or_else(|| {
            multipart_field(
                request.bytes(),
                relay.request_content_type.as_deref(),
                "model",
            )
        })
        .unwrap_or_else(|| "unknown".to_owned());
    let response_json = response
        .text()
        .and_then(|text| serde_json::from_str::<Value>(text).ok());

    json!({
        "schema": SCHEMA,
        "generation_id": relay.generation_id,
        "workspace_id": relay.workspace_id,
        "task": relay.task,
        "trace_id": trace_id(relay),
        "session_id": relay.session_id,
        "external_id": null,
        "provider": if envelope.hosted { "gradiated" } else { &relay.provider },
        "protocol": format!("{}.http", relay.provider),
        "model": model,
        "source": if envelope.hosted { "hosted" } else { "relay" },
        "trainable": envelope.hosted,
        "retention_days": relay.retention_days,
        "status": relay.status,
        "outcome": relay.outcome,
        "started_at": envelope.started_at,
        "completed_at": relay.completed_at,
        "streamed": envelope.streamed,
        "usage": response_json.as_ref().map_or(Value::Null, |response| usage("http", response)),
        "raw": {
            "path": relay.path,
            "request_content_type": relay.request_content_type,
            "request_content_encoding": envelope.request_coding,
            "request": request.stored(),
            "response_content_type": relay.response_content_type,
            "response_content_encoding": envelope.response_coding,
            "response": response.stored(),
        },
        "canonical": null
    })
}

/// The value of one small text field in a multipart/form-data body, such as `model`.
fn multipart_field(body: &[u8], content_type: Option<&str>, name: &str) -> Option<String> {
    let boundary = content_type?
        .split(';')
        .map(str::trim)
        .find_map(|part| part.strip_prefix("boundary="))?
        .trim_matches('"');
    let delimiter = format!("--{boundary}");
    let header = format!("name=\"{name}\"");

    let text = String::from_utf8_lossy(body);
    text.split(delimiter.as_str()).find_map(|part| {
        let (headers, value) = part.split_once("\r\n\r\n")?;
        let disposition = headers.lines().find(|line| {
            line.to_ascii_lowercase()
                .starts_with("content-disposition:")
        })?;
        let named = disposition
            .split(';')
            .map(str::trim)
            .any(|field| field == header);
        let value = value.strip_suffix("\r\n").unwrap_or(value);
        (named && !disposition.contains("filename=") && value.len() <= 256)
            .then(|| value.to_owned())
    })
}

fn usage(protocol: &str, response: &Value) -> Value {
    let Some(usage) = response.get("usage").filter(|value| value.is_object()) else {
        return Value::Null;
    };
    let number = |path: &str| {
        usage
            .pointer(path)
            .and_then(Value::as_u64)
            .map(Value::from)
            .unwrap_or(Value::Null)
    };

    match protocol {
        "openai.chat" => json!({
            "input": number("/prompt_tokens"), "output": number("/completion_tokens"),
            "reasoning": number("/completion_tokens_details/reasoning_tokens"),
            "cache_read": number("/prompt_tokens_details/cached_tokens")
        }),
        "openai.responses" => json!({
            "input": number("/input_tokens"), "output": number("/output_tokens"),
            "reasoning": number("/output_tokens_details/reasoning_tokens"),
            "cache_read": number("/input_tokens_details/cached_tokens")
        }),
        // Raw exchanges name tokens either way, such as embeddings' prompt_tokens.
        "http" => {
            let either = |first: &str, second: &str| {
                let value = number(first);
                if value.is_null() {
                    number(second)
                } else {
                    value
                }
            };
            json!({
                "input": either("/input_tokens", "/prompt_tokens"),
                "output": either("/output_tokens", "/completion_tokens"),
                "reasoning": null, "cache_read": null
            })
        }
        _ => json!({
            "input": number("/input_tokens"), "output": number("/output_tokens"),
            "reasoning": null, "cache_read": number("/cache_read_input_tokens")
        }),
    }
}

pub(crate) fn invalid(message: &str) -> RecordError {
    RecordError::Malformed(message.to_owned())
}

fn malformed(error: serde_json::Error) -> RecordError {
    invalid(&error.to_string())
}
