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
    catalog::HostedCatalog,
    config::Limits,
    credentials::{self, Credentials, Provider},
    error::{Protocol, ProxyError},
    identity::IdentityCache,
    metrics::{Destination, Metrics},
    target,
    upstream::{gateway_headers, provider_headers, Admission, UpstreamResponse, Upstreams},
};

const GENERATION_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-generation-id");

#[derive(Clone)]
pub struct AppState {
    pub catalog: HostedCatalog,
    pub identity: IdentityCache,
    pub upstreams: Upstreams,
    pub metrics: Metrics,
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

    state
        .upstreams
        .to_gateway(
            parts.method.clone(),
            path_and_query,
            headers,
            body,
            admission,
        )
        .await
        .map_err(|error| ProxyError::from_upstream(error, true))
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

    let response = state
        .upstreams
        .to_provider(
            provider_key.provider,
            parts.method.clone(),
            &provider_path(parts),
            headers,
            body,
            admission,
        )
        .await
        .map_err(|error| ProxyError::from_upstream(error, false))?;

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
