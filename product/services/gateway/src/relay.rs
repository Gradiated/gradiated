use std::{
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
};

use axum::{
    body::Bytes,
    http::{HeaderMap, HeaderName, HeaderValue, StatusCode},
};
use futures_util::Stream;
use reqwest::{redirect::Policy, Client};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

use crate::{
    auth::{Provider, ProviderCredential, X_API_KEY},
    config::ProxyLimits,
    diagnostics::limited_warn,
    error::GatewayError,
};

pub(crate) use crate::request::parse_target;

const HOP_HEADER: HeaderName = HeaderName::from_static("x-gradiated-hop");
const GRADIATED_HEADER_PREFIX: &str = "x-gradiated-";

/// Hop-by-hop and transport headers that never cross a proxy boundary, plus the
/// credential and edge headers that belong to this gateway alone.
const STRIPPED_REQUEST_HEADERS: &[&str] = &[
    "authorization",
    "connection",
    "content-length",
    "cookie",
    "forwarded",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "x-api-key",
    "x-real-ip",
];

const STRIPPED_RESPONSE_HEADERS: &[&str] = &[
    "alt-svc",
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "set-cookie",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
];

/// Edge and platform header families that must not reach a provider.
const STRIPPED_REQUEST_PREFIXES: &[&str] = &["x-forwarded-", "cf-", "x-amzn-", "x-amz-cf-"];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RelayRoute {
    AnthropicMessages,
}

impl RelayRoute {
    pub fn provider(self) -> Provider {
        match self {
            Self::AnthropicMessages => Provider::Anthropic,
        }
    }

    fn credential_header(self) -> HeaderName {
        match self {
            Self::AnthropicMessages => X_API_KEY,
        }
    }
}

fn connection_named(headers: &HeaderMap) -> Vec<String> {
    headers
        .get_all("connection")
        .iter()
        .filter_map(|value| value.to_str().ok())
        .flat_map(|value| value.split(','))
        .map(|name| name.trim().to_ascii_lowercase())
        .filter(|name| !name.is_empty())
        .collect()
}

fn stripped_from_request(name: &str, connection: &[String]) -> bool {
    STRIPPED_REQUEST_HEADERS.contains(&name)
        || name.starts_with(GRADIATED_HEADER_PREFIX)
        || STRIPPED_REQUEST_PREFIXES
            .iter()
            .any(|prefix| name.starts_with(prefix))
        || connection.iter().any(|named| named == name)
}

/// Builds the upstream header set. The customer's provider credential is the only
/// credential that survives; no Gradiated header or key is forwarded.
pub fn upstream_headers(
    inbound: &HeaderMap,
    route: RelayRoute,
    credential: &ProviderCredential<'_>,
) -> Result<UpstreamHeaders, GatewayError> {
    if inbound.contains_key(&HOP_HEADER) {
        limited_warn!(error_code = "relay_loop", "provider relay refused");
        return Err(GatewayError::invalid_request(None));
    }

    let connection = connection_named(inbound);
    let mut upstream = HeaderMap::new();
    for (name, value) in inbound {
        if !stripped_from_request(name.as_str(), &connection) {
            upstream.append(name.clone(), value.clone());
        }
    }

    let mut secret = HeaderValue::from_str(credential.secret)
        .map_err(|_| GatewayError::invalid_request(None))?;
    secret.set_sensitive(true);
    upstream.insert(route.credential_header(), secret);
    upstream.insert(HOP_HEADER, HeaderValue::from_static("1"));
    // The caller receives the provider's exact bytes, and the edge never re-encodes them.
    upstream.insert(
        HeaderName::from_static("accept-encoding"),
        HeaderValue::from_static("identity"),
    );

    Ok(UpstreamHeaders(upstream))
}

/// A header set that has passed `upstream_headers`. The relay accepts nothing
/// else, so no caller can forward an unsanitized header set to a provider.
pub struct UpstreamHeaders(HeaderMap);

impl UpstreamHeaders {
    #[cfg(test)]
    pub(crate) fn get(&self, name: &str) -> Option<&HeaderValue> {
        self.0.get(name)
    }
}

/// Keeps the provider's own content headers, including `content-encoding`, and
/// drops everything that describes the provider connection.
fn downstream_headers(upstream: &HeaderMap) -> HeaderMap {
    let connection = connection_named(upstream);
    let mut downstream = HeaderMap::new();
    for (name, value) in upstream {
        let name_str = name.as_str();
        let stripped = STRIPPED_RESPONSE_HEADERS.contains(&name_str)
            || connection.iter().any(|named| named == name_str);
        if !stripped {
            downstream.append(name.clone(), value.clone());
        }
    }

    downstream
}

pub struct RelayResponse {
    pub status: StatusCode,
    pub headers: HeaderMap,
    pub body: RelayBody,
}

/// Carries the relay's permits, so every exit path releases the byte budget and
/// the in-flight slot when the caller drops the response. The request's own
/// deadline bounds this stream, including a provider that stalls mid-response.
pub struct RelayBody {
    inner: Pin<Box<dyn Stream<Item = reqwest::Result<Bytes>> + Send>>,
    _permits: RelayPermits,
}

