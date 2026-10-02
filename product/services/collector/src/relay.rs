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
    request: String,
    response_content_type: String,
    response: String,
}

pub fn normalize(body: &[u8]) -> Result<Vec<u8>, RecordError> {
    let value: Value = serde_json::from_slice(body).map_err(malformed)?;
    let hosted = value["schema"] == "gradiated.hosted/1";
    if !hosted && value["schema"] != "gradiated.relay/1" {
        GenerationContent::parse(body)?;
        return Ok(body.to_vec());
    }

    let relay: Relay = serde_json::from_value(value).map_err(malformed)?;
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

    let protocol = match (relay.provider.as_str(), relay.path.split('?').next()) {
        ("anthropic", Some("/v1/messages" | "/messages")) => "anthropic.messages",
        ("openai", Some("/v1/chat/completions" | "/chat/completions")) => "openai.chat",
        ("openai", Some("/v1/responses" | "/responses")) => "openai.responses",
        _ => return Err(invalid("unsupported relay protocol")),
    };
    let request: Value = serde_json::from_str(&relay.request).map_err(malformed)?;
    let model = request["model"]
        .as_str()
        .ok_or_else(|| invalid("missing model"))?;
    let streamed = relay
        .response_content_type
        .split(';')
        .next()
        .unwrap_or("")
        .trim()
        .eq_ignore_ascii_case("text/event-stream");
    let response: Value = if streamed {
        crate::relay_stream::rebuild(protocol, &relay.response)?
    } else {
        serde_json::from_str(&relay.response).map_err(malformed)?
    };
    if !response.is_object() {
        return Err(invalid("response must be an object"));
    }

    let (seconds, nanos) = relay.generation_id.get_timestamp().unwrap().to_unix();
    let started_at = DateTime::<Utc>::from_timestamp(seconds as i64, nanos)
        .ok_or_else(|| invalid("invalid generation timestamp"))?;
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
    let record = json!({
        "schema": SCHEMA,
        "generation_id": relay.generation_id,
        "workspace_id": relay.workspace_id,
        "task": relay.task,
        "trace_id": relay.trace_id.unwrap_or_else(|| relay.generation_id.to_string()),
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
        "started_at": started_at,
        "completed_at": relay.completed_at,
        "streamed": streamed,
        "usage": usage(protocol, &response),
        "raw": { "request": request, "response": response },
        "canonical": canonical
    });
    let bytes = serde_json::to_vec(&record).map_err(malformed)?;
    GenerationContent::parse(&bytes)?;

    Ok(bytes)
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
