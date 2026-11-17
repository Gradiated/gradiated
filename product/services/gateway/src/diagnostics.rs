//! Bounded warning volume during outages. Counters and HTTP responses are never sampled.
pub(crate) mod body;

use std::{
    sync::Mutex,
    time::{Duration, Instant},
};

use axum::http::HeaderMap;
use sha2::{Digest, Sha256};

const WINDOW: Duration = Duration::from_secs(1);
const BURST: u32 = 10;

#[derive(Default)]
pub(crate) struct LogBudget {
    window: Option<Instant>,
    emitted: u32,
    suppressed: u64,
}

impl LogBudget {
    pub(crate) fn take_now(budget: &Mutex<Self>) -> Option<u64> {
        budget
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .take(Instant::now())
    }

    fn take(&mut self, now: Instant) -> Option<u64> {
        if self
            .window
            .is_none_or(|start| now.duration_since(start) >= WINDOW)
        {
            self.window = Some(now);
            self.emitted = 0;
        }

        if self.emitted == BURST {
            self.suppressed = self.suppressed.saturating_add(1);
            return None;
        }

        self.emitted += 1;
        Some(std::mem::take(&mut self.suppressed))
    }
}

// One fixed-size budget per call site and process. No user-controlled keys or growing maps.
// Tests run concurrently in one process, so each test thread has a budget of its own.
macro_rules! limited {
    ($level:expr, $($fields:tt)*) => {{
        #[cfg(not(test))]
        static BUDGET: std::sync::LazyLock<std::sync::Mutex<$crate::diagnostics::LogBudget>> =
            std::sync::LazyLock::new(Default::default);
        #[cfg(test)]
        thread_local! {
            static BUDGET: std::sync::Mutex<$crate::diagnostics::LogBudget> = Default::default();
        }

        if tracing::enabled!($level) {
            #[cfg(not(test))]
            let taken = $crate::diagnostics::LogBudget::take_now(&BUDGET);
            #[cfg(test)]
            let taken = BUDGET.with($crate::diagnostics::LogBudget::take_now);

            if let Some(suppressed_events) = taken {
                tracing::event!($level, suppressed_events, $($fields)*);
            }
        }
    }};
}
pub(crate) use limited;

macro_rules! limited_warn {
    ($($fields:tt)*) => { $crate::diagnostics::limited!(tracing::Level::WARN, $($fields)*) };
}
pub(crate) use limited_warn;

macro_rules! limited_error {
    ($($fields:tt)*) => { $crate::diagnostics::limited!(tracing::Level::ERROR, $($fields)*) };
}
pub(crate) use limited_error;

#[cfg(test)]
mod tests {
    use axum::http::HeaderValue;

    use super::*;

    #[test]
    fn bounds_bursts_and_reports_suppression_on_next_event() {
        let mut budget = LogBudget::default();
        let now = Instant::now();
        for _ in 0..BURST {
            assert_eq!(budget.take(now), Some(0));
        }
        assert_eq!(budget.take(now), None);
        assert_eq!(budget.take(now), None);
        assert_eq!(budget.take(now + WINDOW), Some(2));
        assert_eq!(budget.take(now + WINDOW), Some(0));
    }

