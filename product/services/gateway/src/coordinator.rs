use std::{collections::HashSet, sync::Arc};

use axum::http::HeaderMap;
use chrono::{DateTime, Utc};
use serde_json::Value;
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::{
    auth::{
        authenticate_credential, authorize_access, extract_api_key, AccessError,
        AuthenticatedIdentity,
    },
    generation::{CapturedPricing, CapturedPricingError},
    healthy_deployment_count,
    model::{ModelStatus, ServingDeployment, ServingDeploymentError, TextOutputModality},
    protocol::Protocol,
    request::parse_target,
    runtime::{openrouter_supports_parameter, FallbackRoutes},
    serving_state::{ServingState, ServingStateError},
    CatalogModel, ExternalModel, GatewayError, GatewayModel, GatewayModelDeployment,
    InferenceRequest, ModelAccess, RequestKind,
};

/// A runtime scheduling hint that only internal callers may set.
const RUNTIME_PRIORITY_HEADER: &str = "x-vllm-priority";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestMetadata {
    pub generation_id: Uuid,
    pub received_at: DateTime<Utc>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct QualifiedRequest {
    pub metadata: RequestMetadata,
    pub is_verification: bool,
    pub identity: AuthenticatedIdentity,
    pub local: Option<LocalCapacity>,
    /// For an adapter, the base model's deployments, which serve it without the adapter.
    pub base: Option<LocalCapacity>,
    pub external: Option<ExternalModel>,
    /// The model's own tokenizer, for counting when no deployment supplies one.
    pub tokenizer: Option<crate::PinnedTokenizer>,
    pub max_context_tokens: u64,
    pub max_prompt_tokens: u64,
    pub effective_output_tokens: u64,
    pub pricing: CapturedPricing,
    pub request: InferenceRequest,
    pub adapter: Option<crate::PrivateAdapter>,
}

#[cfg(test)]
impl QualifiedRequest {
    pub(crate) fn local_capacity(&self) -> &LocalCapacity {
        self.local.as_ref().expect("the request has local capacity")
    }

    pub(crate) fn local_capacity_mut(&mut self) -> &mut LocalCapacity {
        self.local.as_mut().expect("the request has local capacity")
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LocalCapacity {
    pub deployment: GatewayModelDeployment,
    pub deployments: Vec<GatewayModelDeployment>,
    pub release_digest: String,
}

impl LocalCapacity {
    /// `None` when the model has no available deployment.
    fn of(model: &GatewayModel) -> Result<Option<Self>, GatewayError> {
        match model.serving_deployment() {
            Ok(ServingDeployment {
                deployment,
                release_digest,
            }) => Ok(Some(Self {
                deployment: deployment.clone(),
                deployments: model.deployments.clone(),
                release_digest,
            })),
            Err(ServingDeploymentError::Missing) => Ok(None),
            Err(error) => Err(inconsistent_state(error.diagnostic_code())),
        }
    }
}

pub struct ClassifiedRequest {
    pub hosted: HostedRequest,
    pub request: Value,
}

pub struct HostedRequest {
    is_verification: bool,
    cache_key: Option<crate::session_affinity::CacheKey>,
    identity: AuthenticatedIdentity,
    model: GatewayModel,
    base: Option<GatewayModel>,
    external: Option<ExternalModel>,
    adapter: Option<crate::PrivateAdapter>,
}

impl HostedRequest {
    fn qualify(
        self,
        metadata: RequestMetadata,
        body: &[u8],
        kind: RequestKind,
    ) -> Result<QualifiedRequest, GatewayError> {
        let Self {
            is_verification,
            cache_key,
            identity,
            model,
            base,
            external,
            adapter,
        } = self;

        let mut request = InferenceRequest::parse_kind(body, kind)?;
        request.model = adapter
            .as_ref()
            .map_or_else(|| model.id.clone(), |adapter| adapter.model_id());
        request.runtime_model_name = adapter.as_ref().map(|adapter| adapter.runtime_name());
        request.cartridge_tokens = adapter
            .as_ref()
            .map_or(0, crate::PrivateAdapter::cartridge_tokens);
        if let Some(decision) = &mut request.decision {
            decision.model.clone_from(&model.id);
        }

        request.session_id = cache_key.as_ref().map(|key| key.value.clone());
        crate::session_telemetry::record_effective(cache_key.as_ref(), request.decision.is_some());

        let local = LocalCapacity::of(&model)?;
        let base = base
            .map(|base| LocalCapacity::of(&base))
            .transpose()?
            .flatten();
        if local.is_none() && base.is_none() && external.is_none() {
            return Err(no_capacity(&model, adapter.is_some()));
        }

        let system_one = local
            .as_ref()
            .is_some_and(|local| local.deployment.release.is_system_one());
        if request.decision.is_some() != system_one {
            return Err(GatewayError::unsupported_parameter("model"));
        }

        let output = model.properties.text_output();
        if request.stream && !output.streaming {
            return Err(GatewayError::unsupported_parameter("stream"));
        }

        // Partial Mode is a message field, so the parameter filter below never
        // sees it. Models whose catalog lists `partial` honour it; others keep
        // ignoring it.
        if model.properties.parameter("partial").is_some() {
            if request.parameters.contains_key("partial") {
                return Err(GatewayError::invalid_request(Some("partial")));
            }
            request.continue_final_message = request.partial_mode()?;
        }

        for (name, value) in &request.parameters {
            if model
                .properties
                .parameter(name)
                .is_some_and(|descriptor| !descriptor.accepts(value))
            {
                return Err(GatewayError::invalid_request(Some(name)));
            }
        }

        request
            .parameters
            .retain(|name, _| model.properties.parameter(name).is_some());
        // `partial` is declared so the catalog can advertise Partial Mode. It
        // belongs on the final message: models that declare it reject it in
        // the body above, and others ignore it here.
        request.parameters.remove("partial");

        let external = external.filter(|external| {
            external.is_direct()
                || request
                    .parameters
                    .keys()
                    .all(|name| openrouter_supports_parameter(external.id(), name))
        });
        if local.is_none() && base.is_none() && external.is_none() {
            return Err(no_capacity(&model, adapter.is_some()));
        }

        let effective_output_tokens = effective_output_tokens(&request, output)?;
        request.open_output_limit = request.output_token_limit().is_none()
            && OPEN_OUTPUT_LIMIT_MODELS.contains(&model.id.as_str());
        let input = model.properties.text_input();
        let pricing = CapturedPricing::for_service_tier(
            &input.pricing,
            &output.pricing,
            request.service_tier,
        )
        .map_err(|error| inconsistent_state(pricing_diagnostic_code(&error)))?;

        Ok(QualifiedRequest {
            metadata,
            is_verification,
            identity,
            adapter,
            local,
            base,
            external,
            tokenizer: model
                .tokenizer
                .clone()
                .filter(crate::PinnedTokenizer::valid),
            // The cartridge occupies K positions of the model's context.
            max_context_tokens: input
                .supported_inputs
                .max_context_length
                .value
                .saturating_sub(request.cartridge_tokens),
            max_prompt_tokens: input
                .supported_inputs
                .max_prompt_length
                .value
                .saturating_sub(request.cartridge_tokens),
            effective_output_tokens,
            pricing,
            request,
        })
    }
}

/// Keeps the errors that predate external capacity; only a mapped model may have
/// no deployments by design.
fn no_capacity(model: &GatewayModel, adapter: bool) -> GatewayError {
    if adapter {
        GatewayError::ModelUnavailable
    } else if model.openrouter_model_id.is_some() && model.deployments.is_empty() {
        GatewayError::RuntimeUnavailable
    } else {
        inconsistent_state(ServingDeploymentError::Missing.diagnostic_code())
    }
}

/// A checked credential and its workspace and account, reused across one request.
pub(crate) struct Authorization {
    identity: AuthenticatedIdentity,
    funds_hosted: bool,
    /// OpenRouter resells this capacity and fails over itself; serving its traffic
    /// through OpenRouter could route a request back to us.
    from_openrouter: bool,
}

impl Authorization {
    fn into_hosted_identity(self) -> Result<AuthenticatedIdentity, GatewayError> {
        if !self.funds_hosted {
            return Err(GatewayError::InsufficientBalance);
        }

        Ok(self.identity)
    }
}

#[derive(Clone)]
pub struct RequestCoordinator {
    serving_state: Arc<dyn ServingState>,
    verification_workspace_id: Option<Uuid>,
    fallback_routes: Option<FallbackRoutes>,
}

impl RequestCoordinator {
    pub fn new(serving_state: Arc<dyn ServingState>) -> Self {
        Self {
            serving_state,
            verification_workspace_id: None,
            fallback_routes: (!cfg!(test)).then(FallbackRoutes::default),
        }
    }

    pub fn with_verification_workspace(mut self, workspace_id: Option<Uuid>) -> Self {
        self.verification_workspace_id = workspace_id;
        self
    }

    pub fn with_fallback_routes(mut self, routes: FallbackRoutes) -> Self {
        self.fallback_routes = Some(routes);
        self
    }

    #[doc(hidden)]
    pub fn with_legacy_openrouter_fallback(mut self) -> Self {
        self.fallback_routes = None;
        self
    }

    fn external_model(
        &self,
        model: &GatewayModel,
        from_openrouter: bool,
        pinned: bool,
    ) -> Option<ExternalModel> {
        if from_openrouter
            || pinned
            || model
                .deployments
                .iter()
                .any(|deployment| deployment.release.is_system_one())
        {
            return None;
        }

        match &self.fallback_routes {
            Some(routes) => routes
                .contains(&model.id)
                .then(|| ExternalModel::direct(&model.id)),
            None => model.openrouter_model().map(ExternalModel::openrouter),
        }
    }

    pub fn qualify(
        &self,
        metadata: RequestMetadata,
        _headers: &HeaderMap,
        hosted: HostedRequest,
        body: &[u8],
        kind: RequestKind,
    ) -> Result<QualifiedRequest, GatewayError> {
        hosted.qualify(metadata, body, kind)
    }

    async fn prefer_ready_release(
        &self,
        mut model: GatewayModel,
        now: DateTime<Utc>,
        selection: Option<u128>,
    ) -> Result<GatewayModel, GatewayError> {
        if model.serving_deployment().is_err() {
            return Ok(model);
        }

        let releases = available_releases(&model);
        if model
            .deployments
            .iter()
            .filter(|deployment| deployment.status == crate::DeploymentStatus::Available)
            .count()
            < 2
        {
            return Ok(model);
        }

        let mut selected = None;
        let mut most_ready = 0;
        let mut eligible = Vec::new();
        for (index, digest) in releases.into_iter().rev() {
            let statuses = self
                .serving_state
                .deployment_statuses(&digest)
                .await
                .map_err(state_unavailable("deployment_status_read"))?;
            let candidates: Vec<_> = model
                .deployments
                .iter()
                .filter(|deployment| {
                    deployment.served_release_digest().ok().as_ref() == Some(&digest)
                })
                .cloned()
                .collect();
            let ready = healthy_deployment_count(&candidates, &statuses, now);
            let accepting: Vec<_> = statuses
                .into_iter()
                .filter(|status| status.accepting_requests)
                .collect();
            let accepting_count = healthy_deployment_count(&candidates, &accepting, now);
            if accepting_count > 0 {
                eligible.extend(
                    model
                        .deployments
                        .iter()
                        .enumerate()
                        .filter(|(_, deployment)| {
                            deployment.served_release_digest().ok().as_ref() == Some(&digest)
                                && healthy_deployment_count(
                                    std::slice::from_ref(*deployment),
                                    &accepting,
                                    now,
                                ) > 0
                        })
                        .map(|(candidate, deployment)| {
                            let active_requests = accepting
                                .iter()
                                .find(|status| status.deployment_id == deployment.id)
                                .and_then(|status| status.active_requests);
                            (candidate, active_requests)
                        }),
                );
                if ready > most_ready {
                    most_ready = ready;
                    selected = Some(index);
                }
            }
        }

        if let Some(mut index) = selected {
            if let Some(selection) = selection {
                let candidates: Vec<_> = eligible
                    .iter()
                    .filter(|(candidate, _)| {
                        same_model_release(
                            &model.deployments[index],
                            &model.deployments[*candidate],
                        )
                    })
                    .collect();
                let weights = crate::routing::route_weights(
                    candidates
                        .iter()
                        .map(|(_, active_requests)| *active_requests),
                );
                index = candidates
                    .iter()
                    .zip(weights)
                    .map(|((candidate, _), weight)| {
                        let id = model.deployments[*candidate].id;
                        let mut hash = Sha256::new();
                        hash.update(selection.to_be_bytes());
                        hash.update(id.as_bytes());
                        let score: [u8; 32] = hash.finalize().into();
                        (
                            crate::routing::weighted_score(&score, weight),
                            score,
                            id,
                            *candidate,
                        )
                    })
                    .max_by(|left, right| {
                        left.0
                            .total_cmp(&right.0)
                            .then_with(|| (left.1, left.2).cmp(&(right.1, right.2)))
                    })
                    .expect("selected release has an accepting replica")
                    .3;
            }
            model.deployments[..=index].rotate_right(1);
        }

        Ok(model)
    }

    pub async fn list_models(
        &self,
        headers: &HeaderMap,
        requested_at: DateTime<Utc>,
    ) -> Result<Vec<CatalogModel>, GatewayError> {
        let authorization = self.authorize(headers, requested_at).await?;
        let from_openrouter = authorization.from_openrouter;
        let identity = authorization.into_hosted_identity()?;

        // Another organization's own model is never listed, including to
        // OpenRouter, whose key belongs to its own organization, or to the
        // verification workspace.
        let models = self
            .serving_state
            .models_visible_to(ModelAccess::caller(&identity))
            .await
            .map_err(state_unavailable("catalog_read"))?;

        let mut catalog = Vec::with_capacity(models.len());
        for model in models {
            let model = self.prefer_ready_release(model, requested_at, None).await?;
            let mut statuses = Vec::new();
            if listed_release_digest(&model).is_some() {
                let selected = model
                    .serving_deployment()
                    .expect("validated serving deployment");
                for (index, digest) in available_releases(&model) {
                    if same_model_release(selected.deployment, &model.deployments[index]) {
                        statuses.extend(
                            self.serving_state
                                .deployment_statuses(&digest)
                                .await
                                .map_err(state_unavailable("deployment_status_read"))?,
                        );
                    }
                }
            }

            catalog.push(CatalogModel {
                healthy_deployments: healthy_deployment_count(
                    &model.deployments,
                    &statuses,
                    requested_at,
                ),
                external_capacity: self
                    .external_model(&model, from_openrouter, false)
                    .is_some(),
                model,
            });
        }

        Ok(catalog)
    }

    pub async fn classify(
        &self,
        headers: &HeaderMap,
        body: &[u8],
        received_at: DateTime<Utc>,
        protocol: Protocol,
    ) -> Result<ClassifiedRequest, GatewayError> {
        let mut is_verification = false;
        self.classify_with_traffic(headers, body, received_at, protocol, &mut is_verification)
            .await
    }

    pub(crate) async fn classify_with_traffic(
        &self,
        headers: &HeaderMap,
        body: &[u8],
        received_at: DateTime<Utc>,
        protocol: Protocol,
        is_verification: &mut bool,
    ) -> Result<ClassifiedRequest, GatewayError> {
        self.classify_authorized(headers, body, received_at, protocol, is_verification, None)
            .await
    }

    /// [`Self::classify_with_traffic`], reusing an authorization already made for this request.
    pub(crate) async fn classify_authorized(
        &self,
        headers: &HeaderMap,
        body: &[u8],
        received_at: DateTime<Utc>,
        protocol: Protocol,
        is_verification: &mut bool,
        authorization: Option<Authorization>,
    ) -> Result<ClassifiedRequest, GatewayError> {
        *is_verification = false;
        // A malformed or unsupported request is a local error on every route, so it
        // is rejected before identity.
        if headers.contains_key(RUNTIME_PRIORITY_HEADER) {
            return Err(GatewayError::invalid_request(Some("priority")));
        }

        let target = parse_target(body)?;
        protocol.validate_request(&target.request)?;
        let mut cache_key = crate::session_affinity::cache_key(headers, &target.request)?;

        let authorization = match authorization {
            Some(authorization) => authorization,
            None => self.authorize(headers, received_at).await?,
        };
        let header = "x-gradiated-deployment-id";
        if headers.contains_key("x-gradiated-verification-deployment") {
            return Err(GatewayError::invalid_request(Some(header)));
        }
        let verification = headers.contains_key(header)
            && self.verification_workspace_id == Some(authorization.identity.workspace_id);
        let deployment_target = if headers.contains_key(header) {
            if headers.get_all(header).iter().count() != 1 {
                return Err(GatewayError::invalid_request(Some(header)));
            }
            Some(
                headers
                    .get(header)
                    .and_then(|value| value.to_str().ok())
                    .and_then(|value| Uuid::parse_str(value).ok())
                    .ok_or_else(|| GatewayError::invalid_request(Some(header)))?,
            )
        } else {
            None
        };
        *is_verification = verification;

        let mut model_id = target.model.clone();
        model_id.make_ascii_lowercase();
        let mut adapter = None;
        // An organization's own model answers only its keys and the platform's
        // verification workspace; to anyone else it is an unknown model.
        let access = ModelAccess::calling(&authorization.identity, self.verification_workspace_id);
        let mut model = self
            .serving_state
            .model_for(access, &model_id)
            .await
            .map_err(state_unavailable("model_read"))?;
        if model.is_some()
            && self
                .serving_state
                .private_model_exists(authorization.identity.workspace_id, &target.model)
                .await
                .map_err(state_unavailable("private_adapter_read"))?
        {
            // A retired hosted model gives its name to the private model, as
            // happens when the catalog withholds an owned model that collides.
            if model
                .as_ref()
                .is_some_and(|model| model.status != ModelStatus::Retired)
            {
                return Err(inconsistent_state("ambiguous_model_name"));
            }
            model = None;
        }
        if model.is_none() {
            let resolved = self
                .serving_state
                .private_adapter(authorization.identity.workspace_id, &target.model)
                .await
                .map_err(state_unavailable("private_adapter_read"))?
                .ok_or(GatewayError::ModelNotFound)?;
            if resolved.workspace_id != authorization.identity.workspace_id || !resolved.is_valid()
            {
                return Err(inconsistent_state("invalid_private_adapter"));
            }
            model = self
                .serving_state
                .model_for(access, &resolved.base_model_id)
                .await
                .map_err(state_unavailable("model_read"))?;
            if model
                .as_ref()
                .is_some_and(|model| model.id != resolved.base_model_id)
            {
                return Err(GatewayError::ModelUnavailable);
            }

            adapter = Some(resolved);
        }
        let mut model = model.ok_or(GatewayError::ModelNotFound)?;
        let from_openrouter = authorization.from_openrouter;
        let identity = authorization.into_hosted_identity()?;
        let pinned = deployment_target.is_some();
        // A cartridge fails closed: without one, the answer is not the version's, so
        // neither the base model nor OpenRouter may serve it.
        let cartridge = adapter
            .as_ref()
            .is_some_and(crate::PrivateAdapter::is_cartridge);
        let external = self.external_model(&model, from_openrouter, pinned || cartridge);
        // An adapter that cannot be served falls back to its base model without it;
        // a pinned request keeps its exact deployment instead.
        let base = (adapter.is_some() && !pinned && !cartridge).then(|| {
            let mut base = model.clone();
            base.deployments.retain(|deployment| {
                !deployment.release.is_system_one() && !deployment.release.sends_token_ids()
            });
            base
        });
        if let Some(adapter) = &adapter {
            model.deployments.retain(|deployment| {
                deployment.release.lora_enabled == Some(true)
                    && (!adapter.is_cartridge()
                        || deployment.release.cartridge_enabled == Some(true))
                    && deployment
                        .release
                        .lora_base_model_revision
                        .as_ref()
                        .unwrap_or(&deployment.release.model_revision)
                        == &adapter.base_model_revision
                    && !deployment.release.is_system_one()
                    && !deployment.release.sends_token_ids()
            });
            if model.deployments.is_empty() && base.is_none() {
                return Err(GatewayError::ModelUnavailable);
            }
        }

        if model.status != ModelStatus::Available {
            return Err(GatewayError::ModelUnavailable);
        }

        if let Some(id) = deployment_target {
            model.deployments.retain(|deployment| {
                deployment.id == id && deployment.status != crate::DeploymentStatus::Draining
            });
            let deployment = model
                .deployments
                .first_mut()
                .ok_or(GatewayError::ModelUnavailable)?;
            deployment.status = crate::DeploymentStatus::Available;
        }

        if cache_key.is_none()
            && !model
                .deployments
                .iter()
                .any(|deployment| deployment.release.is_system_one())
        {
            cache_key = Some(crate::content_affinity::content_key(
                &target.request,
                body,
                protocol,
            ));
        }

        let selection = cache_key.as_ref().map_or_else(
            || Uuid::now_v7().as_u128(),
            |session| {
                let mut hash = Sha256::new();
                hash.update(identity.workspace_id.as_bytes());
                hash.update(session.value.as_bytes());
                u128::from_be_bytes(hash.finalize()[..16].try_into().expect("SHA-256 prefix"))
            },
        );
        let model = self
            .prefer_ready_release(model, received_at, Some(selection))
            .await?;
        let base = match base {
            Some(base) => Some(
                self.prefer_ready_release(base, received_at, Some(selection))
                    .await?,
            ),
            None => None,
        };

        Ok(ClassifiedRequest {
            hosted: HostedRequest {
                is_verification: verification,
                cache_key,
                identity,
                model,
                base,
                external,
                adapter,
            },
            request: target.request,
        })
    }

    /// Checks the credential alone, so a compressed body is inflated only for a known caller.
    pub(crate) async fn authenticate(
        &self,
        headers: &HeaderMap,
        received_at: DateTime<Utc>,
    ) -> Result<Authorization, GatewayError> {
        self.authorize(headers, received_at).await
    }

    async fn authorize(
        &self,
        headers: &HeaderMap,
        received_at: DateTime<Utc>,
    ) -> Result<Authorization, GatewayError> {
        let digest = extract_api_key(headers)?.digest();
        let credential = self
            .serving_state
            .credential(&digest)
            .await
            .map_err(state_unavailable("credential_read"))?
            .ok_or(GatewayError::InvalidApiKey)?;
        // A record cached before the field existed may be OpenRouter's, so it is
        // treated as OpenRouter's until the cache refreshes it.
        let from_openrouter = credential.openrouter_channel != Some(false);
        let identity = authenticate_credential(credential, received_at)?;

        tracing::Span::current()
            .record(
                "organization_id",
                tracing::field::display(identity.organization_id),
            )
            .record(
                "workspace_id",
                tracing::field::display(identity.workspace_id),
            )
            .record("api_key_id", tracing::field::display(identity.api_key_id));

        let workspace = self
            .serving_state
            .workspace(identity.workspace_id)
            .await
            .map_err(state_unavailable("workspace_read"))?
            .ok_or_else(|| inconsistent_state("workspace_missing"))?;
        let account = self
            .serving_state
            .account(identity.organization_id)
            .await
            .map_err(state_unavailable("account_read"))?
            .ok_or_else(|| inconsistent_state("account_missing"))?;
        let identity =
            authorize_access(identity, &workspace, &account).map_err(|error| match error {
                AccessError::InconsistentServingState => inconsistent_state("tenant_mismatch"),
                error => error.into(),
            })?;

        Ok(Authorization {
            identity,
            funds_hosted: account.funds_hosted_requests(),
            from_openrouter,
        })
    }
}

/// Logs why a serving-state read failed. The public error carries no cause,
/// and the diagnostic code never contains record data.
fn state_unavailable(phase: &'static str) -> impl FnOnce(ServingStateError) -> GatewayError {
    move |error| {
        crate::diagnostics::limited_warn!(
            phase,
            error_code = error.diagnostic_code(),
            "serving state read failed"
        );

        GatewayError::ServingStateUnavailable
    }
}

fn inconsistent_state(code: &'static str) -> GatewayError {
    warn_inconsistent_state(code);

    GatewayError::ServingStateUnavailable
}

fn pricing_diagnostic_code(error: &CapturedPricingError) -> &'static str {
    match error {
        CapturedPricingError::DuplicateComponent => "pricing_duplicate_component",
        CapturedPricingError::MissingRequiredComponent => "pricing_missing_component",
        CapturedPricingError::UnsafeInteger => "pricing_unsafe_integer",
    }
}

fn warn_inconsistent_state(code: &'static str) {
    crate::diagnostics::limited_warn!(error_code = code, "serving state is inconsistent");
}

fn available_releases(model: &GatewayModel) -> Vec<(usize, String)> {
    let mut seen = HashSet::new();
    model
        .deployments
        .iter()
        .enumerate()
        .filter(|(_, deployment)| deployment.status == crate::DeploymentStatus::Available)
        .filter_map(|(index, deployment)| {
            deployment
                .served_release_digest()
                .ok()
                .map(|digest| (index, digest))
        })
        .filter(|(_, digest)| seen.insert(digest.clone()))
        .collect()
}

fn same_model_release(left: &GatewayModelDeployment, right: &GatewayModelDeployment) -> bool {
    let mut release = left.release.clone();
    release
        .runtime_revision
        .clone_from(&right.release.runtime_revision);
    release == right.release
}

/// A model without an available deployment is listed as not ready. An invalid
/// one is listed the same way, but it is a state error, so its cause is logged.
fn listed_release_digest(model: &GatewayModel) -> Option<String> {
    if model.status != ModelStatus::Available {
        return None;
    }

    match model.serving_deployment() {
        Ok(serving) => Some(serving.release_digest),
        Err(ServingDeploymentError::Missing) => None,
        Err(error) => {
            warn_inconsistent_state(error.diagnostic_code());
            None
        }
    }
}

/// Models whose unset output limit goes to the runtime as no limit, so a
/// request can use the whole remaining context up to the runtime's maximum.
/// A fixed default would either cut reasoning short or, for long prompts,
/// exceed the context window. The catalog default stays the model maximum.
const OPEN_OUTPUT_LIMIT_MODELS: [&str; 2] = [
    "moonshotai/kimi-k3.1-pro",
    "yetalabs/kimi-k3.1-pro-abliterated",
];

fn effective_output_tokens(
    request: &InferenceRequest,
    output: &TextOutputModality,
) -> Result<u64, GatewayError> {
    if request.decision.is_some() {
        return Ok(0);
    }

    match request.output_token_limit() {
        Some(limit) if limit.value() > output.max_length.value => Err(
            GatewayError::context_length_exceeded(limit.parameter_name()),
        ),
        Some(limit) => Ok(limit.value()),
        None => Ok(output.default_length.value),
    }
}

#[cfg(test)]
#[path = "coordinator_test_support.rs"]
mod support;

#[cfg(test)]
#[path = "coordinator_qualify_tests.rs"]
mod qualify_tests;

#[cfg(test)]
#[path = "coordinator_listing_tests.rs"]
mod listing_tests;

#[cfg(test)]
#[path = "coordinator_auth_tests.rs"]
mod authorization_tests;

#[cfg(test)]
#[path = "coordinator_route_tests.rs"]
mod route_tests;

#[cfg(test)]
#[path = "coordinator_verification_tests.rs"]
mod verification_tests;

#[cfg(test)]
#[path = "coordinator_adapter_tests.rs"]
mod adapter_tests;

#[cfg(test)]
#[path = "coordinator_capacity_tests.rs"]
mod capacity_tests;

#[cfg(test)]
#[path = "coordinator_ownership_tests.rs"]
mod ownership_tests;
