use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

use axum::{
    body::{Body, Bytes},
    extract::{Request, State},
    http::{request::Parts, HeaderName, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use bytes::BytesMut;
use chrono::Utc;
use http_body_util::BodyExt;
use uuid::Uuid;

use crate::{
    capture::{Capture, Relay},
    catalog::HostedCatalog,
    config::Limits,
    credentials::{self, Credentials, Provider},
    error::{Protocol, ProxyError},
    identity::{Identity, IdentityCache},
    metrics::{Destination, Metrics},
    target,
    upstream::{gateway_headers, provider_headers, Admission, UpstreamResponse, Upstreams},
};

const GENERATION_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-generation-id");
const TASK_HEADER: HeaderName = HeaderName::from_static("x-gradiated-task");
const TRACE_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-trace-id");
const SESSION_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-session-id");

#[derive(Clone)]
pub struct AppState {
    pub catalog: HostedCatalog,
    pub identity: IdentityCache,
    pub upstreams: Upstreams,
    pub metrics: Metrics,
    pub capture: Capture,
    pub relay_enabled: bool,
    pub draining: Arc<AtomicBool>,
}

pub fn public_router(state: AppState) -> Router {
    Router::new()
        .fallback(|State(state): State<AppState>, request: Request| proxy(state, request))
        .with_state(state)
}

/// The gateway serves its health and metrics on its public port, so the proxy keeps
/// them private until the gateway moves them to a port of their own.
fn gateway_private(path: &str) -> bool {
    path == "/metrics" || path == "/health" || path.starts_with("/health/")
}

pub fn admin_router(state: AppState) -> Router {
    Router::new()
        .route("/health/live", get(|| async { StatusCode::OK }))
        .route("/health/ready", get(ready))
        .route("/metrics", get(metrics))
        .with_state(state)
}

async fn ready(State(state): State<AppState>) -> StatusCode {
    if state.catalog.is_loaded() && !state.draining.load(Ordering::SeqCst) {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    }
}

async fn metrics(State(state): State<AppState>) -> Response {
    state.metrics.set_catalog_age(state.catalog.age());

    (
        [(
            "content-type",
            "application/openmetrics-text; version=1.0.0; charset=utf-8",
        )],
        state.metrics.encode(),
    )
        .into_response()
}

enum Decision<'a> {
    Gateway,
    Provider { credentials: Credentials<'a> },
}

fn protocol(parts: &Parts) -> Protocol {
    let anthropic_key = credentials::extract(&parts.headers)
        .ok()
        .and_then(|credentials| credentials.provider)
        .is_some_and(|key| key.provider == Provider::Anthropic);

    if anthropic_key {
        Protocol::Anthropic
    } else {
        Protocol::OpenAi
    }
}

async fn proxy(state: AppState, request: Request) -> Response {
    let (parts, body) = request.into_parts();
    let protocol = protocol(&parts);
    let generation_id = Uuid::now_v7();

    let (destination, result) = if gateway_private(parts.uri.path()) {
        (Destination::Local, Err(ProxyError::NotFound))
    } else {
        serve(&state, &parts, body, generation_id).await
    };

    let mut response = match result {
        Ok(upstream) => {
            let mut response = Response::new(Body::from_stream(upstream.body));
            *response.status_mut() = upstream.status;
            *response.headers_mut() = upstream.headers;
            response
        }
        Err(error) => error.render(protocol),
    };

    response
        .headers_mut()
        .insert(GENERATION_ID_HEADER, id_header(generation_id));
    state
        .metrics
        .record_response(destination, response.status().as_u16());

    response
}

fn id_header(generation_id: Uuid) -> HeaderValue {
    HeaderValue::from_str(&generation_id.to_string()).expect("a UUID is a valid header value")
}

async fn serve(
    state: &AppState,
    parts: &Parts,
    body: Body,
    generation_id: Uuid,
) -> (Destination, Result<UpstreamResponse, ProxyError>) {
    let local = |error| (Destination::Local, Err(error));

    let credentials = match state
        .relay_enabled
        .then(|| credentials::extract(&parts.headers))
        .transpose()
    {
        Ok(credentials) => credentials,
        Err(_) => return local(ProxyError::InvalidApiKey),
    };

    let mut admission = match state.upstreams.admit() {
        Ok(admission) => admission,
        Err(error) => return local(ProxyError::from_upstream(error, false)),
    };
    let body = match read_body(body, state.upstreams.limits(), &mut admission).await {
        Ok(body) => body,
        Err(error) => return local(error),
    };

    match decide(state, credentials, &body) {
        Decision::Gateway => {
            let result = forward(state, parts, body, admission, generation_id).await;
            (Destination::Gateway, result)
        }
        Decision::Provider { credentials } => {
            let destination = match credentials.provider.as_ref().map(|key| key.provider) {
                Some(Provider::Anthropic) => Destination::Anthropic,
                _ => Destination::OpenAi,
            };
            let result = relay(state, parts, credentials, body, admission, generation_id).await;
            let destination = if result.is_err() {
                Destination::Local
            } else {
                destination
            };
            (destination, result)
        }
    }
}

async fn read_body(
    body: Body,
    limits: &Limits,
    admission: &mut Admission,
) -> Result<Bytes, ProxyError> {
    let read = async {
        let mut body = body;
        let mut buffer = BytesMut::new();

        while let Some(frame) = body.frame().await {
            let frame = frame.map_err(|_| ProxyError::InvalidRequest)?;
            let Ok(chunk) = frame.into_data() else {
                continue;
            };

            if buffer.len() + chunk.len() > limits.max_request_bytes {
                return Err(ProxyError::PayloadTooLarge);
            }

            admission
                .reserve(chunk.len())
                .map_err(|error| ProxyError::from_upstream(error, false))?;
            buffer.extend_from_slice(&chunk);
        }

        Ok(buffer.freeze())
    };

    tokio::time::timeout(limits.body_read, read)
        .await
        .map_err(|_| ProxyError::RequestTimeout)?
}

fn decide<'a>(state: &AppState, credentials: Option<Credentials<'a>>, body: &[u8]) -> Decision<'a> {
    let Some(credentials) = credentials.filter(|credentials| credentials.provider.is_some()) else {
        return Decision::Gateway;
    };

    if target::model(body).is_some_and(|model| state.catalog.is_hosted(&model)) {
        return Decision::Gateway;
    }

    Decision::Provider { credentials }
}