    #[test]
    fn limited_macros_emit_at_their_level_with_the_suppression_count() {
        let logs = capture::Logs::default();
        let _guard = logs.start();

        limited_error!(phase = "error_probe", "probe");
        limited_warn!(phase = "warn_probe", "probe");

        let events = logs.events();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0]["level"], "ERROR");
        assert_eq!(events[0]["fields"]["phase"], "error_probe");
        assert_eq!(events[0]["fields"]["suppressed_events"], 0);
        assert_eq!(events[1]["level"], "WARN");
        assert_eq!(events[1]["fields"]["phase"], "warn_probe");
        assert_eq!(events[1]["fields"]["suppressed_events"], 0);
    }

    #[test]
    fn header_telemetry_keeps_cache_and_client_signals_without_secrets() {
        let mut headers = HeaderMap::new();
        headers.insert("user-agent", "Anthropic-Python/0.40.0".parse().unwrap());
        headers.insert("x-stainless-package-version", "0.40.0".parse().unwrap());
        headers.insert(
            "anthropic-beta",
            "prompt-caching-2024-07-31".parse().unwrap(),
        );
        headers.insert("cache-control", "no-cache".parse().unwrap());
        headers.insert(
            "x-gradiated-session-id",
            "session-secret-looking".parse().unwrap(),
        );
        headers.insert(
            "authorization",
            "Bearer must-not-appear-1234".parse().unwrap(),
        );

        let telemetry = header_telemetry(&headers);
        assert_eq!(telemetry.client, "anthropic-python");
        assert_eq!(telemetry.sdk_version.as_deref(), Some("0.40.0"));
        assert!(telemetry.prompt_cache_requested);
        assert_eq!(telemetry.cache_control.as_deref(), Some("no-cache"));
        assert_eq!(telemetry.credential_suffix.as_deref(), Some("…1234"));
        assert_eq!(telemetry.session_id_hash.as_deref().map(str::len), Some(16));
        assert!(!format!("{telemetry:?}").contains("must-not-appear"));
        assert!(!format!("{telemetry:?}").contains("session-secret-looking"));

        headers.insert(
            "cache-control",
            "public, secret=do-not-log-this".parse().unwrap(),
        );
        headers.insert("x-cache", "HIT; secret=do-not-log-this".parse().unwrap());
        let normalized = header_telemetry(&headers);
        assert_eq!(normalized.cache_control.as_deref(), Some("public"));
        assert_eq!(normalized.cache_status.as_deref(), Some("hit"));
        assert!(!format!("{normalized:?}").contains("do-not-log-this"));
    }

    #[test]
    fn header_telemetry_rejects_unbounded_values_and_unknown_clients() {
        let mut headers = HeaderMap::new();
        headers.insert("user-agent", "custom-client/1.0".parse().unwrap());
        headers.insert(
            "cache-status",
            HeaderValue::from_str(&"x".repeat(MAX_VALUE_LENGTH + 1)).unwrap(),
        );
        headers.insert("x-vllm-priority", "-10".parse().unwrap());

        let telemetry = header_telemetry(&headers);
        assert_eq!(telemetry.client, "other");
        assert_eq!(telemetry.cache_status, None);
        assert_eq!(telemetry.vllm_priority.as_deref(), Some("-10"));
    }

    #[test]
    fn request_span_emits_only_allowlisted_header_fields() {
        let logs = capture::Logs::default();
        let _guard = logs.start();
        let mut headers = HeaderMap::new();
        headers.insert("user-agent", "OpenAI/Python 1.2.3".parse().unwrap());
        headers.insert("cache-control", "no-cache".parse().unwrap());
        headers.insert("x-request-id", "request-secret-looking".parse().unwrap());
        headers.insert(
            "authorization",
            "Bearer do-not-log-this-9876".parse().unwrap(),
        );
        headers.insert("x-not-allowlisted", "arbitrary-value".parse().unwrap());

        let span = request_span(uuid::Uuid::from_u128(7), &headers);
        span.in_scope(|| tracing::info!(event = "header_telemetry_probe", "probe"));

        let event = logs
            .events()
            .into_iter()
            .find(|event| event["fields"]["event"] == "header_telemetry_probe")
            .expect("probe event should be captured");
        let span = &event["span"];
        assert_eq!(span["client"], "openai");
        assert_eq!(span["cache_control"], "no-cache");
        assert_eq!(span["credential_suffix"], "…9876");
        assert_eq!(span["request_id_hash"].as_str().unwrap().len(), 16);
        assert!(!event.to_string().contains("do-not-log-this"));
        assert!(!event.to_string().contains("request-secret-looking"));
        assert!(!event.to_string().contains("arbitrary-value"));
    }
}

#[cfg(test)]
pub(crate) mod capture {
    use std::{
        io,
        sync::{Arc, LazyLock, Mutex},
    };

    // tracing caches each callsite's interest globally. While a single dispatcher
    // is registered, a callsite first reached on a thread without a capture is
    // cached as never and stays silent for every later capture. A permanent
    // second dispatcher makes registration consult every live dispatcher.
    static PERMANENT_DISPATCH: LazyLock<tracing::Dispatch> = LazyLock::new(|| {
        tracing::Dispatch::new(tracing_subscriber::fmt().with_writer(io::sink).finish())
    });

    #[derive(Clone, Default)]
    pub(crate) struct Logs(Arc<Mutex<Vec<u8>>>);

