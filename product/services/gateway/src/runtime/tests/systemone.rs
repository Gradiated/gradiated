use axum::http::{header, StatusCode};
use serde_json::{json, Map, Value};

use super::support::{client, deadline, decision_request, MockRuntime, SYSTEMONE};
use crate::{
    model::MAX_SAFE_INTEGER,
    runtime::{
        client::ModelNames, systemone::normalize_response, ModelRuntime, RuntimeFailure,
        RuntimeFailureKind,
    },
    systemone::{
        fixtures::{request, request_value},
        SystemOneRequest,
    },
    NormalizedUsage,
};

fn response_from(model: &str) -> Value {
    let mut response = response();
    response["model"] = json!(model);

    response
}

#[tokio::test]
async fn decision_transport_preserves_schema_and_authoritative_usage() {
    let runtime = MockRuntime::builder()
        .json(SYSTEMONE, StatusCode::OK, response())
        .start()
        .await;
    let mut deployment = runtime.system_one_deployment();
    deployment.release.runtime_model_name = Some("runtime-model".to_owned());

    let completion = client()
        .complete(&deployment, decision_request(), 0, deadline(5))
        .await
        .unwrap();

    assert_eq!(
        completion.usage(),
        NormalizedUsage::new(10, 3, 0, 0, 0).unwrap()
    );
    assert_eq!(completion.finish_reason(), "stop");
    assert_eq!(completion.into_response()["model"], "Exact/Model");

    let requests = runtime.requests();
    assert_eq!(requests[0].body["model"], "runtime-model");
    assert_eq!(requests[0].body["state"], request_value()["state"]);
    assert_eq!(requests[0].body["priority"], 0);
    assert!(requests[0].body.get("messages").is_none());
    assert!(requests[0].body.get("max_completion_tokens").is_none());
    assert_eq!(
        requests[0].headers[header::AUTHORIZATION],
        "Bearer runtime-secret"
    );
}

#[tokio::test]
async fn sends_and_expects_the_requested_model_without_a_runtime_name() {
    let runtime = MockRuntime::builder()
        .json(SYSTEMONE, StatusCode::OK, response_from("Exact/Model"))
        .start()
        .await;

    let completion = client()
        .complete(
            &runtime.system_one_deployment(),
            decision_request(),
            0,
            deadline(5),
        )
        .await
        .unwrap();

    assert_eq!(completion.response()["model"], "Exact/Model");
    assert_eq!(runtime.requests()[0].body["model"], "Exact/Model");
}

#[tokio::test]
async fn rejects_a_decision_from_another_model() {
    let runtime = MockRuntime::builder()
        .json(SYSTEMONE, StatusCode::OK, response_from("other-model"))
        .start()
        .await;

    let failure = client()
        .complete(
            &runtime.system_one_deployment(),
            decision_request(),
            0,
            deadline(5),
        )
        .await
        .unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::ProtocolViolation);
}

#[tokio::test]
async fn maps_decision_backpressure_to_capacity() {
    for status in [
        StatusCode::TOO_MANY_REQUESTS,
        StatusCode::SERVICE_UNAVAILABLE,
    ] {
        let runtime = MockRuntime::builder()
            .json(SYSTEMONE, status, json!({"error": "busy"}))
            .start()
            .await;

        let failure = client()
            .complete(
                &runtime.system_one_deployment(),
                decision_request(),
                0,
                deadline(5),
            )
            .await
            .unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::CapacityExceeded,
            "{status}"
        );
        assert_eq!(failure.upstream_status(), Some(status.as_u16()));
        assert_eq!(failure.usage(), NormalizedUsage::zero());
    }
}

fn response() -> Value {
    json!({"model":"runtime-model", "answers":{
        "pick":{"type":"choice","choice":"b","confidence":0.5,"probabilities":{"a":0.25,"b":0.75}},
        "yes":{"type":"noul","noul":0.7},
        "level":{"type":"score","score":0.75,"legend":{"0":"low","1":"label: high"},"confidence":0.75,"probabilities":{"0":0.25,"1":0.75}}
    },"usage":{"input_tokens":10,"cached_input_tokens":3,"output_tokens":0}, "latency_ms":2})
}

