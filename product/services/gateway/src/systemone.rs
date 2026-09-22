//! Native SystemOne wire validation. Call `parse` before admission and
//! `normalize_response` before exposing answers or settling usage.

use crate::json::strict_json;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value};

use crate::{GatewayError, NormalizedUsage, RuntimeFailure, RuntimeFailureKind, ServiceTier};

const MAX_OPTIONS: usize = 255;
const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SystemOneRequest {
    pub model: String,
    pub state: Value,
    pub questions: Map<String, Value>,
    #[serde(
        default,
        deserialize_with = "deserialize_session_id",
        skip_serializing_if = "Option::is_none"
    )]
    pub session_id: Option<String>,
    #[serde(default)]
    pub service_tier: ServiceTier,
}

impl SystemOneRequest {
    pub fn parse(body: &[u8]) -> Result<Self, GatewayError> {
        let value = strict_json(body).map_err(|_| GatewayError::invalid_request(None))?;
        let request: Self =
            serde_json::from_value(value).map_err(|_| GatewayError::invalid_request(None))?;
        request.validate()?;
        Ok(request)
    }

    fn validate(&self) -> Result<(), GatewayError> {
        if !bounded_name(&self.model) {
            return Err(GatewayError::invalid_request(Some("model")));
        }
        if !matches!(
            self.state,
            Value::String(_) | Value::Object(_) | Value::Array(_)
        ) {
            return Err(GatewayError::invalid_request(Some("state")));
        }
        if self.service_tier != ServiceTier::Default {
            return Err(GatewayError::unsupported_parameter("service_tier"));
        }
        if self
            .session_id
            .as_ref()
            .is_some_and(|session| !(1..=256).contains(&session.encode_utf16().count()))
        {
            return Err(GatewayError::invalid_request(Some("session_id")));
        }
        if !(1..=64).contains(&self.questions.len())
            || self
                .questions
                .iter()
                .any(|(key, question)| !bounded_name(key) || !valid_question(question))
        {
            return Err(GatewayError::invalid_request(Some("questions")));
        }
        Ok(())
    }
}

fn bounded_name(value: &str) -> bool {
    // Zod's string bounds use JavaScript length (UTF-16 code units).
    (1..=200).contains(&value.encode_utf16().count())
}

fn deserialize_session_id<'de, D: Deserializer<'de>>(
    deserializer: D,
) -> Result<Option<String>, D::Error> {
    // Omission is allowed, but an explicitly supplied null is not a string.
    String::deserialize(deserializer).map(Some)
}

fn valid_question(value: &Value) -> bool {
    let Some(question) = value.as_object() else {
        return false;
    };
    if !question.contains_key("instructions")
        || question
            .keys()
            .any(|key| !matches!(key.as_str(), "type" | "instructions" | "criteria"))
    {
        return false;
    }
    match question.get("type").and_then(Value::as_str) {
        Some("choice") => question
            .get("criteria")
            .and_then(Value::as_object)
            .is_some_and(|options| (1..=MAX_OPTIONS).contains(&options.len())),
        Some("score") => question
            .get("criteria")
            .and_then(Value::as_array)
            .is_some_and(|levels| (2..=MAX_OPTIONS).contains(&levels.len())),
        Some("noul") => match question.get("criteria") {
            None | Some(Value::Null) => true,
            // Reject unsupported outcomes instead of letting Kev silently drop them.
            Some(Value::Object(criteria)) => criteria
                .keys()
                .all(|key| matches!(key.as_str(), "false" | "true")),
            _ => false,
        },
        _ => false,
    }
}

fn protocol_failure() -> RuntimeFailure {
    RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation)
}

