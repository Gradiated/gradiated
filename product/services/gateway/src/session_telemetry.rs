use axum::http::HeaderMap;
use serde_json::Value;
use sha2::{Digest, Sha256};

const MAX_IDENTIFIER_BYTES: usize = 256;
const MAX_METADATA_BYTES: usize = 8_192;
const SESSION_HEADERS: [(&str, &str); 8] = [
    ("x-opencode-session-id", "opencode_session_hash"),
    ("x-session-affinity", "session_affinity_hash"),
    ("x-session-id", "generic_session_hash"),
    ("x-claude-code-session-id", "claude_session_hash"),
    ("session-id", "codex_session_hash"),
    ("thread-id", "codex_thread_hash"),
    ("x-client-request-id", "client_request_hash"),
    ("x-codex-window-id", "codex_window_hash"),
];

fn identifier_hash(value: &str) -> Option<String> {
    (!value.is_empty() && value.len() <= MAX_IDENTIFIER_BYTES)
        .then(|| format!("{:x}", Sha256::digest(value.as_bytes()))[..16].to_owned())
}

fn record_identifier(span: &tracing::Span, field: &str, value: Option<&str>) {
    if let Some(hash) = value.and_then(identifier_hash) {
        span.record(field, hash);
    }
}

fn json_metadata(value: &str) -> Option<Value> {
    (value.len() <= MAX_METADATA_BYTES)
        .then(|| serde_json::from_str(value).ok())
        .flatten()
}

pub(crate) fn record_headers(span: &tracing::Span, headers: &HeaderMap) {
    let mut present = Vec::new();
    for (header, field) in SESSION_HEADERS {
        if headers.contains_key(header) {
            present.push(header);
        }
        let mut values = headers.get_all(header).iter();
        let value = values.next().and_then(|value| value.to_str().ok());
        if values.next().is_none() {
            record_identifier(span, field, value);
        }
    }
    if headers.contains_key("x-codex-turn-metadata") {
        present.push("x-codex-turn-metadata");
        let mut values = headers.get_all("x-codex-turn-metadata").iter();
        let metadata = values
            .next()
            .and_then(|value| value.to_str().ok())
            .and_then(json_metadata);
        if values.next().is_none() {
            if let Some(metadata) = metadata {
                record_identifier(
                    span,
                    "codex_metadata_session_hash",
                    metadata.get("session_id").and_then(Value::as_str),
                );
                record_identifier(
                    span,
                    "codex_metadata_thread_hash",
                    metadata.get("thread_id").and_then(Value::as_str),
                );
            }
        }
    }
    span.record("session_headers_present", present.join(","));
}

pub(crate) fn record_body(request: &Value) {
    let span = tracing::Span::current();
    if let Some(value) = request
        .get("session_id")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty() && value.chars().take(257).count() <= 256)
    {
        span.record(
            "body_session_hash",
            format!("{:x}", Sha256::digest(value.as_bytes()))[..16].to_owned(),
        );
    }
    for (pointer, field) in [
        ("/prompt_cache_key", "prompt_cache_key_hash"),
        (
            "/client_metadata/session_id",
            "client_metadata_session_hash",
        ),
        ("/client_metadata/thread_id", "client_metadata_thread_hash"),
    ] {
        record_identifier(
            &span,
            field,
            request.pointer(pointer).and_then(Value::as_str),
        );
    }
    let metadata = request
        .pointer("/metadata/user_id")
        .and_then(Value::as_str)
        .and_then(json_metadata);
    if let Some(metadata) = metadata {
        record_identifier(
            &span,
            "anthropic_metadata_session_hash",
            metadata.get("session_id").and_then(Value::as_str),
        );
    }
}

pub(crate) fn record_effective(key: Option<&crate::session_affinity::CacheKey>, system_one: bool) {
    let span = tracing::Span::current();
    span.record(
        "effective_session_source",
        key.map_or(
            if system_one {
                "state_prefix"
            } else {
                "content_prefix"
            },
            |key| key.source,
        ),
    );
    if let Some(key) = key {
        span.record(
            "effective_session_hash",
            format!("{:x}", Sha256::digest(key.value.as_bytes()))[..16].to_owned(),
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::diagnostics::{capture::Logs, request_span};
    use serde_json::json;

    #[test]
    fn hashes_only_known_identifiers_and_rejects_oversized_or_duplicate_values() {
        let logs = Logs::default();
        let _guard = logs.start();
        let mut headers = HeaderMap::new();
        for (header, _) in SESSION_HEADERS {
            headers.insert(header, "synthetic-session".parse().unwrap());
        }
        headers.insert("x-codex-turn-metadata", r#"{"session_id":"synthetic-session","thread_id":"synthetic-thread","workspaces":"private-path","installation_id":"private-device"}"#.parse().unwrap());
        headers.insert("x-arbitrary-session", "must-not-log".parse().unwrap());
        let span = request_span(uuid::Uuid::from_u128(1), &headers);
        span.in_scope(|| {
            record_body(&json!({"prompt_cache_key":"synthetic-key","metadata":{"user_id":r#"{"session_id":"synthetic-session","device_id":"private-device"}"#},"client_metadata":{"session_id":"synthetic-session","thread_id":"synthetic-thread"}}));
            record_effective(None, false);
            tracing::info!(event = "session_probe");
        });
        let events = logs.events();
        let event = &events[0];
        let fields = &event["span"];
        for (_, field) in SESSION_HEADERS {
            assert_eq!(fields[field], identifier_hash("synthetic-session").unwrap());
        }
        assert_eq!(
            fields["anthropic_metadata_session_hash"],
            fields["claude_session_hash"]
        );
        assert_eq!(fields["effective_session_source"], "content_prefix");
        for private in [
            "synthetic-session",
            "synthetic-key",
            "synthetic-thread",
            "private-path",
            "private-device",
            "must-not-log",
        ] {
            assert!(!event.to_string().contains(private));
        }

        assert!(identifier_hash("").is_none());
        assert!(identifier_hash(&"x".repeat(MAX_IDENTIFIER_BYTES + 1)).is_none());
        assert!(json_metadata(&"x".repeat(MAX_METADATA_BYTES + 1)).is_none());
        headers.append("x-session-id", "second-session".parse().unwrap());
        let span = request_span(uuid::Uuid::from_u128(2), &headers);
        span.in_scope(|| tracing::info!(event = "duplicate_probe"));
        let events = logs.events();
        assert!(events[1]["span"].get("generic_session_hash").is_none());
        assert!(events[1]["span"]["session_headers_present"]
            .as_str()
            .unwrap()
            .contains("x-session-id"));
    }
}