impl Stream for RelayBody {
    type Item = Result<Bytes, RelayError>;

    fn poll_next(mut self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        self.inner
            .as_mut()
            .poll_next(context)
            .map(|chunk| chunk.map(|result| result.map_err(|error| failed("body", &error))))
    }
}

struct RelayPermits {
    _bytes: OwnedSemaphorePermit,
    _slot: OwnedSemaphorePermit,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
pub enum RelayError {
    #[error("the provider connection failed")]
    Unavailable,
    #[error("the provider request exceeded its deadline")]
    Timeout,
    #[error("provider relay is at capacity")]
    Overloaded,
    #[error("the request exceeds the relay request cap")]
    RequestTooLarge,
}

fn failed(phase: &'static str, error: &reqwest::Error) -> RelayError {
    limited_warn!(
        phase,
        error_code = diagnostic_code(error),
        "provider relay failed"
    );

    if error.is_timeout() {
        RelayError::Timeout
    } else {
        RelayError::Unavailable
    }
}

fn diagnostic_code(error: &reqwest::Error) -> &'static str {
    if error.is_connect() {
        "connect"
    } else if error.is_timeout() {
        "timeout"
    } else if error.is_body() {
        "body"
    } else if error.is_decode() {
        "decode"
    } else if error.is_request() {
        "request"
    } else {
        "other"
    }
}

impl From<RelayError> for GatewayError {
    fn from(error: RelayError) -> Self {
        match error {
            RelayError::Unavailable => Self::ProviderUnavailable,
            RelayError::Timeout => Self::ProviderTimeout,
            RelayError::Overloaded => Self::ProxyOverloaded,
            RelayError::RequestTooLarge => Self::PayloadTooLarge,
        }
    }
}

#[derive(Clone)]
pub struct ProviderRelay {
    client: Client,
    anthropic_origin: Arc<str>,
    limits: ProxyLimits,
    bytes: Arc<Semaphore>,
    slots: Arc<Semaphore>,
}

impl ProviderRelay {
    pub fn new(anthropic_origin: &str, limits: ProxyLimits) -> Result<Self, reqwest::Error> {
        let client = Client::builder()
            .redirect(Policy::none())
            .connect_timeout(limits.connect_timeout)
            .read_timeout(limits.idle_timeout)
            .build()?;

        Ok(Self {
            client,
            anthropic_origin: Arc::from(anthropic_origin),
            limits,
            bytes: Arc::new(Semaphore::new(permit_count(limits.request_buffer_bytes))),
            slots: Arc::new(Semaphore::new(permit_count(limits.max_in_flight))),
        })
    }

    pub async fn send(
        &self,
        route: RelayRoute,
        headers: UpstreamHeaders,
        body: Bytes,
    ) -> Result<RelayResponse, RelayError> {
        if body.len() as u64 > self.limits.max_request_bytes {
            return Err(RelayError::RequestTooLarge);
        }

        let permits = self.reserve(body.len())?;
        let url = self.url(route);
        let request = self
            .client
            .request(reqwest::Method::POST, url)
            .timeout(self.limits.total_timeout)
            .headers(headers.0)
            .body(body);
        // The total deadline covers the whole exchange; this one bounds the wait
        // for response headers alone.
        let response = tokio::time::timeout(self.limits.response_header_timeout, request.send())
            .await
            .map_err(|_| {
                limited_warn!(
                    phase = "send",
                    error_code = "header_timeout",
                    "provider relay failed"
                );
                RelayError::Timeout
            })?
            .map_err(|error| failed("send", &error))?;

        Ok(RelayResponse {
            status: response.status(),
            headers: downstream_headers(response.headers()),
            body: RelayBody {
                inner: Box::pin(response.bytes_stream()),
                _permits: permits,
            },
        })
    }

    /// The upstream URL is fixed per route. The caller's own path never selects it.
    fn url(&self, route: RelayRoute) -> String {
        match route {
            RelayRoute::AnthropicMessages => format!("{}/v1/messages", self.anthropic_origin),
        }
    }

    fn reserve(&self, length: usize) -> Result<RelayPermits, RelayError> {
        let slot = self
            .slots
            .clone()
            .try_acquire_owned()
            .map_err(|_| RelayError::Overloaded)?;
        // An empty body still reserves one permit, so the budget counts every relay.
        let requested = u32::try_from(length.max(1)).map_err(|_| RelayError::Overloaded)?;
        let bytes = self
            .bytes
            .clone()
            .try_acquire_many_owned(requested)
            .map_err(|_| RelayError::Overloaded)?;

        Ok(RelayPermits {
            _bytes: bytes,
            _slot: slot,
        })
    }
}

fn permit_count(configured: u64) -> usize {
    usize::try_from(configured.min(u32::MAX as u64)).unwrap_or(usize::MAX)
}

#[cfg(test)]
#[path = "relay_support.rs"]
pub(crate) mod support;

#[cfg(test)]
#[path = "relay_tests.rs"]
mod tests;
