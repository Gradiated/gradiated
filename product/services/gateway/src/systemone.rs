use serde::{Deserialize, Deserializer};
use serde_json::{Map, Value};

use crate::{json::strict_json, GatewayError, ServiceTier};

const MAX_OPTIONS: usize = 255;

#[derive(Clone, Debug, PartialEq)]
pub struct SystemOneRequest {
    pub model: String,
    pub state: Value,
    pub session_id: Option<String>,
    pub service_tier: ServiceTier,
    questions: Map<String, Value>,
    shapes: Vec<(String, AnswerShape)>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WireRequest {
    model: String,
    state: Value,
    questions: Map<String, Value>,
    #[serde(default, deserialize_with = "deserialize_session_id")]
    session_id: Option<String>,
    #[serde(default)]
    service_tier: ServiceTier,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum AnswerShape {
    Noul,
    Choice { options: Vec<String> },
    Score { levels: usize },
}

impl AnswerShape {
    fn parse(value: &Value) -> Option<Self> {
        let question = value.as_object()?;
        if !question.contains_key("instructions")
            || question
                .keys()
                .any(|key| !matches!(key.as_str(), "type" | "instructions" | "criteria"))
        {
            return None;
        }

        let criteria = question.get("criteria");
        match question.get("type")?.as_str()? {
            "choice" => {
                let options = criteria?.as_object()?;
                (1..=MAX_OPTIONS)
                    .contains(&options.len())
                    .then(|| Self::Choice {
                        options: options.keys().cloned().collect(),
                    })
            }
            "score" => {
                let levels = criteria?.as_array()?.len();
                (2..=MAX_OPTIONS)
                    .contains(&levels)
                    .then_some(Self::Score { levels })
            }
            "noul" => match criteria {
                None | Some(Value::Null) => Some(Self::Noul),
                // Reject unsupported outcomes instead of letting Kev silently drop them.
                Some(Value::Object(criteria)) => criteria
                    .keys()
                    .all(|key| matches!(key.as_str(), "false" | "true"))
                    .then_some(Self::Noul),
                _ => None,
            },
            _ => None,
        }
    }

    pub(crate) fn type_name(&self) -> &'static str {
        match self {
            Self::Noul => "noul",
            Self::Choice { .. } => "choice",
            Self::Score { .. } => "score",
        }
    }
}

impl SystemOneRequest {
    pub fn parse(body: &[u8]) -> Result<Self, GatewayError> {
        let value = strict_json(body).map_err(|_| GatewayError::invalid_request(None))?;
        let wire: WireRequest =
            serde_json::from_value(value).map_err(|_| GatewayError::invalid_request(None))?;

        if !bounded_name(&wire.model) {
            return Err(GatewayError::invalid_request(Some("model")));
        }

        if !matches!(
            wire.state,
            Value::String(_) | Value::Object(_) | Value::Array(_)
        ) {
            return Err(GatewayError::invalid_request(Some("state")));
        }

        if wire.service_tier != ServiceTier::Default {
            return Err(GatewayError::unsupported_parameter("service_tier"));
        }

        if wire
            .session_id
            .as_ref()
            .is_some_and(|session| !(1..=256).contains(&session.encode_utf16().count()))
        {
            return Err(GatewayError::invalid_request(Some("session_id")));
        }

        let shapes = question_shapes(&wire.questions)
            .ok_or(GatewayError::invalid_request(Some("questions")))?;

        Ok(Self {
            model: wire.model,
            state: wire.state,
            session_id: wire.session_id,
            service_tier: wire.service_tier,
            questions: wire.questions,
            shapes,
        })
    }

    pub(crate) fn questions(&self) -> &Map<String, Value> {
        &self.questions
    }

    pub(crate) fn answer_shapes(&self) -> &[(String, AnswerShape)] {
        &self.shapes
    }
}

fn question_shapes(questions: &Map<String, Value>) -> Option<Vec<(String, AnswerShape)>> {
    if !(1..=64).contains(&questions.len()) {
        return None;
    }

    questions
        .iter()
        .map(|(id, question)| {
            let shape = AnswerShape::parse(question).filter(|_| bounded_name(id))?;
            Some((id.clone(), shape))
        })
        .collect()
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

#[cfg(test)]
pub(crate) mod fixtures {
    use serde_json::{json, Value};

    use super::SystemOneRequest;

    pub(crate) fn request_value() -> Value {
        json!({"model":"Exact/Model", "state":{"context":["a", "b"]}, "questions": {
            "pick":{"type":"choice", "instructions":{"task":["pick"]}, "criteria":{"a":null,"b":{"description":"B"}}},
            "yes":{"type":"noul", "instructions":true, "criteria":{"false":[],"true":{}}},
            "level":{"type":"score", "instructions":null, "criteria":["low", {"label":"high"}]}
        }})
    }

    pub(crate) fn request() -> SystemOneRequest {
        SystemOneRequest::parse(&serde_json::to_vec(&request_value()).unwrap()).unwrap()
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        fixtures::{request, request_value},
        *,
    };

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

    #[test]
    fn accepts_structured_questions() {
        let request = request();

        assert_eq!(request.model, "Exact/Model");
        assert_eq!(request.service_tier, ServiceTier::Default);
        assert_eq!(request.session_id, None);
        assert_eq!(
            request
                .answer_shapes()
                .iter()
                .map(|(id, shape)| (id.as_str(), shape.type_name()))
                .collect::<Vec<_>>(),
            [("pick", "choice"), ("yes", "noul"), ("level", "score")]
        );
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
    }
}