fn provider_path(parts: &Parts) -> String {
    let path_and_query = parts.uri.path_and_query().map_or("/", |path| path.as_str());

    if path_and_query.starts_with("/v1/") {
        path_and_query.to_owned()
    } else {
        format!("/v1{path_and_query}")
    }
}

async fn forward(
    state: &AppState,
    parts: &Parts,
    body: Bytes,
    admission: Admission,
    generation_id: Uuid,
) -> Result<UpstreamResponse, ProxyError> {
    let path_and_query = parts.uri.path_and_query().map_or("/", |path| path.as_str());
    let mut headers = gateway_headers(&parts.headers);
    headers.insert(GENERATION_ID_HEADER, id_header(generation_id));

    let capture = if state.capture.is_enabled() && parts.headers.contains_key(&TASK_HEADER) {
        let state = state.clone();
        let headers = parts.headers.clone();
        let body = body.clone();
        let path = path_and_query.to_owned();
        Some(tokio::spawn(async move {
            capture_hosted(&state, &headers, generation_id, &path, &body).await
        }))
    } else {
        None
    };

    let mut response = state
        .upstreams
        .to_gateway(
            parts.method.clone(),
            path_and_query,
            headers,
            body,
            admission,
        )
        .await
        .map_err(|error| ProxyError::from_upstream(error, true))?;

    // Pending lookups can warm the cache, but never delay the response.
    let request = match capture {
        Some(lookup) if lookup.is_finished() => lookup.await.ok().flatten(),
        _ => None,
    };
    if let Some(mut request) = request {
        request.hosted = true;
        if let Some(recording) =
            state
                .capture
                .record(request, response.status.as_u16(), &response.headers)
        {
            response.body.record(recording);
        }
    }

    Ok(response)
}

