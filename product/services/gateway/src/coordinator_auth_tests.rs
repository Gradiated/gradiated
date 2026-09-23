use super::support::{
    classify_messages, headers, qualify, qualify_chat, FailingState, StateChange, StateRead,
    CHAT_BODY, FRONTIER_BODY, PROVIDER_KEYS, WORKSPACE_KEY,
};
use super::*;
use crate::domain::{BillingMode, OrganizationStatus};
use crate::test_support::{metadata, TestServingState};

#[tokio::test]
async fn a_relay_looks_up_only_the_workspace_key_digest() {
    let state = Arc::new(TestServingState::without_models());
    let provider_headers = headers(&PROVIDER_KEYS);
    let classified = classify_messages(state.clone(), &provider_headers, FRONTIER_BODY).await;

    assert!(matches!(classified, Ok(RequestRoute::Relay { .. })));
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account", "model"]
    );
    assert_eq!(
        *state.requested_digests.lock().unwrap(),
        [crate::auth::credential_digest(&headers(&WORKSPACE_KEY)).unwrap()]
    );
}

#[tokio::test]
async fn provider_credentials_do_not_bypass_hosted_balance_checks() {
    for balance in [0, -100] {
        let unfunded = |mut state: TestServingState| {
            state.account.as_mut().unwrap().balance = balance;
            Arc::new(state)
        };
        let headers = headers(&PROVIDER_KEYS);

        let relayed = classify_messages(
            unfunded(TestServingState::without_models()),
            &headers,
            FRONTIER_BODY,
        )
        .await;
        assert!(
            matches!(relayed, Ok(RequestRoute::Relay { .. })),
            "a relay is paid by the provider key at balance {balance}"
        );

        let hosted = qualify(
            unfunded(TestServingState::ready()),
            &headers,
            CHAT_BODY,
            RequestKind::Chat,
        )
        .await;
        assert_eq!(hosted.err(), Some(GatewayError::InsufficientBalance));
    }
}

#[tokio::test]
async fn the_model_resolves_before_the_hosted_balance_gate() {
    let mut state = TestServingState::ready();
    state.account.as_mut().unwrap().balance = 0;
    let state = Arc::new(state);
    let result = qualify_chat(state.clone(), CHAT_BODY).await;

    assert_eq!(result.err(), Some(GatewayError::InsufficientBalance));
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account", "model"],
        "the model decides whether a request is hosted, so it resolves before \
         the hosted balance gate"
    );
}

#[tokio::test]
async fn invoiced_accounts_are_not_gated_by_their_balance() {
    let mut state = TestServingState::ready();
    let account = state.account.as_mut().unwrap();
    account.billing_mode = BillingMode::Invoiced;
    account.balance = -10_000;

    let request = qualify_chat(Arc::new(state), CHAT_BODY).await.unwrap();

    assert_eq!(request.effective_output_tokens, 1_024);
}

#[tokio::test]
async fn hosted_requests_accept_combined_identity_and_discard_provider_secrets() {
    let state = Arc::new(TestServingState::ready());
    let request = qualify(
        state.clone(),
        &headers(&PROVIDER_KEYS),
        CHAT_BODY,
        RequestKind::Chat,
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
async fn rejects_invalid_workspace_credentials_before_access_lookups() {
    let failures: [(&str, StateChange); 3] = [
        ("missing", |state| state.credential = None),
        ("revoked", |state| {
            state.credential.as_mut().unwrap().revoked_at = Some(metadata().received_at)
        }),
        ("expired", |state| {
            state.credential.as_mut().unwrap().expires_at = Some(metadata().received_at)
        }),
    ];

    for (name, change) in failures {
        let mut state = TestServingState::ready();
        change(&mut state);
        let state = Arc::new(state);
        let result = qualify_chat(state.clone(), CHAT_BODY).await;

        assert_eq!(result.err(), Some(GatewayError::InvalidApiKey), "{name}");
        assert_eq!(*state.calls.lock().unwrap(), ["credential"], "{name}");
    }
}

#[tokio::test]
async fn rejects_missing_inactive_and_cross_tenant_state_before_the_model() {
    // Missing or inconsistent records stay retryable; a workspace or organization
    // that is deliberately closed does not.
    let failures: [(&str, StateChange, GatewayError); 7] = [
        (
            "workspace missing",
            |state| state.workspace = None,
            GatewayError::ServingStateUnavailable,
        ),
        (
            "account missing",
            |state| state.account = None,
            GatewayError::ServingStateUnavailable,
        ),
        (
            "workspace archived",
            |state| state.workspace.as_mut().unwrap().archived_at = Some(metadata().received_at),
            GatewayError::WorkspaceArchived,
        ),
        (
            "organization suspended",
            |state| {
                state.account.as_mut().unwrap().organization_status = OrganizationStatus::Suspended
            },
            GatewayError::OrganizationSuspended,
        ),
        (
            "workspace id mismatch",
            |state| state.workspace.as_mut().unwrap().workspace_id = Uuid::nil(),
            GatewayError::ServingStateUnavailable,
        ),
        (
            "workspace organization mismatch",
            |state| state.workspace.as_mut().unwrap().organization_id = Uuid::nil(),
            GatewayError::ServingStateUnavailable,
        ),
        (
            "account organization mismatch",
            |state| state.account.as_mut().unwrap().organization_id = Uuid::nil(),
            GatewayError::ServingStateUnavailable,
        ),
    ];

    for (name, change, expected) in failures {
        let mut state = TestServingState::ready();
        change(&mut state);
        let state = Arc::new(state);
        let result = qualify_chat(state.clone(), CHAT_BODY).await;

        assert_eq!(result.err(), Some(expected), "{name}");
        assert_eq!(state.lookups("model"), 0, "{name}");
    }
}

#[tokio::test]
async fn rejects_malformed_identity_without_a_state_lookup() {
    let state = Arc::new(TestServingState::ready());
    let mut headers = headers(&PROVIDER_KEYS);
    headers.append("x-gradiated-api-key", "grad_other".parse().unwrap());
    let result = qualify(state.clone(), &headers, CHAT_BODY, RequestKind::Chat).await;

    assert_eq!(result.err(), Some(GatewayError::InvalidApiKey));
    assert!(state.calls.lock().unwrap().is_empty());
}

#[tokio::test]
async fn a_failed_classification_read_stops_the_pipeline() {
    let phases: [(StateRead, &[&str]); 4] = [
        (StateRead::Credential, &[]),
        (StateRead::Workspace, &["credential"]),
        (StateRead::Account, &["credential", "workspace"]),
        (StateRead::Model, &["credential", "workspace", "account"]),
    ];

    for (phase, earlier) in phases {
        let state = Arc::new(FailingState::new(TestServingState::ready(), phase));
        let result = qualify_chat(state.clone(), CHAT_BODY).await;

        assert_eq!(
            result.err(),
            Some(GatewayError::ServingStateUnavailable),
            "{phase:?}"
        );
        assert_eq!(*state.inner.calls.lock().unwrap(), earlier, "{phase:?}");
    }
}
