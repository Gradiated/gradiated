use std::{
    future::Future,
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
    time::{Duration, Instant},
};

use axum::{
    body::Bytes,
    http::{header::AUTHORIZATION, HeaderMap, HeaderName, HeaderValue, Method, StatusCode},
};
use futures_util::Stream;
use reqwest::{redirect::Policy, Client};
use tokio::{
    sync::{OwnedSemaphorePermit, Semaphore},
    time::Sleep,
};

use crate::{
    capture::{Outcome, Recording},
    config::{Deadlines, Limits},
    credentials::{self, Provider, ProviderKey, X_API_KEY},
    metrics::{Destination, InFlight, Metrics},
};

const HOP_HEADER: HeaderName = HeaderName::from_static("x-gradiated-hop");

const HOP_BY_HOP: &[&str] = &[
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
];

const PROVIDER_PRIVATE: &[&str] = &[
    "authorization",
    "cookie",
    "forwarded",
    "x-api-key",
    "x-real-ip",
];
const PROVIDER_PRIVATE_PREFIXES: &[&str] = &["x-gradiated-", "x-forwarded-", "x-amzn-"];

const PROVIDER_RESPONSE_PRIVATE: &[&str] = &["alt-svc", "set-cookie"];

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
pub enum UpstreamError {
    #[error("the upstream connection failed")]
    Unavailable,
    #[error("the upstream did not answer in time")]
    Timeout,
    #[error("the proxy is at capacity")]
    Overloaded,
    #[error("the request would loop back through the proxy")]
    Loop,
}

pub struct Admission {
    admitted: Instant,
    budget: Arc<Semaphore>,
    _slot: OwnedSemaphorePermit,
    bytes: Option<OwnedSemaphorePermit>,
}

impl Admission {
    pub fn reserve(&mut self, length: usize) -> Result<(), UpstreamError> {
        let permits = u32::try_from(length).map_err(|_| overloaded("body_budget"))?;
        let permit = self
            .budget
            .clone()
            .try_acquire_many_owned(permits)
            .map_err(|_| overloaded("body_budget"))?;

        match &mut self.bytes {
            Some(held) => held.merge(permit),
            None => self.bytes = Some(permit),
        }

        Ok(())
    }

    pub fn release_bytes(&mut self) {
        self.bytes = None;
    }

    fn remaining(&self, total: Duration) -> Duration {
        total.saturating_sub(self.admitted.elapsed())
    }
}

pub struct UpstreamResponse {
    pub status: StatusCode,
    pub headers: HeaderMap,
    pub body: UpstreamBody,
}

#[derive(Clone)]
pub struct Upstreams {
    gateway: Client,
    provider: Client,
    gateway_origin: Arc<str>,
    anthropic_origin: Arc<str>,
    openai_origin: Arc<str>,
    limits: Limits,
    slots: Arc<Semaphore>,
    bytes: Arc<Semaphore>,
    metrics: Metrics,
}

pub struct Origins<'a> {
    pub gateway: &'a str,
    pub anthropic: &'a str,
    pub openai: &'a str,
}

impl Upstreams {
    pub fn new(
        origins: Origins<'_>,
        limits: Limits,
        metrics: Metrics,
    ) -> Result<Self, reqwest::Error> {
        let client = |deadlines: Deadlines| {
            Client::builder()
                .redirect(Policy::none())
                .connect_timeout(deadlines.connect)
                .build()
        };

        Ok(Self {
            gateway: client(limits.gateway)?,
            provider: client(limits.provider)?,
            gateway_origin: Arc::from(origins.gateway),
            anthropic_origin: Arc::from(origins.anthropic),
            openai_origin: Arc::from(origins.openai),
            limits,
            slots: Arc::new(Semaphore::new(limits.max_in_flight)),
            bytes: Arc::new(Semaphore::new(limits.request_buffer_bytes)),
            metrics,
        })
    }

    pub fn limits(&self) -> &Limits {
        &self.limits
    }

