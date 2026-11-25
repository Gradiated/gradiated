use std::{collections::HashMap, sync::Arc, time::Duration};

use async_trait::async_trait;
use futures_util::future::BoxFuture;
use gradiated_credentials::{CredentialLoader, Provider};
use reqwest::{header, redirect::Policy, Url};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use super::{
    client::{
        one_shot_body, open_events, read_completion_body, record_rejection, remaining_until, send,
        within, CONNECT_TIMEOUT,
    },
    external_chat::{failure_for_code, normalize_completion, ChatStream, Names, UpstreamBilling},
    progress::ProgressStream,
    ExternalCapacity, ExternalRequest, FailureCause, ProtocolViolation, RuntimeClientError,
    RuntimeCompletion, RuntimeEventStream, RuntimeFailure, RuntimeFailureKind, MIN_FALLBACK_BUDGET,
};
use crate::{cache::LazyTtlCache, model::MAX_SAFE_INTEGER, NormalizedUsage};

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "lowercase")]
pub(super) enum FallbackVendor {
    Baseten,
    Modal,
}

impl FallbackVendor {
    pub(super) fn as_str(self) -> &'static str {
        match self {
            Self::Baseten => "baseten",
            Self::Modal => "modal",
        }
    }

    fn credential(self) -> Provider {
        match self {
            Self::Baseten => Provider::Baseten,
            Self::Modal => Provider::Modal,
        }
    }

    fn accepts_url(self, url: &Url) -> bool {
        match (self, url.scheme(), url.host_str()) {
            (Self::Baseten, "https", Some("inference.baseten.co")) => url.port().is_none(),
            (Self::Modal, "https", Some(host)) => {
                url.port().is_none()
                    && host
                        .strip_suffix(".modal.direct")
                        .is_some_and(|prefix| !prefix.is_empty())
            }
            (_, "http", Some("127.0.0.1" | "[::1]" | "localhost")) => true,
            _ => false,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct TokenRates {
    input: u64,
    cached_input: u64,
    output: u64,
    cache_write: Option<u64>,
}

impl TokenRates {
    pub(super) fn cost(self, usage: NormalizedUsage) -> Option<u64> {
        let uncached = usage.input_tokens() - usage.cached_input_tokens();
        let cost = u128::from(uncached) * u128::from(self.input)
            + u128::from(usage.cached_input_tokens()) * u128::from(self.cached_input)
            + u128::from(usage.cache_write_tokens()) * u128::from(self.cache_write.unwrap_or(0))
            + u128::from(usage.output_tokens()) * u128::from(self.output);

        (cost <= u128::from(MAX_SAFE_INTEGER)).then_some(cost as u64)
    }

    fn valid(self) -> bool {
        [
            self.input,
            self.cached_input,
            self.output,
            self.cache_write.unwrap_or(0),
        ]
        .into_iter()
        .all(|rate| rate <= MAX_SAFE_INTEGER)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct FallbackRoute {
    provider: FallbackVendor,
    base_url: String,
    model: String,
    response_model: Option<String>,
    nano_usd_per_token: TokenRates,
}

impl FallbackRoute {
    fn endpoint(&self) -> Option<Url> {
        let url = Url::parse(&format!(
            "{}/chat/completions",
            self.base_url.trim_end_matches('/')
        ))
        .ok()?;

        (self.provider.accepts_url(&url)
            && url.username().is_empty()
            && url.password().is_none()
            && url.query().is_none()
            && url.fragment().is_none()
            && url.path() == "/v1/chat/completions")
            .then_some(url)
    }
}

const PRODUCTION_FALLBACK_ROUTES: &str = include_str!("fallback_routes.json");

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct FallbackRoutes(HashMap<String, Vec<FallbackRoute>>);

impl FallbackRoutes {
    pub(crate) fn production() -> Self {
        Self::parse(Some(PRODUCTION_FALLBACK_ROUTES))
            .expect("embedded fallback_routes.json must be valid")
    }

    pub(crate) fn parse(raw: Option<&str>) -> Option<Self> {
        let routes: Self = match raw {
            Some(raw) => {
                Self(serde_json::from_value(crate::json::strict_json(raw.as_bytes()).ok()?).ok()?)
            }
            None => Self::default(),
        };
        let valid = routes.0.iter().all(|(model, entries)| {
            !model.is_empty()
                && model.chars().count() <= 200
                && !model
                    .chars()
                    .any(|ch| ch.is_ascii_uppercase() || ch.is_whitespace() || ch.is_control())
                && !entries.is_empty()
                && entries.len() <= 2
                && (entries.len() == 1 || entries[0].provider != entries[1].provider)
                && entries.iter().all(|route| {
                    !route.model.is_empty()
                        && route.model.len() <= 300
                        && route.model.trim() == route.model
                        && !route.model.chars().any(char::is_control)
                        && route.response_model.as_deref().is_none_or(|model| {
                            !model.is_empty()
                                && model.len() <= 300
                                && model.trim() == model
                                && !model.chars().any(char::is_control)
                        })
                        && route.endpoint().is_some()
                        && route.nano_usd_per_token.valid()
                })
        });

        valid.then_some(routes)
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub(crate) fn contains(&self, model: &str) -> bool {
        self.0.contains_key(model)
    }
}

struct FallbackProvider {
    vendor: FallbackVendor,
    client: reqwest::Client,
    endpoint: Url,
    model: String,
    response_model: Option<String>,
    rates: TokenRates,
    credentials: Arc<CredentialLoader>,
}

impl FallbackProvider {
    async fn send(
        &self,
        request: &ExternalRequest,
        accept: &str,
        affinity: Option<&str>,
    ) -> Result<reqwest::Response, RuntimeFailure> {
        let key = self
            .credentials
            .load(self.vendor.credential())
            .await
            .map_err(|_| {
                crate::diagnostics::limited_warn!(
                    error_code = "fallback_credential_unavailable",
                    upstream_provider = self.vendor.as_str(),
                    "Fallback provider credential could not be loaded"
                );
                RuntimeFailure::caused(RuntimeFailureKind::Unavailable, FailureCause::Credential)
            })?;
        let mut body = request
            .request
            .clone()
            .into_external_body(request.output_tokens, &self.model);
        if request.request.stream {
            let options = body.entry("stream_options").or_insert_with(|| json!({}));
            if !options.is_object() {
                *options = json!({});
            }
            if let Some(map) = options.as_object_mut() {
                map.remove("continuous_usage_stats");
                map.insert("include_usage".to_owned(), Value::Bool(true));
            }
        }

        let body = Value::Object(body);
        crate::diagnostics::body::record_value("runtime_request", &body, None);
        let encoded = serde_json::to_vec(&body).map_err(|_| ProtocolViolation::Json)?;
        let mut upstream = self
            .client
            .post(self.endpoint.clone())
            .bearer_auth(key)
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, accept)
            .body(one_shot_body(encoded));
        if let (FallbackVendor::Modal, Some(affinity)) = (self.vendor, affinity) {
            upstream = upstream.header("Modal-Routing-Affinity-Key", affinity);
        }

        let response = send(upstream).await?;
        if response.status().is_success() {
            return Ok(response);
        }

        let headers = response.headers().clone();
        let code = record_rejection(response).await.as_u16();

        Err(failure_for_code(code, NormalizedUsage::zero()).with_retry_after(&headers))
    }

    fn names(&self, request: &ExternalRequest) -> Names {
        Names::new(
            request,
            &self.model,
            UpstreamBilling::Direct(self.vendor, self.rates),
        )
        .with_response_model(self.response_model.as_deref())
    }

    async fn complete(
        &self,
        request: &ExternalRequest,
        affinity: Option<&str>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        within(remaining_until(request.deadline)?, async {
            let response = self.send(request, "application/json", affinity).await?;
            let body = read_completion_body(response).await?;

            normalize_completion(&body, &self.names(request))
        })
        .await
    }

    async fn stream(
        &self,
        request: &ExternalRequest,
        affinity: Option<&str>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let remaining = remaining_until(request.deadline)?;
        let deadline = tokio::time::Instant::now() + remaining;
        let stream = within(remaining, async {
            let response = self.send(request, "text/event-stream", affinity).await?;
            let mut stream = ChatStream::new(open_events(response)?, self.names(request));
            // A provider can send a role followed by an error before producing an answer.
            stream.peek(16).await?;

            Ok(stream)
        })
        .await?;

        Ok(Box::new(ProgressStream::new(Box::new(stream), deadline)))
    }
}

pub struct FallbackRouter {
    models: HashMap<String, Vec<FallbackProvider>>,
    affinity: LazyTtlCache<String, FallbackVendor>,
}

impl FallbackRouter {
    pub async fn connect(routes: &FallbackRoutes) -> Result<Self, RuntimeClientError> {
        if routes.0.is_empty() {
            return Ok(Self::new(HashMap::new()));
        }

        let aws = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new("us-east-1"))
            .load()
            .await;
        Self::with_loader(
            routes,
            CredentialLoader::new(aws_sdk_secretsmanager::Client::new(&aws)),
        )
    }

    pub(super) fn with_loader(
        routes: &FallbackRoutes,
        loader: CredentialLoader,
    ) -> Result<Self, RuntimeClientError> {
        let client = reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .redirect(Policy::none())
            .build()?;
        let credentials = Arc::new(loader);
        let models = routes
            .0
            .iter()
            .map(|(model, routes)| {
                let providers = routes
                    .iter()
                    .map(|route| FallbackProvider {
                        vendor: route.provider,
                        client: client.clone(),
                        endpoint: route.endpoint().expect("validated provider endpoint"),
                        model: route.model.clone(),
                        response_model: route.response_model.clone(),
                        rates: route.nano_usd_per_token,
                        credentials: credentials.clone(),
                    })
                    .collect();

                (model.clone(), providers)
            })
            .collect();

        Ok(Self::new(models))
    }

    fn new(models: HashMap<String, Vec<FallbackProvider>>) -> Self {
        Self {
            models,
            affinity: LazyTtlCache::new(Duration::from_secs(15 * 60), 4_096),
        }
    }

    async fn route<T>(
        &self,
        request: &ExternalRequest,
        attempt: impl for<'a> Fn(
                &'a FallbackProvider,
                &'a ExternalRequest,
                Option<&'a str>,
            ) -> BoxFuture<'a, Result<T, RuntimeFailure>>
            + Send,
    ) -> Result<T, RuntimeFailure> {
        let providers = self.models.get(request.model.id()).ok_or_else(|| {
            RuntimeFailure::caused(
                RuntimeFailureKind::Unavailable,
                FailureCause::Protocol(ProtocolViolation::Dispatch),
            )
        })?;
        let affinity = request.request.session_id.as_deref().map(|session| {
            let mut hash = Sha256::new();
            hash.update(request.workspace_id.as_bytes());
            hash.update((request.model.id().len() as u64).to_be_bytes());
            hash.update(request.model.id().as_bytes());
            hash.update(session.as_bytes());

            let digest = hash.finalize();
            (format!("{digest:x}"), digest[0])
        });
        let preferred = affinity
            .as_ref()
            .and_then(|(key, _)| self.affinity.get(key));
        let index =
            match preferred.and_then(|vendor| providers.iter().position(|p| p.vendor == vendor)) {
                Some(index) => index,
                None => {
                    let byte = affinity
                        .as_ref()
                        .map_or(request.generation_id.as_bytes()[15], |(_, byte)| *byte);
                    usize::from(byte) % providers.len()
                }
            };

        for (try_index, provider) in providers[index..]
            .iter()
            .chain(&providers[..index])
            .enumerate()
        {
            let affinity_key = affinity.as_ref().map(|(key, _)| key.as_str());
            match attempt(provider, request, affinity_key).await {
                Ok(result) => {
                    if let Some((key, _)) = affinity {
                        self.affinity.store(key, provider.vendor);
                    }
                    return Ok(result);
                }
                Err(failure) => {
                    tracing::debug!(generation_id = %request.generation_id,
                        upstream_provider = provider.vendor.as_str(), code = failure.diagnostic_code(),
                        "Fallback provider failed");

                    // Retry another provider on any pre-output, zero-usage failure — including
                    // 400/422 — so a provider-specific parameter or model rejection can still
                    // succeed on the other provider.
                    if try_index + 1 == providers.len()
                        || !failure.usage().is_zero()
                        || remaining_until(request.deadline).unwrap_or_default()
                            < MIN_FALLBACK_BUDGET
                    {
                        return Err(failure);
                    }
                }
            }
        }

        unreachable!("validated fallback routes have a provider")
    }
}

#[async_trait]
impl ExternalCapacity for FallbackRouter {
    async fn complete(
        &self,
        request: ExternalRequest,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        self.route(&request, |provider, request, affinity| {
            Box::pin(provider.complete(request, affinity))
        })
        .await
    }

    async fn stream(
        &self,
        request: ExternalRequest,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        self.route(&request, |provider, request, affinity| {
            Box::pin(provider.stream(request, affinity))
        })
        .await
    }
}