/// Validate the runtime identity, question correspondence and authoritative
/// prefill usage. SystemOne generates no model tokens: serialized answer size
/// must never be accepted as output usage.
pub fn normalize_response(
    body: &[u8],
    request: &SystemOneRequest,
    runtime_model: &str,
) -> Result<(Value, NormalizedUsage), RuntimeFailure> {
    // The public struct can also be constructed without going through parse.
    request.validate().map_err(|_| protocol_failure())?;
    let mut response = strict_json(body).map_err(|_| protocol_failure())?;
    let object = response.as_object().ok_or_else(protocol_failure)?;
    if object.get("model").and_then(Value::as_str) != Some(runtime_model) {
        return Err(protocol_failure());
    }
    let answers = object
        .get("answers")
        .and_then(Value::as_object)
        .ok_or_else(protocol_failure)?;
    if answers.len() != request.questions.len() {
        return Err(protocol_failure());
    }
    for (id, question) in &request.questions {
        let answer = answers
            .get(id)
            .and_then(Value::as_object)
            .ok_or_else(protocol_failure)?;
        validate_answer(answer, question)?;
    }
    let usage = object
        .get("usage")
        .and_then(Value::as_object)
        .ok_or_else(protocol_failure)?;
    if !exact_keys(
        usage,
        &["input_tokens", "cached_input_tokens", "output_tokens"],
    ) {
        return Err(protocol_failure());
    }
    let integer = |key: &str| {
        usage
            .get(key)
            .and_then(Value::as_u64)
            .filter(|value| *value <= MAX_SAFE_INTEGER)
            .ok_or_else(protocol_failure)
    };
    let input = integer("input_tokens")?;
    let cached = integer("cached_input_tokens")?;
    if integer("output_tokens")? != 0 || cached > input {
        return Err(protocol_failure());
    }
    let usage = NormalizedUsage::new(input, cached, 0, 0, 0).map_err(|_| protocol_failure())?;
    response["model"] = Value::String(request.model.clone());
    Ok((response, usage))
}

fn exact_keys(object: &Map<String, Value>, keys: &[&str]) -> bool {
    object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key))
}

fn bounded_number(value: &Value, max: f64) -> bool {
    value
        .as_f64()
        .is_some_and(|n| n.is_finite() && (0.0..=max).contains(&n))
}