fn models() -> ModelNames {
    ModelNames {
        requested: "Exact/Model".to_owned(),
        runtime: "runtime-model".to_owned(),
    }
}

fn normalize(value: &Value) -> Result<(Value, NormalizedUsage), RuntimeFailure> {
    normalize_response(&serde_json::to_vec(value).unwrap(), &request(), &models())
}

#[test]
fn rebuilds_the_public_response_with_the_requested_model() {
    let (result, usage) = normalize(&response()).unwrap();

    let mut expected = response();
    expected["model"] = json!("Exact/Model");
    assert_eq!(result.to_string(), expected.to_string());
    assert_eq!(usage, NormalizedUsage::new(10, 3, 0, 0, 0).unwrap());

    let mut without_latency = response();
    without_latency
        .as_object_mut()
        .unwrap()
        .remove("latency_ms");
    let (result, _) = normalize(&without_latency).unwrap();
    assert!(result.get("latency_ms").is_none());
}

#[test]
fn rejects_fields_and_latency_outside_the_public_contract() {
    for (key, value) in [
        ("debug", json!({"internal_id": 1})),
        ("latency_ms", json!(-1)),
        ("latency_ms", json!("x")),
        ("latency_ms", Value::Null),
    ] {
        let mut body = response();
        body[key] = value;

        let failure = normalize(&body).unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{key}"
        );
    }
}

#[test]
fn rejects_malformed_json_and_duplicate_keys() {
    let duplicate = serde_json::to_string(&response()).unwrap().replace(
        "\"input_tokens\":10",
        "\"input_tokens\":10,\"input_tokens\":10",
    );

    for body in ["", "{", "null", "[]", "{} {}", "{\"a\":1e999}", &duplicate] {
        let failure = normalize_response(body.as_bytes(), &request(), &models()).unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{body}"
        );
    }
}

#[test]
fn rejects_bad_usage_and_requires_zero_generated_tokens() {
    for usage in [
        Value::Null,
        json!({}),
        json!({"input_tokens":10,"output_tokens":0}),
        json!({"input_tokens":10,"cached_input_tokens":0,"output_tokens":0,"extra":0}),
    ] {
        let mut body = response();
        body["usage"] = usage;
        assert!(normalize(&body).is_err());
    }
    for key in ["input_tokens", "cached_input_tokens", "output_tokens"] {
        for value in [
            json!(-1),
            json!(1.5),
            json!("0"),
            json!(true),
            Value::Null,
            json!(MAX_SAFE_INTEGER + 1),
        ] {
            let mut body = response();
            body["usage"][key] = value;
            assert!(normalize(&body).is_err(), "{key}");
        }
    }
    for (key, value) in [("output_tokens", 1), ("cached_input_tokens", 11)] {
        let mut body = response();
        body["usage"][key] = json!(value);
        assert!(normalize(&body).is_err());
    }
    let mut body = response();
    body["usage"] = json!({"input_tokens":MAX_SAFE_INTEGER,"cached_input_tokens":MAX_SAFE_INTEGER,"output_tokens":0});
    assert!(normalize(&body).is_ok());
}

#[test]
fn rejects_mismatched_models_questions_answer_types_and_distributions() {
    for (pointer, value) in [
        ("/model", json!("different")),
        ("/answers/yes/type", json!("choice")),
        ("/answers/yes/noul", json!(1.01)),
        ("/answers/pick/choice", json!("unoffered")),
        ("/answers/pick/confidence", json!(-0.01)),
        ("/answers/pick/probabilities", json!({"a":0.5,"other":0.5})),
        ("/answers/pick/probabilities", json!({"a":0.1,"b":0.1})),
        ("/answers/pick/probabilities", json!({"a":-0.2,"b":1.2})),
        ("/answers/pick/probabilities/a", json!("0.25")),
        ("/answers/level/score", json!(1.01)),
        ("/answers/level/score", json!(-0.01)),
        ("/answers/level/legend", json!({"0":"low","2":"high"})),
        ("/answers/level/legend/0", json!(0)),
    ] {
        let mut body = response();
        *body.pointer_mut(pointer).unwrap() = value;
        assert_eq!(
            normalize(&body).unwrap_err().kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{pointer}"
        );
    }
    let mut body = response();
    let answers = body["answers"].as_object_mut().unwrap();
    let swapped = answers.remove("yes").unwrap();
    answers.insert("other-question".into(), swapped);
    assert!(normalize(&body).is_err());
    let mut body = response();
    body["answers"]["pick"]["extra"] = json!(0);
    assert!(normalize(&body).is_err());
}

