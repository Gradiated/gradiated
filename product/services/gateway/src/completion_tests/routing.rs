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

fn eval_request() -> QualifiedRequest {
    let mut request = qualified_request(1);
    request.identity.lane = crate::auth::Lane::Eval;
    request.identity.eval_id = Some("ev_abc".to_owned());
    request
}

#[tokio::test]
async fn an_eval_generation_holds_an_eval_slot_and_is_billed_as_eval() {
    let request = eval_request();
    let generation_id = request.metadata.generation_id;
    let harness = Harness::new(request, [completion()]);

    harness.complete().await.unwrap();

    let steps = routes(&harness, 4).await;
    assert_eq!(steps[1], RouteStep::AdmitEval(generation_id));
    assert!(
        steps.contains(&RouteStep::ReleaseEval(generation_id)),
        "{steps:?}"
    );
    // Pool autoscaling reads these by model, so eval traffic never scales a pool.
    assert_eq!(
        harness.metric("admissions_total", "model=\"eval:model-a\""),
        1
    );
    assert_eq!(harness.metric("admissions_total", "model=\"model-a\""), 0);
    let finalized = harness.only_finalized();
    assert_eq!(
        (&finalized["lane"], &finalized["eval_id"]),
        (&"eval".into(), &"ev_abc".into())
    );
}

#[tokio::test]
async fn standard_generations_skip_the_eval_lane_and_carry_no_lane() {
    let harness = Harness::new(qualified_request(1), [completion()]);

    harness.complete().await.unwrap();

    let steps = routes(&harness, 2).await;
    assert!(!steps
        .iter()
        .any(|step| matches!(step, RouteStep::AdmitEval(_))));
    assert!(harness.only_finalized().get("lane").is_none());
}

#[tokio::test]
async fn a_full_eval_lane_answers_429_before_admission() {
    for capped in [
        crate::serving_state::EvalAdmission::ConcurrencyCapped,
        crate::serving_state::EvalAdmission::RateCapped,
    ] {
        let harness = Harness::new(eval_request(), [completion()]);
        *harness.state.eval_admission.lock().unwrap() = capped;

        let result = harness.complete().await;

        assert!(
            matches!(result, Err(GatewayError::EvalLaneLimited)),
            "{capped:?}"
        );
        assert!(harness.journal.dispatches().is_empty());
        assert!(harness.finalized().is_empty());
    }
}
