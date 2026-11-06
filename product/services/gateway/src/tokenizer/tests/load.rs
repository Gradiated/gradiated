use std::{sync::Arc, time::Duration};

use axum::http::StatusCode;
use tokio::time::Instant;

use crate::{
    tokenizer::{
        registry::{TokenizerRelease, LOAD_RETRY_BACKOFF},
        test_support::{chat_tokenizer, qualified, Hub},
        ModelTokenizer, ModelTokenizerError,
    },
    GatewayError,
};

#[tokio::test]
async fn concurrent_requests_share_one_compiled_tokenizer() {
    let qualified = qualified(None);
    let release = &qualified.local_capacity().deployment.release;
    let registry = ModelTokenizer::seeded(release, chat_tokenizer());

    let (first, second) = tokio::join!(registry.tokenizer(release), registry.tokenizer(release));
    let counts = tokio::join!(registry.count(&qualified), registry.count(&qualified));

    assert!(Arc::ptr_eq(&first.unwrap(), &second.unwrap()));
    assert_eq!(counts, (Ok(3), Ok(3)));
}

#[tokio::test]
async fn a_cached_release_loads_without_the_hub_api_and_a_missing_template_is_optional() {
    let hub = Hub::answering(StatusCode::NOT_FOUND).await;
    let qualified = qualified(None);
    hub.cache_release(&qualified.local_capacity().deployment.release);

    let count = hub.tokenizer.count(&qualified).await;

    assert_eq!(count, Ok(3));
    assert_eq!(
        hub.requests(),
        1,
        "only the absent template reaches the hub"
    );
}

#[tokio::test]
async fn a_failed_load_is_logged_once_and_retried_only_after_a_backoff() {
    let hub = Hub::answering(StatusCode::INTERNAL_SERVER_ERROR).await;
    let qualified = qualified(None);
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();

    let failed = hub.tokenizer.count(&qualified).await;
    let attempts = hub.requests();
    let backing_off = hub
        .tokenizer
        .decoder(&qualified.local_capacity().deployment.release)
        .await;

    assert_eq!(failed, Err(GatewayError::ServingStateUnavailable));
    assert!(attempts > 0);
    assert!(matches!(backing_off, Err(ModelTokenizerError::Backoff)));
    assert_eq!(hub.requests(), attempts);
    let events = logs.events();
    assert_eq!(events.len(), 1);
    assert_eq!(events[0]["fields"]["error_code"], "hub");

    let key = TokenizerRelease::from(&qualified.local_capacity().deployment.release);
    let slot = hub.tokenizer.loaded.lock().unwrap()[&key].clone();
    *slot.failed_at.lock().unwrap() = Instant::now().checked_sub(LOAD_RETRY_BACKOFF);

    assert!(hub.tokenizer.count(&qualified).await.is_err());
    assert!(hub.requests() > attempts);
}

#[tokio::test]
async fn a_hub_that_never_answers_times_out() {
    let mut hub = Hub::silent().await;
    hub.tokenizer.load_timeout = Duration::from_millis(50);
    let qualified = qualified(None);
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();

    let count = hub.tokenizer.count(&qualified).await;

    assert_eq!(count, Err(GatewayError::ServingStateUnavailable));
    assert_eq!(logs.events()[0]["fields"]["error_code"], "timeout");
}

#[tokio::test]
async fn a_model_without_a_deployment_counts_with_its_pinned_tokenizer() {
    let mut qualified = qualified(None);
    let release = qualified.local_capacity().deployment.release.clone();
    assert_eq!(release.tokenizer_mode, None);
    let registry = ModelTokenizer::seeded(&release, chat_tokenizer());
    qualified.local = None;
    qualified.tokenizer = Some(crate::PinnedTokenizer {
        path: release.tokenizer_path,
        revision: release.tokenizer_revision,
    });

    assert_eq!(registry.count(&qualified).await, Ok(3));
}

#[test]
fn only_a_bounded_path_at_a_full_commit_is_a_valid_pin() {
    let pin = |path: &str, revision: &str| crate::PinnedTokenizer {
        path: path.to_owned(),
        revision: revision.to_owned(),
    };
    let commit = "ba32f8c19c8738e2c57c71798c601d477a7bf844";

    assert!(pin("zai-org/GLM-5.3", commit).valid());
    assert!(!pin("zai-org/GLM-5.3", "main").valid());
    assert!(!pin("", commit).valid());
    assert!(!pin(&"a".repeat(301), commit).valid());
}

#[tokio::test]
async fn a_model_without_a_deployment_has_no_tokenizer_to_count_with() {
    let mut qualified = qualified(None);
    qualified.local = None;

    let count = ModelTokenizer::new().unwrap().count(&qualified).await;

    assert_eq!(count, Err(GatewayError::ModelUnavailable));
}