#[test]
fn accepts_independently_rounded_large_distributions() {
    let mut request = request_value();
    request["questions"] = json!({"q":{"type":"choice","instructions":"","criteria":(0..30).map(|i| (i.to_string(), Value::Null)).collect::<Map<_,_>>()}});
    let request = SystemOneRequest::parse(&serde_json::to_vec(&request).unwrap()).unwrap();
    let mut body = response();
    body["answers"] = json!({"q":{"type":"choice","choice":"0","confidence":0,"probabilities":(0..30).map(|i| (i.to_string(), json!(0.03))).collect::<Map<_,_>>()}});
    assert!(normalize_response(&serde_json::to_vec(&body).unwrap(), &request, &models()).is_ok());
}

#[tokio::test]
async fn list_choice_criteria_reach_the_runtime_as_options_and_key_its_answers() {
    let mut body = request_value();
    body["questions"]["pick"]["criteria"] = json!(["a", "b"]);
    let request = crate::InferenceRequest::parse_kind(
        &serde_json::to_vec(&body).unwrap(),
        crate::RequestKind::SystemOne,
    )
    .unwrap();
    let runtime = MockRuntime::builder()
        .json(SYSTEMONE, StatusCode::OK, response())
        .start()
        .await;
    let mut deployment = runtime.system_one_deployment();
    deployment.release.runtime_model_name = Some("runtime-model".to_owned());

    let completion = client()
        .complete(&deployment, request, 0, deadline(5))
        .await
        .unwrap();

    assert_eq!(
        completion.into_response()["answers"]["pick"]["probabilities"],
        json!({"a":0.25,"b":0.75})
    );
    let forwarded = &runtime.requests()[0].body["questions"];
    assert_eq!(forwarded["pick"]["criteria"], json!({"a":null,"b":null}));
    assert_eq!(forwarded["yes"], request_value()["questions"]["yes"]);
    assert_eq!(forwarded["level"], request_value()["questions"]["level"]);
}

#[test]
fn answers_to_list_choice_criteria_must_use_its_labels() {
    let mut body = request_value();
    body["questions"]["pick"]["criteria"] = json!(["a", "b"]);
    let request = SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).unwrap();
    let check = |response: &Value| {
        normalize_response(&serde_json::to_vec(response).unwrap(), &request, &models())
    };

    assert!(check(&response()).is_ok());
    for (pointer, value) in [
        ("/answers/pick/choice", json!("c")),
        ("/answers/pick/probabilities", json!({"0":0.25,"1":0.75})),
        ("/answers/pick/probabilities", json!({"a":0.25,"c":0.75})),
        ("/answers/pick/probabilities", json!({"a":1})),
    ] {
        let mut response = response();
        *response.pointer_mut(pointer).unwrap() = value;
        assert!(check(&response).is_err(), "{pointer}");
    }
}

#[test]
fn validates_answers_to_every_question_of_a_large_request() {
    let count = crate::systemone::MAX_QUESTIONS;
    let mut body = request_value();
    body["questions"] = (0..count)
        .map(|i| (format!("q{i}"), json!({"type":"noul"})))
        .collect::<Map<_, _>>()
        .into();
    let request = SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).unwrap();
    let mut response = response();
    response["answers"] = (0..count)
        .map(|i| (format!("q{i}"), json!({"type":"noul","noul":0.5})))
        .collect::<Map<_, _>>()
        .into();
    let check = |response: &Value| {
        normalize_response(&serde_json::to_vec(response).unwrap(), &request, &models())
    };

    assert!(check(&response).is_ok());
    response["answers"]
        .as_object_mut()
        .unwrap()
        .remove(&format!("q{}", count - 1));
    assert!(check(&response).is_err());
}
