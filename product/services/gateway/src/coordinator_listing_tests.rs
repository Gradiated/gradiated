use super::support::{list_models, FailingState, StateChange, StateRead};
use super::*;
use crate::test_support::TestServingState;
use crate::DeploymentStatus;

#[tokio::test]
async fn model_listing_reuses_the_complete_access_pipeline_without_admission() {
    let state = Arc::new(TestServingState::ready());
    let models = list_models(state.clone()).await.unwrap();

    assert_eq!(models.len(), 1);
    assert_eq!(models[0].model.id, "model-a");
    assert_eq!(models[0].healthy_deployments, 1);
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account", "models"]
    );
}

#[tokio::test]
async fn model_listing_requires_a_positive_prepaid_balance() {
    let mut state = TestServingState::ready();
    state.account.as_mut().unwrap().balance = 0;
    let state = Arc::new(state);
    let result = list_models(state.clone()).await;

    assert_eq!(result.err(), Some(GatewayError::InsufficientBalance));
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account"]
    );
}

#[tokio::test]
async fn a_model_without_a_usable_serving_deployment_lists_as_unhealthy() {
    let unusable: [(&str, StateChange); 2] = [
        ("unavailable", |state| {
            state.model.as_mut().unwrap().deployments[0].status = DeploymentStatus::Unavailable
        }),
        ("invalid", |state| {
            state.model.as_mut().unwrap().deployments[0].service_url =
                "ftp://runtime.internal".to_owned()
        }),
    ];

    for (name, change) in unusable {
        let mut inner = TestServingState::ready();
        change(&mut inner);
        let state = Arc::new(FailingState::new(inner, StateRead::DeploymentStatuses));
        let models = list_models(state.clone()).await.unwrap();

        assert_eq!(models.len(), 1, "{name}");
        assert_eq!(models[0].healthy_deployments, 0, "{name}");
        assert_eq!(state.inner.lookups("deployment_statuses"), 0, "{name}");
    }
}

#[tokio::test]
async fn a_failed_catalog_read_stops_the_listing() {
    let phases: [(StateRead, &[&str]); 2] = [
        (StateRead::Models, &["credential", "workspace", "account"]),
        (
            StateRead::DeploymentStatuses,
            &[
                "credential",
                "workspace",
                "account",
                "models",
                "deployment_statuses",
            ],
        ),
    ];

    for (phase, calls) in phases {
        let state = Arc::new(FailingState::new(TestServingState::ready(), phase));
        let result = list_models(state.clone()).await;

        assert_eq!(
            result.err(),
            Some(GatewayError::ServingStateUnavailable),
            "{phase:?}"
        );
        assert_eq!(*state.inner.calls.lock().unwrap(), calls, "{phase:?}");
    }
}