    impl io::Write for Logs {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl Logs {
        pub(crate) fn start(&self) -> tracing::subscriber::DefaultGuard {
            LazyLock::force(&PERMANENT_DISPATCH);
            let logs = self.clone();
            tracing::subscriber::set_default(
                tracing_subscriber::fmt()
                    .json()
                    .with_ansi(false)
                    .without_time()
                    .with_writer(move || logs.clone())
                    .finish(),
            )
        }

        pub(crate) fn events(&self) -> Vec<serde_json::Value> {
            String::from_utf8(self.0.lock().unwrap().clone())
                .unwrap()
                .lines()
                .map(|line| serde_json::from_str(line).unwrap())
                .collect()
        }
    }
}

const MAX_VALUE_LENGTH: usize = 64;

#[derive(Debug, Default, PartialEq, Eq)]
struct HeaderTelemetry {
    client: &'static str,
    sdk_version: Option<String>,
    credential_suffix: Option<String>,
    cache_control: Option<String>,
    prompt_cache_requested: bool,
    cache_status: Option<String>,
    age: Option<String>,
    etag_present: bool,
    conditional_request: bool,
    request_id_hash: Option<String>,
    session_id_hash: Option<String>,
    traceparent_present: bool,
    content_encoding: Option<String>,
    accept: Option<String>,
    vllm_priority: Option<String>,
}

fn bounded(value: &str) -> Option<String> {
    let value = value.trim();
    (!value.is_empty() && value.len() <= MAX_VALUE_LENGTH && value.is_ascii())
        .then(|| value.to_owned())
}

fn normalized_header(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .and_then(bounded)
}

fn normalized_cache_control(headers: &HeaderMap) -> Option<String> {
    let value = normalized_header(headers, "cache-control")?;
    let directives = value
        .split(',')
        .filter_map(|directive| {
            let name = directive.split('=').next()?.trim().to_ascii_lowercase();
            matches!(
                name.as_str(),
                "no-cache"
                    | "no-store"
                    | "max-age"
                    | "s-maxage"
                    | "private"
                    | "public"
                    | "must-revalidate"
                    | "only-if-cached"
            )
            .then_some(name)
        })
        .collect::<Vec<_>>();
    (!directives.is_empty()).then(|| directives.join(","))
}

fn normalized_cache_status(headers: &HeaderMap) -> Option<String> {
    let value = normalized_header(headers, "cache-status")
        .or_else(|| normalized_header(headers, "x-cache"))?;
    let status = value
        .split(|character: char| character == ';' || character == ',' || character.is_whitespace())
        .find(|token| !token.is_empty())?
        .to_ascii_lowercase();
    matches!(
        status.as_str(),
        "hit" | "miss" | "bypass" | "fwd" | "stored" | "expired" | "stale" | "dynamic"
    )
    .then_some(status)
}

fn normalized_integer(headers: &HeaderMap, name: &str) -> Option<String> {
    let value = normalized_header(headers, name)?;
    value.parse::<i64>().ok().map(|value| value.to_string())
}

fn hash_header(headers: &HeaderMap, name: &str) -> Option<String> {
    let value = headers.get(name)?.to_str().ok()?;
    Some(format!("{:x}", Sha256::digest(value.as_bytes()))[..16].to_owned())
}

fn secret_suffix(headers: &HeaderMap) -> Option<String> {
    ["authorization", "x-api-key", "x-gradiated-api-key"]
        .into_iter()
        .find_map(|name| {
            let value = headers.get(name)?.to_str().ok()?.trim();
            (value.len() >= 4).then(|| format!("…{}", &value[value.len() - 4..]))
        })
}

pub(crate) fn client_family(user_agent: Option<&str>) -> &'static str {
    let user_agent = user_agent.unwrap_or_default().to_ascii_lowercase();
    [
        ("claude-code", "claude-code"),
        ("claude-cli/", "claude-code"),
        ("opencode", "opencode"),
        ("codex", "codex"),
        ("codex_cli", "codex"),
        ("openai-python", "openai-python"),
        ("openai/", "openai"),
        ("openai-node", "openai-node"),
        ("anthropic-python", "anthropic-python"),
        ("anthropic/", "anthropic"),
        ("anthropic-node", "anthropic-node"),
        ("curl/", "curl"),
    ]
    .into_iter()
    .find_map(|(needle, family)| user_agent.contains(needle).then_some(family))
    .unwrap_or("other")
}

