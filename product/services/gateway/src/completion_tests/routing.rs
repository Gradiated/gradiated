use std::time::Duration;

use super::{super::*, support::*};
use crate::{serving_state::ServingStateError, AdmissionError, RuntimeFailure, RuntimeFailureKind};

async fn routes(harness: &Harness, count: usize) -> Vec<RouteStep> {
    // Releases run on their own task once the generation ends.
    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            let routes = harness.state.routes.lock().unwrap().clone();
            if routes.len() >= count {
                return routes;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("every route step is recorded")
}

#[tokio::test]
async fn the_placed_replica_serves_and_its_lease_is_released() {
    let harness = Harness::new(qualified_request(3), [completion()]);
    let ids = harness.deployment_ids();
    *harness.state.placed.lock().unwrap() = Some(ids[2]);

    harness.complete().await.unwrap();

    assert_eq!(harness.journal.dispatches(), vec![ids[2]]);
    let steps = routes(&harness, 2).await;
    let RouteStep::Place(candidates) = &steps[0] else {
        panic!("placement comes first: {steps:?}");
    };
    assert_eq!(
        candidates.iter().collect::<std::collections::HashSet<_>>(),
        ids.iter().collect()
    );
    assert_eq!(steps[1], RouteStep::Release(ids[2]));
    assert_eq!(
        harness.metric("session_routes_total", "outcome=\"placed\""),
        1
    );
}

#[tokio::test]
async fn a_fallback_takes_the_session_and_the_lease_with_it() {
    let harness = Harness::new(
        qualified_request(2),
        [failure(RuntimeFailureKind::Unavailable), completion()],
    );

    harness.complete().await.unwrap();

    let dispatches = harness.journal.dispatches();
    let steps = routes(&harness, 4).await;
    assert_eq!(
        steps[1..],
        [
            RouteStep::Claim(dispatches[1]),
            RouteStep::Release(dispatches[0]),
            RouteStep::Release(dispatches[1]),
        ]
    );
}

#[tokio::test]
async fn a_placement_failure_rejects_before_admission() {
    let harness = Harness::new(qualified_request(2), [completion()]);
    *harness.state.placement_error.lock().unwrap() = Some(ServingStateError::Redis(
        redis::RedisError::from((redis::ErrorKind::Io, "connection refused")),
    ));

    let result = harness.complete().await;

    assert!(matches!(result, Err(GatewayError::ServingStateUnavailable)));
    assert!(harness.journal.steps().is_empty());
}

#[tokio::test]
async fn a_rejected_admission_releases_the_placed_lease() {
    let harness = Harness::new(qualified_request(1), [completion()]);
    *harness.state.admission_error.lock().unwrap() = Some(AdmissionError::ConcurrencyExceeded);

    assert!(harness.complete().await.is_err());

    let steps = routes(&harness, 2).await;
    assert_eq!(steps[1], RouteStep::Release(harness.deployment_ids()[0]));
    assert!(harness.journal.dispatches().is_empty());
}

#[tokio::test]
async fn a_stream_retried_after_it_opened_takes_the_session_and_the_lease_with_it() {
    let harness = Harness::new(
        streaming_request(2),
        [
            Script::Stream(vec![Err(RuntimeFailure::new(
                RuntimeFailureKind::CapacityExceeded,
            ))]),
            successful_stream(),
        ],
    );

    harness.stream().await.unwrap();

    let dispatches = harness.journal.dispatches();
    let steps = routes(&harness, 4).await;
    assert_eq!(
        steps[1..],
        [
            RouteStep::Claim(dispatches[1]),
            RouteStep::Release(dispatches[0]),
            RouteStep::Release(dispatches[1]),
        ]
    );
}
