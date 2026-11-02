use axum::http::HeaderMap;
use serde_json::Value;

use crate::GatewayError;

const MAX_IDENTIFIER_BYTES: usize = 256;
const MAX_METADATA_BYTES: usize = 8_192;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct CacheKey {
    pub source: &'static str,
    pub value: String,
}

fn identifier(source: &'static str, value: &str) -> Option<CacheKey> {
    (!value.is_empty()
        && value.len() <= MAX_IDENTIFIER_BYTES
        && !value.chars().any(char::is_control))
    .then(|| CacheKey {
        source,
        value: value.to_owned(),
    })
}

fn header_key(headers: &HeaderMap, source: &'static str) -> Option<CacheKey> {
    let mut values = headers.get_all(source).iter();
    let value = values.next()?.to_str().ok()?;
    if values.next().is_some() {
        return None;
    }
    identifier(source, value)
}

fn metadata(value: &str) -> Option<Value> {
    (value.len() <= MAX_METADATA_BYTES)
        .then(|| serde_json::from_str(value).ok())
        .flatten()
}

pub(crate) fn cache_key(
    headers: &HeaderMap,
    body: &Value,
) -> Result<Option<CacheKey>, GatewayError> {
    if let Some(value) = body.get("session_id").filter(|value| !value.is_null()) {
        // Endpoint parsers retain their own scalar/UTF-16 length contracts.
        return value
            .as_str()
            .filter(|value| !value.is_empty() && value.chars().take(257).count() <= 256)
            .map(|value| {
                Some(CacheKey {
                    source: "body_session_id",
                    value: value.to_owned(),
                })
            })
            .ok_or_else(|| GatewayError::invalid_request(Some("session_id")));
    }
    if headers.contains_key("x-gradiated-session-id") {
        return header_key(headers, "x-gradiated-session-id")
            .map(Some)
            .ok_or_else(|| GatewayError::invalid_request(Some("session_id")));
    }
    if let Some(value) = body
        .get("prompt_cache_key")
        .filter(|value| !value.is_null())
    {
        return value
            .as_str()
            .and_then(|value| identifier("prompt_cache_key", value))
            .map(Some)
            .ok_or_else(|| GatewayError::invalid_request(Some("prompt_cache_key")));
    }
    for header in [
        "x-claude-code-session-id",
        "x-opencode-session-id",
        "x-session-affinity",
        "session-id",
        "thread-id",
        "x-session-id",
    ] {
        if let Some(key) = header_key(headers, header) {
            return Ok(Some(key));
        }
    }
    for (pointer, source) in [
        ("/client_metadata/session_id", "client_metadata_session_id"),
        ("/client_metadata/thread_id", "client_metadata_thread_id"),
    ] {
        if let Some(key) = body
            .pointer(pointer)
            .and_then(Value::as_str)
            .and_then(|value| identifier(source, value))
        {
            return Ok(Some(key));
        }
    }
    let mut values = headers.get_all("x-codex-turn-metadata").iter();
    let codex = values
        .next()
        .and_then(|value| value.to_str().ok())
        .and_then(metadata);
    if values.next().is_none() {
        if let Some(codex) = codex {
            for (field, source) in [
                ("session_id", "codex_metadata_session_id"),
                ("thread_id", "codex_metadata_thread_id"),
            ] {
                if let Some(key) = codex
                    .get(field)
                    .and_then(Value::as_str)
                    .and_then(|value| identifier(source, value))
                {
                    return Ok(Some(key));
                }
            }
        }
    }
    let anthropic = body
        .pointer("/metadata/user_id")
        .and_then(Value::as_str)
        .and_then(metadata);
    Ok(anthropic.and_then(|metadata| {
        metadata
            .get("session_id")
            .and_then(Value::as_str)
            .and_then(|value| identifier("anthropic_metadata_session_id", value))
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn every_source_resolves_and_pairwise_precedence_is_deterministic() {
        let candidates = [
            ("body_session_id", "body", "session_id"),
            ("x-gradiated-session-id", "header", "x-gradiated-session-id"),
            ("prompt_cache_key", "body", "prompt_cache_key"),
            (
                "x-claude-code-session-id",
                "header",
                "x-claude-code-session-id",
            ),
            ("x-opencode-session-id", "header", "x-opencode-session-id"),
            ("x-session-affinity", "header", "x-session-affinity"),
            ("session-id", "header", "session-id"),
            ("thread-id", "header", "thread-id"),
            ("x-session-id", "header", "x-session-id"),
            (
                "client_metadata_session_id",
                "client_metadata",
                "session_id",
            ),
            ("client_metadata_thread_id", "client_metadata", "thread_id"),
            ("codex_metadata_session_id", "codex", "session_id"),
            ("codex_metadata_thread_id", "codex", "thread_id"),
            ("anthropic_metadata_session_id", "anthropic", "session_id"),
        ];
        for first in 0..candidates.len() {
            for second in first..candidates.len() {
                let mut headers = HeaderMap::new();
                let mut body = json!({});
                let mut codex = json!({});
                let mut anthropic = json!({});
                for (index, value) in [(second, "lower"), (first, "preferred")] {
                    let (_, kind, field) = candidates[index];
                    match kind {
                        "header" => {
                            headers.insert(field, value.parse().unwrap());
                        }
                        "body" => {
                            body[field] = json!(value);
                        }
                        "client_metadata" => {
                            body["client_metadata"][field] = json!(value);
                        }
                        "codex" => {
                            codex[field] = json!(value);
                        }
                        "anthropic" => {
                            anthropic[field] = json!(value);
                        }
                        _ => unreachable!(),
                    }
                }
                headers.insert("x-codex-turn-metadata", codex.to_string().parse().unwrap());
                body["metadata"]["user_id"] = json!(anthropic.to_string());
                assert_eq!(
                    cache_key(&headers, &body).unwrap(),
                    Some(CacheKey {
                        source: candidates[first].0,
                        value: "preferred".into()
                    }),
                    "{first} must precede {second}"
                );
            }
        }
    }

    #[test]
    fn invalid_explicit_keys_are_rejected_but_invalid_optional_hints_are_skipped() {
        for value in [json!(""), json!("x".repeat(257)), json!(123), json!({})] {
            for field in ["session_id", "prompt_cache_key"] {
                let mut body = json!({});
                body[field] = value.clone();
                assert_eq!(
                    cache_key(&HeaderMap::new(), &body),
                    Err(GatewayError::invalid_request(Some(field)))
                );
            }
        }
        assert!(cache_key(
            &HeaderMap::new(),
            &json!({"prompt_cache_key":"line\nbreak"})
        )
        .is_err());
        let unicode = "😀".repeat(128);
        assert_eq!(
            cache_key(&HeaderMap::new(), &json!({"session_id":unicode}))
                .unwrap()
                .unwrap()
                .value,
            unicode
        );
        let mut headers = HeaderMap::new();
        headers.append("x-claude-code-session-id", "first".parse().unwrap());
        headers.append("x-claude-code-session-id", "second".parse().unwrap());
        headers.insert("x-opencode-session-id", "x".repeat(257).parse().unwrap());
        headers.insert("x-session-affinity", "fallback".parse().unwrap());
        assert_eq!(
            cache_key(&headers, &json!({})).unwrap().unwrap().value,
            "fallback"
        );
        headers.append("x-gradiated-session-id", "first".parse().unwrap());
        headers.append("x-gradiated-session-id", "second".parse().unwrap());
        assert!(cache_key(&headers, &json!({})).is_err());
        assert_eq!(
            cache_key(&headers, &json!({"session_id":"explicit"}))
                .unwrap()
                .unwrap()
                .value,
            "explicit"
        );
    }

    #[test]
    fn request_ids_windows_and_unstructured_user_metadata_are_not_affinity_keys() {
        let mut headers = HeaderMap::new();
        for header in [
            "x-client-request-id",
            "x-request-id",
            "x-codex-window-id",
            "x-arbitrary-session",
        ] {
            headers.insert(header, "changes-per-request".parse().unwrap());
        }
        headers.insert("x-codex-turn-metadata", "not-json".parse().unwrap());
        assert_eq!(cache_key(&headers, &json!({"session_id":null,"prompt_cache_key":null,"metadata":{"user_id":"user-account-id"}})).unwrap(), None);
        headers.insert(
            "x-codex-turn-metadata",
            "x".repeat(MAX_METADATA_BYTES + 1).parse().unwrap(),
        );
        assert_eq!(cache_key(&headers, &json!({})).unwrap(), None);
        assert_eq!(
            identifier("test", &"x".repeat(256)).unwrap().value.len(),
            256
        );
    }
}