fn header_telemetry(headers: &HeaderMap) -> HeaderTelemetry {
    let user_agent = headers
        .get("user-agent")
        .and_then(|value| value.to_str().ok())
        .filter(|value| value.len() <= 512);
    let stainless_package = normalized_header(headers, "x-stainless-package-version");
    let sdk_version = stainless_package
        .clone()
        .or_else(|| normalized_header(headers, "anthropic-version"));
    let prompt_cache_requested = headers
        .get("anthropic-beta")
        .and_then(|value| value.to_str().ok())
        .filter(|value| value.len() <= 8192)
        .is_some_and(|value| {
            value
                .split(',')
                .any(|item| item.trim().contains("prompt-caching"))
        });

    HeaderTelemetry {
        client: client_family(user_agent),
        sdk_version,
        credential_suffix: secret_suffix(headers),
        cache_control: normalized_cache_control(headers),
        prompt_cache_requested,
        cache_status: normalized_cache_status(headers),
        age: normalized_integer(headers, "age"),
        etag_present: headers.contains_key("etag"),
        conditional_request: headers.contains_key("if-none-match")
            || headers.contains_key("if-modified-since"),
        request_id_hash: hash_header(headers, "x-request-id"),
        session_id_hash: hash_header(headers, "x-gradiated-session-id"),
        traceparent_present: headers.contains_key("traceparent"),
        content_encoding: normalized_header(headers, "content-encoding"),
        accept: normalized_header(headers, "accept"),
        vllm_priority: normalized_integer(headers, "x-vllm-priority"),
    }
}

/// Identity fields are populated only after credential verification. This span
/// records only the fixed, normalized allowlist; it never records credentials,
/// cookies, arbitrary headers, or request bodies.
pub(crate) fn request_span(generation_id: uuid::Uuid, headers: &HeaderMap) -> tracing::Span {
    let telemetry = header_telemetry(headers);
    let span = tracing::info_span!("inference_request", service = "gateway", %generation_id,
        organization_id = tracing::field::Empty,
        workspace_id = tracing::field::Empty,
        api_key_id = tracing::field::Empty,
        client = telemetry.client,
        sdk_version = telemetry.sdk_version.as_deref().unwrap_or(""),
        credential_suffix = telemetry.credential_suffix.as_deref().unwrap_or(""),
        cache_control = telemetry.cache_control.as_deref().unwrap_or(""),
        prompt_cache_requested = telemetry.prompt_cache_requested,
        cache_status = telemetry.cache_status.as_deref().unwrap_or(""),
        age = telemetry.age.as_deref().unwrap_or(""),
        etag_present = telemetry.etag_present,
        conditional_request = telemetry.conditional_request,
        request_id_hash = telemetry.request_id_hash.as_deref().unwrap_or(""),
        session_id_hash = telemetry.session_id_hash.as_deref().unwrap_or(""),
        traceparent_present = telemetry.traceparent_present,
        content_encoding = telemetry.content_encoding.as_deref().unwrap_or(""),
        accept = telemetry.accept.as_deref().unwrap_or(""),
        vllm_priority = telemetry.vllm_priority.as_deref().unwrap_or(""),
        session_headers_present = tracing::field::Empty,
        opencode_session_hash = tracing::field::Empty,
        session_affinity_hash = tracing::field::Empty,
        generic_session_hash = tracing::field::Empty,
        claude_session_hash = tracing::field::Empty,
        codex_session_hash = tracing::field::Empty,
        codex_thread_hash = tracing::field::Empty,
        client_request_hash = tracing::field::Empty,
        codex_window_hash = tracing::field::Empty,
        codex_metadata_session_hash = tracing::field::Empty,
        codex_metadata_thread_hash = tracing::field::Empty,
        body_session_hash = tracing::field::Empty,
        prompt_cache_key_hash = tracing::field::Empty,
        client_metadata_session_hash = tracing::field::Empty,
        client_metadata_thread_hash = tracing::field::Empty,
        anthropic_metadata_session_hash = tracing::field::Empty,
        effective_session_source = tracing::field::Empty,
        effective_session_hash = tracing::field::Empty,
    );
    crate::session_telemetry::record_headers(&span, headers);
    span
}