    pub fn admit(&self) -> Result<Admission, UpstreamError> {
        let slot = self
            .slots
            .clone()
            .try_acquire_owned()
            .map_err(|_| overloaded("in_flight"))?;

        Ok(Admission {
            admitted: Instant::now(),
            budget: self.bytes.clone(),
            _slot: slot,
            bytes: None,
        })
    }

    pub async fn to_gateway(
        &self,
        method: Method,
        path_and_query: &str,
        headers: HeaderMap,
        body: Bytes,
        admission: Admission,
    ) -> Result<UpstreamResponse, UpstreamError> {
        let request = self
            .gateway
            .request(method, format!("{}{path_and_query}", self.gateway_origin))
            .timeout(admission.remaining(self.limits.gateway.total))
            .headers(headers)
            .body(body);

        self.exchange(
            Destination::Gateway,
            self.limits.gateway,
            request,
            admission,
        )
        .await
    }

    pub async fn to_provider(
        &self,
        provider: Provider,
        method: Method,
        path_and_query: &str,
        headers: HeaderMap,
        body: Bytes,
        admission: Admission,
    ) -> Result<UpstreamResponse, UpstreamError> {
        let origin = match provider {
            Provider::Anthropic => &self.anthropic_origin,
            Provider::OpenAi => &self.openai_origin,
        };
        let request = self
            .provider
            .request(method, format!("{origin}{path_and_query}"))
            .timeout(admission.remaining(self.limits.provider.total))
            .headers(headers)
            .body(body);

        self.exchange(
            destination(provider),
            self.limits.provider,
            request,
            admission,
        )
        .await
    }

    async fn exchange(
        &self,
        destination: Destination,
        deadlines: Deadlines,
        request: reqwest::RequestBuilder,
        admission: Admission,
    ) -> Result<UpstreamResponse, UpstreamError> {
        let in_flight = self.metrics.in_flight(destination);
        let started = Instant::now();

        let response = tokio::time::timeout(deadlines.headers, request.send())
            .await
            .map_err(|_| {
                tracing::debug!(
                    ?destination,
                    error_code = "header_timeout",
                    "upstream failed"
                );
                UpstreamError::Timeout
            })?
            .map_err(|error| failed(destination, "send", &error))?;

        self.metrics
            .record_upstream_headers(destination, started.elapsed());

        let mut headers = response_headers(response.headers());
        if destination != Destination::Gateway {
            for name in PROVIDER_RESPONSE_PRIVATE {
                headers.remove(*name);
            }
        }

        Ok(UpstreamResponse {
            status: response.status(),
            headers,
            body: UpstreamBody {
                inner: Box::pin(response.bytes_stream()),
                idle: deadlines.idle,
                idle_timer: Box::pin(tokio::time::sleep(deadlines.idle)),
                destination,
                recording: None,
                _admission: admission,
                _in_flight: in_flight,
            },
        })
    }
}

fn destination(provider: Provider) -> Destination {
    match provider {
        Provider::Anthropic => Destination::Anthropic,
        Provider::OpenAi => Destination::OpenAi,
    }
}

fn overloaded(reason: &'static str) -> UpstreamError {
    tracing::debug!(error_code = reason, "request refused at capacity");

    UpstreamError::Overloaded
}

fn failed(destination: Destination, phase: &'static str, error: &reqwest::Error) -> UpstreamError {
    let code = if error.is_connect() {
        "connect"
    } else if error.is_timeout() {
        "timeout"
    } else if error.is_body() {
        "body"
    } else if error.is_request() {
        "request"
    } else {
        "other"
    };
    tracing::debug!(?destination, phase, error_code = code, "upstream failed");

    if error.is_timeout() {
        UpstreamError::Timeout
    } else {
        UpstreamError::Unavailable
    }
}

pub struct UpstreamBody {
    inner: Pin<Box<dyn Stream<Item = reqwest::Result<Bytes>> + Send>>,
    idle: Duration,
    idle_timer: Pin<Box<Sleep>>,
    destination: Destination,
    recording: Option<Recording>,
    _admission: Admission,
    _in_flight: InFlight,
}