fn validate_answer(answer: &Map<String, Value>, question: &Value) -> Result<(), RuntimeFailure> {
    if answer.get("type") != question.get("type") {
        return Err(protocol_failure());
    }
    let keys: Vec<String> = match question["type"].as_str() {
        Some("noul") => {
            return if exact_keys(answer, &["type", "noul"]) && bounded_number(&answer["noul"], 1.0)
            {
                Ok(())
            } else {
                Err(protocol_failure())
            };
        }
        Some("choice") => {
            if !exact_keys(answer, &["type", "choice", "confidence", "probabilities"]) {
                return Err(protocol_failure());
            }
            let criteria = question["criteria"]
                .as_object()
                .ok_or_else(protocol_failure)?;
            if !answer["choice"]
                .as_str()
                .is_some_and(|choice| criteria.contains_key(choice))
            {
                return Err(protocol_failure());
            }
            criteria.keys().cloned().collect()
        }
        Some("score") => {
            if !exact_keys(
                answer,
                &["type", "score", "legend", "confidence", "probabilities"],
            ) {
                return Err(protocol_failure());
            }
            let levels = question["criteria"]
                .as_array()
                .ok_or_else(protocol_failure)?;
            if !bounded_number(&answer["score"], (levels.len() - 1) as f64) {
                return Err(protocol_failure());
            }
            let keys: Vec<String> = (0..levels.len()).map(|i| i.to_string()).collect();
            let legend = answer["legend"].as_object().ok_or_else(protocol_failure)?;
            if legend.len() != keys.len()
                || keys
                    .iter()
                    .any(|key| !legend.get(key).is_some_and(Value::is_string))
            {
                return Err(protocol_failure());
            }
            keys
        }
        _ => return Err(protocol_failure()),
    };
    if !bounded_number(&answer["confidence"], 1.0) {
        return Err(protocol_failure());
    }
    let probabilities = answer["probabilities"]
        .as_object()
        .ok_or_else(protocol_failure)?;
    if probabilities.len() != keys.len()
        || keys.iter().any(|key| {
            !probabilities
                .get(key)
                .is_some_and(|value| bounded_number(value, 1.0))
        })
    {
        return Err(protocol_failure());
    }
    let sum: f64 = probabilities.values().filter_map(Value::as_f64).sum();
    // Upstream independently rounds each probability to two decimal places.
    // Accumulated rounding error can exceed .02 for larger option sets.
    let tolerance = 0.02_f64.max(keys.len() as f64 * 0.005) + 1e-12;
    if (sum - 1.0).abs() > tolerance {
        return Err(protocol_failure());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn request_value() -> Value {
        json!({"model":"Exact/Model", "state":{"context":["a", "b"]}, "questions": {
            "pick":{"type":"choice", "instructions":{"task":["pick"]}, "criteria":{"a":null,"b":{"description":"B"}}},
            "yes":{"type":"noul", "instructions":true, "criteria":{"false":[],"true":{}}},
            "level":{"type":"score", "instructions":null, "criteria":["low", {"label":"high"}]}
        }})
    }

    fn request() -> SystemOneRequest {
        SystemOneRequest::parse(&serde_json::to_vec(&request_value()).unwrap()).unwrap()
    }

    #[test]
    fn shared_typescript_request_fixtures_match() {
        for (fixtures, accepted) in [
            (
                include_str!("../test/fixtures/systemone-request.accepted.json"),
                true,
            ),
            (
                include_str!("../test/fixtures/systemone-request.rejected.json"),
                false,
            ),
        ] {
            let fixtures: Vec<Value> = serde_json::from_str(fixtures).unwrap();
            assert!(!fixtures.is_empty());
            for fixture in fixtures {
                let body = serde_json::to_vec(&fixture["request"]).unwrap();
                assert_eq!(
                    SystemOneRequest::parse(&body).is_ok(),
                    accepted,
                    "fixture: {}",
                    fixture["name"]
                );
            }
        }
    }

    #[test]
    fn optional_session_and_utf16_bounds_match_typescript() {
        for (session, accepted) in [
            (json!(null), false),
            (json!(""), false),
            (json!("s"), true),
            (json!("s".repeat(256)), true),
            (json!("s".repeat(257)), false),
            (json!("😀".repeat(128)), true),
            (json!("😀".repeat(129)), false),
        ] {
            let mut body = request_value();
            body["session_id"] = session;
            assert_eq!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_ok(),
                accepted
            );
        }
        let serialized = serde_json::to_value(request()).unwrap();
        assert!(serialized.get("session_id").is_none());
        for (length, accepted) in [(100, true), (101, false)] {
            let mut body = request_value();
            body["model"] = json!("😀".repeat(length));
            assert_eq!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_ok(),
                accepted
            );
            let mut body = request_value();
            body["questions"] = json!({"😀".repeat(length):{"type":"noul","instructions":null}});
            assert_eq!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_ok(),
                accepted
            );
        }
    }

    #[test]
    fn noul_criteria_reject_unknown_outcomes_without_dropping_them() {
        for (criteria, accepted) in [
            (Value::Null, true),
            (json!({}), true),
            (json!({"false":null}), true),
            (json!({"true":["yes"]}), true),
            (json!({"false":[],"true":{"description":"yes"}}), true),
            (json!({"ignored-upstream":null}), false),
            (json!({"false":null,"true":null,"extra":null}), false),
            (json!({"False":null}), false),
            (json!({"true ":null}), false),
        ] {
            let mut body = request_value();
            body["questions"]["yes"]["criteria"] = criteria.clone();
            let result = SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap());
            assert_eq!(result.is_ok(), accepted, "criteria: {criteria}");
            if let Ok(request) = result {
                assert_eq!(request.questions["yes"]["criteria"], criteria);
            }
        }
    }

    fn response() -> Value {
        json!({"model":"runtime-model", "answers":{
            "pick":{"type":"choice","choice":"b","confidence":0.5,"probabilities":{"a":0.25,"b":0.75}},
            "yes":{"type":"noul","noul":0.7},
            "level":{"type":"score","score":0.75,"legend":{"0":"low","1":"label: high"},"confidence":0.75,"probabilities":{"0":0.25,"1":0.75}}
        },"usage":{"input_tokens":10,"cached_input_tokens":3,"output_tokens":0}, "latency_ms":2.0})
    }

    fn normalize(value: &Value) -> Result<(Value, NormalizedUsage), RuntimeFailure> {
        normalize_response(
            &serde_json::to_vec(value).unwrap(),
            &request(),
            "runtime-model",
        )
    }

    #[test]
    fn accepts_structured_questions_and_preserves_exact_model() {
        let request = request();
        assert_eq!(request.model, "Exact/Model");
        assert_eq!(request.service_tier, ServiceTier::Default);
        assert_eq!(request.session_id, None);
        assert_eq!(
            SystemOneRequest::parse(&serde_json::to_vec(&request).unwrap()).unwrap(),
            request
        );
        let (result, usage) = normalize(&response()).unwrap();
        assert_eq!(result["model"], request.model);
        assert_eq!(usage, NormalizedUsage::new(10, 3, 0, 0, 0).unwrap());
    }

    #[test]
    fn rejects_unknown_missing_and_invalid_request_fields() {
        for (key, value) in [
            ("model", json!("")),
            ("model", json!("x".repeat(201))),
            ("model", json!(3)),
            ("state", Value::Null),
            ("state", json!(false)),
            ("state", json!(3)),
            ("questions", json!({})),
            ("questions", json!([])),
            ("service_tier", json!("fast")),
            ("service_tier", json!("flex")),
            ("service_tier", Value::Null),
            ("session_id", json!(1)),
            ("priority", json!(0)),
            ("stream", json!(false)),
            ("max_tokens", json!(0)),
            ("unknown", Value::Null),
        ] {
            let mut body = request_value();
            body[key] = value;
            assert!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_err(),
                "{key}"
            );
        }
        for key in ["model", "state", "questions"] {
            let mut body = request_value();
            body.as_object_mut().unwrap().remove(key);
            assert!(SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_err());
        }
        for question in [
            json!({"type":"other","instructions":""}),
            json!({"type":"noul"}),
            json!({"type":"noul","instructions":"","extra":1}),
            json!({"type":"noul","instructions":"","criteria":[]}),
            json!({"type":"choice","instructions":"","criteria":{}}),
            json!({"type":"choice","instructions":"","criteria":[]}),
            json!({"type":"score","instructions":"","criteria":["only"]}),
            json!({"type":"score","instructions":"","criteria":vec!["";256]}),
        ] {
            let mut body = request_value();
            body["questions"]["pick"] = question;
            assert!(SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_err());
        }
    }

    #[test]
    fn request_count_and_name_boundaries() {
        for (count, valid) in [(1, true), (64, true), (65, false)] {
            let mut body = request_value();
            body["questions"] = Value::Object(
                (0..count)
                    .map(|i| (i.to_string(), json!({"type":"noul","instructions":[]})))
                    .collect(),
            );
            assert_eq!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_ok(),
                valid
            );
        }
        for (len, valid) in [(0, false), (1, true), (200, true), (201, false)] {
            let mut body = request_value();
            body["questions"] = json!({"x".repeat(len):{"type":"noul","instructions":{}}});
            assert_eq!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_ok(),
                valid
            );
        }
    }

    #[test]
    fn rejects_malformed_json_and_duplicates_at_all_depths() {
        for body in [
            "",
            "{",
            "null",
            "{} {}",
            "{\"a\":1e999}",
            r#"{"model":"a","model":"b"}"#,
            r#"{"state":{"a":1,"\u0061":2}}"#,
            r#"{"questions":{"q":{"instructions":[{"a":1,"a":2}]}}}"#,
        ] {
            assert!(SystemOneRequest::parse(body.as_bytes()).is_err());
            assert_eq!(
                normalize_response(body.as_bytes(), &request(), "runtime-model")
                    .unwrap_err()
                    .kind(),
                RuntimeFailureKind::ProtocolViolation
            );
        }
        let valid = serde_json::to_string(&request_value()).unwrap();
        for (original, duplicate) in [
            (
                r#""model":"Exact/Model""#,
                r#""model":"Exact/Model","model":"Exact/Model""#,
            ),
            (
                r#""context":["a","b"]"#,
                r#""context":["a","b"],"context":["a","b"]"#,
            ),
            (r#""task":["pick"]"#, r#""task":["pick"],"task":["pick"]"#),
            (r#""a":null"#, r#""a":null,"\u0061":null"#),
        ] {
            let body = valid.replace(original, duplicate);
            assert_ne!(body, valid);
            assert!(SystemOneRequest::parse(body.as_bytes()).is_err());
        }
        let duplicate = serde_json::to_string(&response()).unwrap().replace(
            "\"input_tokens\":10",
            "\"input_tokens\":10,\"input_tokens\":10",
        );
        assert!(normalize_response(duplicate.as_bytes(), &request(), "runtime-model").is_err());
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
        let mut request = request();
        request.questions = json!({"q":{"type":"choice","instructions":"","criteria":(0..30).map(|i| (i.to_string(), Value::Null)).collect::<Map<_,_>>()}}).as_object().unwrap().clone();
        let mut body = response();
        body["answers"] = json!({"q":{"type":"choice","choice":"0","confidence":0,"probabilities":(0..30).map(|i| (i.to_string(), json!(0.03))).collect::<Map<_,_>>()}});
        assert!(normalize_response(
            &serde_json::to_vec(&body).unwrap(),
            &request,
            "runtime-model"
        )
        .is_ok());
    }
}