async fn capture_hosted(
    state: &AppState,
    headers: &axum::http::HeaderMap,
    generation_id: Uuid,
    path: &str,
    body: &Bytes,
) -> Option<Relay> {
    let provider = match path.split('?').next()? {
        "/v1/messages" | "/messages" => Provider::Anthropic,
        "/v1/chat/completions" | "/chat/completions" | "/v1/responses" | "/responses" => {
            Provider::OpenAi
        }
        _ => return None,
    };
    let key = credentials::extract(headers).ok()?.api_key?;
    let identity = tokio::time::timeout(
        std::time::Duration::from_secs(1),
        state.identity.authorize(&key, Utc::now()),
    )
    .await
    .ok()?
    .ok()?;

    captured(
        &identity,
        headers,
        generation_id,
        provider,
        path.to_owned(),
        body.clone(),
    )
}

async fn relay(
    state: &AppState,
    parts: &Parts,
    credentials: Credentials<'_>,
    body: Bytes,
    admission: Admission,
    generation_id: Uuid,
) -> Result<UpstreamResponse, ProxyError> {
    let (Some(api_key), Some(provider_key)) = (credentials.api_key, credentials.provider) else {
        return Err(ProxyError::InvalidApiKey);
    };

    let identity = state.identity.authorize(&api_key, Utc::now()).await?;
    let headers = provider_headers(&parts.headers, &provider_key)
        .map_err(|error| ProxyError::from_upstream(error, false))?;

    let path = provider_path(parts);

    let mut response = state
        .upstreams
        .to_provider(
            provider_key.provider,
            parts.method.clone(),
            &path,
            headers,
            body.clone(),
            admission,
        )
        .await
        .map_err(|error| ProxyError::from_upstream(error, false))?;

    if let Some(relay) = captured(
        &identity,
        &parts.headers,
        generation_id,
        provider_key.provider,
        path,
        body,
    ) {
        if let Some(recording) =
            state
                .capture
                .record(relay, response.status.as_u16(), &response.headers)
        {
            response.body.record(recording);
        }
    }

    tracing::info!(
        %generation_id,
        organization_id = %identity.organization_id,
        workspace_id = %identity.workspace_id,
        api_key_id = %identity.api_key_id,
        provider = provider_key.provider.as_str(),
        provider_status = response.status.as_u16(),
        event = "provider_relay",
        "request relayed to the provider with the customer key"
    );

    Ok(response)
}

fn captured(
    identity: &Identity,
    headers: &axum::http::HeaderMap,
    generation_id: Uuid,
    provider: Provider,
    path: String,
    request: Bytes,
) -> Option<Relay> {
    if !identity.trace_capture_enabled {
        return None;
    }

    let header = |name: &HeaderName| {
        headers
            .get(name)
            .and_then(|value| value.to_str().ok())
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
    };

    Some(Relay {
        hosted: false,
        generation_id,
        workspace_id: identity.workspace_id,
        task: header(&TASK_HEADER)?,
        trace_id: header(&TRACE_ID_HEADER),
        session_id: header(&SESSION_ID_HEADER),
        provider,
        path,
        retention_days: identity.trace_retention_days,
        request_content_type: header(&axum::http::header::CONTENT_TYPE),
        request_content_encoding: header(&axum::http::header::CONTENT_ENCODING)
            .filter(|coding| !coding.trim().eq_ignore_ascii_case("identity")),
        request,
    })
}