impl UpstreamBody {
    pub fn record(&mut self, recording: Recording) {
        self.recording = Some(recording);
    }

    fn finish(&mut self, outcome: Outcome) {
        if let Some(recording) = &mut self.recording {
            recording.finish(outcome);
        }
    }
}

impl Stream for UpstreamBody {
    type Item = Result<Bytes, UpstreamError>;

    fn poll_next(mut self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        match self.inner.as_mut().poll_next(context) {
            Poll::Ready(Some(Ok(chunk))) => {
                let deadline = tokio::time::Instant::now() + self.idle;
                self.idle_timer.as_mut().reset(deadline);
                if let Some(recording) = &mut self.recording {
                    recording.observe(&chunk);
                }
                Poll::Ready(Some(Ok(chunk)))
            }
            Poll::Ready(Some(Err(error))) => {
                self.finish(Outcome::Error);
                Poll::Ready(Some(Err(failed(self.destination, "body", &error))))
            }
            Poll::Ready(None) => {
                self.finish(Outcome::Complete);
                Poll::Ready(None)
            }
            Poll::Pending => match self.idle_timer.as_mut().poll(context) {
                Poll::Ready(()) => {
                    tracing::debug!(
                        destination = ?self.destination,
                        error_code = "idle_timeout",
                        "upstream failed"
                    );
                    self.finish(Outcome::Error);
                    Poll::Ready(Some(Err(UpstreamError::Timeout)))
                }
                Poll::Pending => Poll::Pending,
            },
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

fn copy_headers(inbound: &HeaderMap, keep: impl Fn(&str) -> bool) -> HeaderMap {
    let connection = connection_named(inbound);
    let mut outbound = HeaderMap::new();
    for (name, value) in inbound {
        let name_str = name.as_str();
        let hop =
            HOP_BY_HOP.contains(&name_str) || connection.iter().any(|named| named == name_str);
        if !hop && keep(name_str) {
            outbound.append(name.clone(), value.clone());
        }
    }

    outbound
}

fn response_headers(upstream: &HeaderMap) -> HeaderMap {
    copy_headers(upstream, |_| true)
}

pub fn gateway_headers(inbound: &HeaderMap) -> HeaderMap {
    let mut outbound = copy_headers(inbound, |_| true);

    let gradiated = |name: &HeaderName, value: &HeaderValue| {
        let value = value.to_str().unwrap_or_default();
        let key = if *name == AUTHORIZATION {
            credentials::bearer_token(value).unwrap_or_default()
        } else {
            value
        };

        key.starts_with("grad_")
    };
    for name in [AUTHORIZATION, X_API_KEY] {
        if !outbound
            .get_all(&name)
            .iter()
            .all(|value| gradiated(&name, value))
        {
            outbound.remove(&name);
        }
    }

    outbound
}

pub fn provider_headers(
    inbound: &HeaderMap,
    key: &ProviderKey,
) -> Result<HeaderMap, UpstreamError> {
    if inbound.contains_key(&HOP_HEADER) {
        tracing::debug!(error_code = "relay_loop", "provider relay refused");
        return Err(UpstreamError::Loop);
    }

    let mut outbound = copy_headers(inbound, |name| {
        !PROVIDER_PRIVATE.contains(&name)
            && !PROVIDER_PRIVATE_PREFIXES
                .iter()
                .any(|prefix| name.starts_with(prefix))
    });

    let mut secret = inbound
        .get(&key.header)
        .cloned()
        .ok_or(UpstreamError::Unavailable)?;
    secret.set_sensitive(true);
    outbound.insert(key.header.clone(), secret);
    outbound.insert(HOP_HEADER, HeaderValue::from_static("1"));

    Ok(outbound)
}

#[cfg(test)]
#[path = "upstream_tests.rs"]
mod tests;
