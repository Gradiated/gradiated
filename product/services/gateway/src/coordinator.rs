use std::sync::Arc;

use axum::http::HeaderMap;
use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::{
    auth::{authenticate_credential, authorize_access, credential_digest, AuthenticatedIdentity},
    domain::{BillingMode, ModelStatus},
    serving_state::ServingState,
    ChatCompletionRequest, GatewayError, GatewayModel, GatewayModelDeployment, InputTokenPrice,
    OutputTokenPrice,
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestMetadata {
    pub generation_id: Uuid,
    pub received_at: DateTime<Utc>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CapturedPricing {
    pub input: Vec<InputTokenPrice>,
    pub output: Vec<OutputTokenPrice>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct QualifiedRequest {
    pub metadata: RequestMetadata,
    pub identity: AuthenticatedIdentity,
    pub deployment: GatewayModelDeployment,
    pub served_release_digest: String,
    pub max_context_tokens: u64,
    pub max_prompt_tokens: u64,
    pub effective_output_tokens: u64,
    pub pricing: CapturedPricing,
    pub request: ChatCompletionRequest,
}

#[derive(Clone)]
pub struct RequestCoordinator {
    serving_state: Arc<dyn ServingState>,
}

impl RequestCoordinator {
    pub fn new(serving_state: Arc<dyn ServingState>) -> Self {
        Self { serving_state }
    }

    pub async fn qualify(
        &self,
        metadata: RequestMetadata,
        headers: &HeaderMap,
        body: &[u8],
    ) -> Result<QualifiedRequest, GatewayError> {
        let identity = self.authenticate(headers, metadata.received_at).await?;
        let identity = self.authorize(identity).await?;
        let request = ChatCompletionRequest::parse(body)?;
        let model = self.load_model(&request.model).await?;
        qualify_model_request(metadata, identity, request, model)
    }

    async fn authenticate(
        &self,
        headers: &HeaderMap,
        received_at: DateTime<Utc>,
    ) -> Result<AuthenticatedIdentity, GatewayError> {
        let digest = credential_digest(headers).map_err(|_| GatewayError::InvalidApiKey)?;
        let credential = self
            .serving_state
            .credential(&digest)
            .await
            .map_err(|_| GatewayError::ServingStateUnavailable)?
            .ok_or(GatewayError::InvalidApiKey)?;
        authenticate_credential(credential, received_at).map_err(|_| GatewayError::InvalidApiKey)
    }

    async fn authorize(
        &self,
        identity: AuthenticatedIdentity,
    ) -> Result<AuthenticatedIdentity, GatewayError> {
        let workspace = self
            .serving_state
            .workspace(identity.workspace_id)
            .await
            .map_err(|_| GatewayError::ServingStateUnavailable)?
            .ok_or(GatewayError::ServingStateUnavailable)?;
        let account = self
            .serving_state
            .account(identity.organization_id)
            .await
            .map_err(|_| GatewayError::ServingStateUnavailable)?
            .ok_or(GatewayError::ServingStateUnavailable)?;
        let identity = authorize_access(identity, &workspace, &account)
            .map_err(|_| GatewayError::ServingStateUnavailable)?;
        if account.billing_mode == BillingMode::Prepaid && account.balance <= 0 {
            return Err(GatewayError::InsufficientBalance);
        }
        Ok(identity)
    }

    async fn load_model(&self, requested_model: &str) -> Result<GatewayModel, GatewayError> {
        let model = self
            .serving_state
            .model(requested_model)
            .await
            .map_err(|_| GatewayError::ServingStateUnavailable)?
            .ok_or(GatewayError::ModelNotFound)?;
        if model.id != requested_model {
            return Err(GatewayError::ServingStateUnavailable);
        }
        model
            .properties
            .validate_for_serving()
            .map_err(|_| GatewayError::ServingStateUnavailable)?;
        if model.status != ModelStatus::Available {
            return Err(GatewayError::ModelUnavailable);
        }
        Ok(model)
    }
}

fn qualify_model_request(
    metadata: RequestMetadata,
    identity: AuthenticatedIdentity,
    request: ChatCompletionRequest,
    model: GatewayModel,
) -> Result<QualifiedRequest, GatewayError> {
    let deployment = model
        .first_available_deployment()
        .map_err(|_| GatewayError::ServingStateUnavailable)?
        .ok_or(GatewayError::ModelUnavailable)?
        .clone();
    let output = model.properties.text_output();
    if request.stream && !output.streaming {
        return Err(GatewayError::unsupported_parameter("stream"));
    }
    for (name, value) in &request.parameters {
        let descriptor = model
            .properties
            .parameter(name)
            .ok_or_else(|| GatewayError::unsupported_parameter(name))?;
        if !descriptor.accepts(value) {
            return Err(GatewayError::invalid_request(Some(name)));
        }
    }

    let effective_output_tokens = match request.output_token_limit() {
        Some(limit) if limit.value() > output.max_length.value => {
            return Err(GatewayError::context_length_exceeded(
                limit.parameter_name(),
            ))
        }
        Some(limit) => limit.value(),
        None => output.default_length.value,
    };
    let served_release_digest = deployment
        .served_release_digest()
        .map_err(|_| GatewayError::ServingStateUnavailable)?;
    let input = model.properties.text_input();
    let pricing = CapturedPricing {
        input: input.pricing.clone(),
        output: output.pricing.clone(),
    };

    Ok(QualifiedRequest {
        metadata,
        identity,
        deployment,
        served_release_digest,
        max_context_tokens: input.supported_inputs.max_context_length.value,
        max_prompt_tokens: input.supported_inputs.max_prompt_length.value,
        effective_output_tokens,
        pricing,
        request,
    })
}

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use async_trait::async_trait;
    use axum::http::{header::AUTHORIZATION, HeaderValue};
    use chrono::TimeZone;

    use super::*;
    use crate::{
        domain::{
            GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace, OrganizationKind,
            OrganizationStatus,
        },
        serving_state::ServingStateError,
    };

    const API_KEY_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000001);
    const ORGANIZATION_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000002);
    const WORKSPACE_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000003);
    const GENERATION_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000004);

    struct FakeServingState {
        credential: Option<GatewayCredential>,
        workspace: Option<GatewayWorkspace>,
        account: Option<GatewayAccount>,
        model: Option<GatewayModel>,
        calls: Mutex<Vec<&'static str>>,
    }

    impl FakeServingState {
        fn ready() -> Self {
            Self {
                credential: Some(GatewayCredential {
                    api_key_id: API_KEY_ID,
                    organization_id: ORGANIZATION_ID,
                    workspace_id: WORKSPACE_ID,
                    expires_at: None,
                    revoked_at: None,
                }),
                workspace: Some(GatewayWorkspace {
                    organization_id: ORGANIZATION_ID,
                    workspace_id: WORKSPACE_ID,
                    archived_at: None,
                }),
                account: Some(GatewayAccount {
                    organization_id: ORGANIZATION_ID,
                    organization_kind: OrganizationKind::Customer,
                    organization_status: OrganizationStatus::Active,
                    billing_mode: BillingMode::Prepaid,
                    balance: 1,
                }),
                model: Some(model(true)),
                calls: Mutex::new(Vec::new()),
            }
        }

        fn record(&self, call: &'static str) {
            self.calls.lock().unwrap().push(call);
        }
    }

    #[async_trait]
    impl ServingState for FakeServingState {
        async fn credential(
            &self,
            _digest_hex: &str,
        ) -> Result<Option<GatewayCredential>, ServingStateError> {
            self.record("credential");
            Ok(self.credential.clone())
        }

        async fn workspace(
            &self,
            _workspace_id: Uuid,
        ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
            self.record("workspace");
            Ok(self.workspace.clone())
        }

        async fn account(
            &self,
            _organization_id: Uuid,
        ) -> Result<Option<GatewayAccount>, ServingStateError> {
            self.record("account");
            Ok(self.account.clone())
        }

        async fn model(&self, _model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
            self.record("model");
            Ok(self.model.clone())
        }
    }

    fn model(streaming: bool) -> GatewayModel {
        serde_json::from_value(serde_json::json!({
            "id": "model-a",
            "name": "Model A",
            "status": "available",
            "properties": {
                "schema_version": 1,
                "description": "Model A",
                "released_at": null,
                "hugging_face_id": null,
                "quantization": null,
                "tokenizer": null,
                "input_modalities": [{
                    "type": "text",
                    "supported_inputs": {
                        "max_context_length": {"value": 8192, "unit": "token"},
                        "max_prompt_length": {"value": 7168, "unit": "token"}
                    },
                    "pricing": [
                        {"type": "prompt", "unit": "token", "cost": 100},
                        {"type": "cached_prompt", "unit": "token", "cost": 50}
                    ]
                }],
                "output_modalities": [{
                    "type": "text",
                    "max_length": {"value": 4096, "unit": "token"},
                    "default_length": {"value": 1024, "unit": "token"},
                    "streaming": streaming,
                    "supported_parameters": {
                        "temperature": {"type": "range", "min": 0, "max": 2}
                    },
                    "pricing": [
                        {"type": "completion", "unit": "token", "cost": 200}
                    ]
                }],
                "passthrough_parameters": {
                    "response_format": {"type": "enum", "values": ["text", "json"]}
                },
                "deprecation_date": null
            },
            "deployments": [{
                "id": "0198c36f-9b6a-7000-8000-000000000005",
                "status": "available",
                "service_url": "http://127.0.0.1:30000",
                "release": {
                    "schema_version": 1,
                    "runtime_revision": "runtime",
                    "model_path": "model",
                    "model_revision": "model-revision",
                    "tokenizer_path": "tokenizer",
                    "tokenizer_revision": "tokenizer-revision"
                }
            }]
        }))
        .unwrap()
    }

    fn metadata() -> RequestMetadata {
        RequestMetadata {
            generation_id: GENERATION_ID,
            received_at: Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap(),
        }
    }

    fn headers() -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(AUTHORIZATION, HeaderValue::from_static("Bearer grad_test"));
        headers
    }

    #[tokio::test]
    async fn qualifies_the_complete_pre_admission_request() {
        let state = Arc::new(FakeServingState::ready());
        let coordinator = RequestCoordinator::new(state.clone());
        let request = coordinator
            .qualify(
                metadata(),
                &headers(),
                br#"{
                    "model":"model-a",
                    "messages":[{"role":"user","content":"hello"}],
                    "temperature":0.5,
                    "response_format":"json"
                }"#,
            )
            .await
            .unwrap();

        assert_eq!(request.effective_output_tokens, 1_024);
        assert_eq!(request.max_prompt_tokens, 7_168);
        assert_eq!(request.max_context_tokens, 8_192);
        assert_eq!(request.identity.organization_id, ORGANIZATION_ID);
        assert_eq!(request.request.parameters["temperature"], 0.5);
        assert_eq!(request.pricing.input.len(), 2);
        assert_eq!(request.pricing.output.len(), 1);
        assert!(request.served_release_digest.starts_with("sha256:"));
        assert_eq!(
            *state.calls.lock().unwrap(),
            ["credential", "workspace", "account", "model"]
        );
    }

    #[tokio::test]
    async fn stops_at_the_first_failed_access_stage() {
        let mut missing_credential = FakeServingState::ready();
        missing_credential.credential = None;
        let missing_credential = Arc::new(missing_credential);
        let result = RequestCoordinator::new(missing_credential.clone())
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::InvalidApiKey));
        assert_eq!(*missing_credential.calls.lock().unwrap(), ["credential"]);

        let mut empty_balance = FakeServingState::ready();
        empty_balance.account.as_mut().unwrap().balance = 0;
        let empty_balance = Arc::new(empty_balance);
        let result = RequestCoordinator::new(empty_balance.clone())
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::InsufficientBalance));
        assert_eq!(
            *empty_balance.calls.lock().unwrap(),
            ["credential", "workspace", "account"]
        );
    }

    #[tokio::test]
    async fn invoiced_accounts_are_not_gated_by_their_balance() {
        let mut state = FakeServingState::ready();
        let account = state.account.as_mut().unwrap();
        account.billing_mode = BillingMode::Invoiced;
        account.balance = -10_000;

        let request = RequestCoordinator::new(Arc::new(state))
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await
            .unwrap();
        assert_eq!(request.effective_output_tokens, 1_024);
    }

    #[tokio::test]
    async fn fails_closed_for_inconsistent_or_inactive_access_state() {
        let mut archived = FakeServingState::ready();
        archived.workspace.as_mut().unwrap().archived_at = Some(metadata().received_at);
        let archived = Arc::new(archived);
        let result = RequestCoordinator::new(archived.clone())
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::ServingStateUnavailable));
        assert_eq!(
            *archived.calls.lock().unwrap(),
            ["credential", "workspace", "account"]
        );

        let mut suspended = FakeServingState::ready();
        suspended.account.as_mut().unwrap().organization_status = OrganizationStatus::Suspended;
        let result = RequestCoordinator::new(Arc::new(suspended))
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::ServingStateUnavailable));

        let mut mismatched = FakeServingState::ready();
        mismatched.workspace.as_mut().unwrap().organization_id = Uuid::from_u128(99);
        let result = RequestCoordinator::new(Arc::new(mismatched))
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::ServingStateUnavailable));
    }

    #[tokio::test]
    async fn request_and_model_failures_remain_pre_admission() {
        let malformed = Arc::new(FakeServingState::ready());
        let result = RequestCoordinator::new(malformed.clone())
            .qualify(metadata(), &headers(), br#"{"model":"model-a"}"#)
            .await;
        assert_eq!(result, Err(GatewayError::invalid_request(None)));
        assert_eq!(
            *malformed.calls.lock().unwrap(),
            ["credential", "workspace", "account"]
        );

        let mut missing = FakeServingState::ready();
        missing.model = None;
        let result = RequestCoordinator::new(Arc::new(missing))
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::ModelNotFound));

        let mut unavailable = FakeServingState::ready();
        unavailable.model.as_mut().unwrap().status = ModelStatus::Unavailable;
        let result = RequestCoordinator::new(Arc::new(unavailable))
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::ModelUnavailable));

        let mut missing_route = FakeServingState::ready();
        missing_route.model.as_mut().unwrap().deployments.clear();
        let result = RequestCoordinator::new(Arc::new(missing_route))
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}]}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::ServingStateUnavailable));
    }

    #[tokio::test]
    async fn rejects_unadvertised_or_invalid_model_parameters() {
        for (body, expected) in [
            (
                br#"{"model":"model-a","messages":[{}],"seed":7}"#.as_slice(),
                GatewayError::unsupported_parameter("seed"),
            ),
            (
                br#"{"model":"model-a","messages":[{}],"temperature":3}"#.as_slice(),
                GatewayError::invalid_request(Some("temperature")),
            ),
            (
                br#"{"model":"model-a","messages":[{}],"max_tokens":4097}"#.as_slice(),
                GatewayError::context_length_exceeded("max_tokens"),
            ),
        ] {
            let result = RequestCoordinator::new(Arc::new(FakeServingState::ready()))
                .qualify(metadata(), &headers(), body)
                .await;
            assert_eq!(result, Err(expected));
        }

        let mut state = FakeServingState::ready();
        state.model = Some(model(false));
        let result = RequestCoordinator::new(Arc::new(state))
            .qualify(
                metadata(),
                &headers(),
                br#"{"model":"model-a","messages":[{}],"stream":true}"#,
            )
            .await;
        assert_eq!(result, Err(GatewayError::unsupported_parameter("stream")));
    }
}
