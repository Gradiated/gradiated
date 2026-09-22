use super::tests::{metadata, qualify, TestServingState};
use super::*;
use crate::domain::OrganizationStatus;

fn provider_headers() -> HeaderMap {
    let mut headers = HeaderMap::new();
    headers.insert("x-gradiated-api-key", "grad_test".parse().unwrap());
    headers.insert("x-api-key", "sk-ant-example".parse().unwrap());

    headers
}

#[tokio::test]
async fn retains_provider_credential_and_looks_up_only_the_workspace_digest() {
    let state = Arc::new(TestServingState::ready());
    let coordinator = RequestCoordinator::new(state.clone());
    let headers = provider_headers();
    let context = coordinator
        .authorize_request(&headers, metadata().received_at)
        .await
        .unwrap();
    let (identity, provider) = context.into_provider_request(Provider::Anthropic).unwrap();

    assert_eq!(
        identity.workspace_id,
        state.workspace.as_ref().unwrap().workspace_id
    );
    assert_eq!(provider.provider, Provider::Anthropic);
    assert_eq!(provider.secret, "sk-ant-example");
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account"]
    );

    let mut hosted_headers = HeaderMap::new();
    hosted_headers.insert("authorization", "Bearer grad_test".parse().unwrap());
    assert_eq!(
        *state.requested_digests.lock().unwrap(),
        [crate::auth::credential_digest(&hosted_headers).unwrap()]
    );
}

#[tokio::test]
async fn provider_credentials_do_not_bypass_hosted_balance_checks() {
    for balance in [0, -100] {
        let mut state = TestServingState::ready();
        state.account.as_mut().unwrap().balance = balance;
        let coordinator = RequestCoordinator::new(Arc::new(state));
        let headers = provider_headers();

        let context = coordinator
            .authorize_request(&headers, metadata().received_at)
            .await
            .unwrap();
        assert!(context.into_provider_request(Provider::Anthropic).is_ok());

        let result = qualify(
            &coordinator,
            &headers,
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::InsufficientBalance));
    }
}

#[tokio::test]
async fn hosted_requests_accept_combined_identity_and_discard_provider_secrets() {
    let state = Arc::new(TestServingState::ready());
    let coordinator = RequestCoordinator::new(state.clone());
    let request = qualify(
        &coordinator,
        &provider_headers(),
        br#"{"model":"model-a","messages":[{}]}"#,
    )
    .await
    .unwrap();

    assert_eq!(request.request.model, "model-a");
    assert!(!format!("{request:?}").contains("sk-ant-example"));
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account", "model"]
    );
}

#[tokio::test]
async fn provider_path_requires_a_matching_provider_credential() {
    let coordinator = RequestCoordinator::new(Arc::new(TestServingState::ready()));
    let headers = provider_headers();
    let context = coordinator
        .authorize_request(&headers, metadata().received_at)
        .await
        .unwrap();
    assert!(matches!(
        context.into_provider_request(Provider::OpenAi),
        Err(GatewayError::InvalidApiKey)
    ));

    let mut headers = HeaderMap::new();
    headers.insert("x-gradiated-api-key", "grad_test".parse().unwrap());
    let context = coordinator
        .authorize_request(&headers, metadata().received_at)
        .await
        .unwrap();
    assert!(matches!(
        context.into_provider_request(Provider::Anthropic),
        Err(GatewayError::ProviderKeyRequired)
    ));
}

#[tokio::test]
async fn rejects_invalid_workspace_credentials_before_access_lookups() {
    for failure in ["missing", "revoked", "expired"] {
        let mut state = TestServingState::ready();
        match failure {
            "missing" => state.credential = None,
            "revoked" => {
                state.credential.as_mut().unwrap().revoked_at = Some(metadata().received_at)
            }
            _ => state.credential.as_mut().unwrap().expires_at = Some(metadata().received_at),
        }
        let state = Arc::new(state);
        let coordinator = RequestCoordinator::new(state.clone());
        let headers = provider_headers();
        let result = coordinator
            .authorize_request(&headers, metadata().received_at)
            .await;

        assert!(matches!(result, Err(GatewayError::InvalidApiKey)));
        assert_eq!(*state.calls.lock().unwrap(), ["credential"]);
    }
}

#[tokio::test]
async fn rejects_missing_inactive_and_cross_tenant_state() {
    for failure in [
        "workspace_missing",
        "account_missing",
        "archived",
        "suspended",
        "workspace_mismatch",
        "account_mismatch",
    ] {
        let mut state = TestServingState::ready();
        match failure {
            "workspace_missing" => state.workspace = None,
            "account_missing" => state.account = None,
            "archived" => {
                state.workspace.as_mut().unwrap().archived_at = Some(metadata().received_at)
            }
            "suspended" => {
                state.account.as_mut().unwrap().organization_status = OrganizationStatus::Suspended
            }
            "workspace_mismatch" => state.workspace.as_mut().unwrap().workspace_id = Uuid::nil(),
            _ => state.account.as_mut().unwrap().organization_id = Uuid::nil(),
        }
        let coordinator = RequestCoordinator::new(Arc::new(state));
        let headers = provider_headers();
        let result = coordinator
            .authorize_request(&headers, metadata().received_at)
            .await;

        // Missing or inconsistent projections stay retryable; a workspace or
        // organization that is deliberately closed does not.
        let expected = match failure {
            "archived" => GatewayError::WorkspaceArchived,
            "suspended" => GatewayError::OrganizationSuspended,
            _ => GatewayError::ServingStateUnavailable,
        };
        assert_eq!(result.err(), Some(expected), "{failure}");
    }
}

#[tokio::test]
async fn rejects_malformed_identity_without_a_valkey_lookup() {
    let state = Arc::new(TestServingState::ready());
    let coordinator = RequestCoordinator::new(state.clone());
    let mut headers = provider_headers();
    headers.append("x-gradiated-api-key", "grad_other".parse().unwrap());
    let result = coordinator
        .authorize_request(&headers, metadata().received_at)
        .await;

    assert!(matches!(result, Err(GatewayError::InvalidApiKey)));
    assert!(state.calls.lock().unwrap().is_empty());
}
