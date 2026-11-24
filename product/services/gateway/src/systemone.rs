use serde::{Deserialize, Deserializer};
use serde_json::{Map, Value};

use crate::{json::strict_json, GatewayError, ServiceTier};

const MAX_OPTIONS: usize = 255;
/// Questions per request. Every runtime (Kev's `kev_http` adapter, which Decider,
/// Linden and the PostHog runtimes share) accepts the same bound, and their token
/// limits stop a request with this many questions long before this count matters.
pub(crate) const MAX_QUESTIONS: usize = 1024;

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
        // Instructions are optional, as in TypeSafe's API: its SDK omits them when a question has only criteria.
        if question
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
                // One level is a valid rubric in TypeSafe's API: its answer is certain.
                let levels = criteria?.as_array()?.len();
                (1..=MAX_OPTIONS)
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

        let mut questions = wire.questions;
        let shapes = question_shapes(&mut questions)
            .ok_or(GatewayError::invalid_request(Some("questions")))?;
        Ok(Self {
            model: wire.model,
            state: wire.state,
            session_id: wire.session_id,
            service_tier: wire.service_tier,
            questions,
            shapes,
        })
    }

    /// The questions as runtimes receive them: choice criteria are always in object form.
    pub(crate) fn questions(&self) -> &Map<String, Value> {
        &self.questions
    }

    pub(crate) fn answer_shapes(&self) -> &[(String, AnswerShape)] {
        &self.shapes
    }
}

fn question_shapes(questions: &mut Map<String, Value>) -> Option<Vec<(String, AnswerShape)>> {
    if !(1..=MAX_QUESTIONS).contains(&questions.len()) {
        return None;
    }

    questions
        .iter_mut()
        .map(|(id, question)| {
            normalize_choice_criteria(question)?;
            let shape = AnswerShape::parse(question).filter(|_| bounded_name(id))?;
            Some((id.clone(), shape))
        })
        .collect()
}

/// Rewrites list-form choice criteria (`["billing", "technical"]`, as PostHog's
/// clients send) to the object form with undescribed options
/// (`{"billing": null, "technical": null}`), so that runtimes, answer validation
/// and everything else see only the object form. A list must hold 1 to 255
/// distinct, non-empty strings.
fn normalize_choice_criteria(question: &mut Value) -> Option<()> {
    let Some(question) = question.as_object_mut() else {
        return Some(());
    };
    if question.get("type").and_then(Value::as_str) != Some("choice") {
        return Some(());
    }
    let Some(Value::Array(labels)) = question.get("criteria") else {
        return Some(());
    };
    if !(1..=MAX_OPTIONS).contains(&labels.len()) {
        return None;
    }

    let mut options = Map::with_capacity(labels.len());
    for label in labels {
        let label = label.as_str().filter(|label| !label.is_empty())?;
        if options.insert(label.to_owned(), Value::Null).is_some() {
            return None;
        }
    }
    question.insert("criteria".to_owned(), Value::Object(options));

    Some(())
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
            json!({"type":"noul","instructions":"","extra":1}),
            json!({"type":"noul","instructions":"","criteria":[]}),
            json!({"type":"choice","instructions":"","criteria":{}}),
            json!({"type":"choice","instructions":"","criteria":[]}),
            json!({"type":"score","instructions":"","criteria":vec!["";256]}),
        ] {
            let mut body = request_value();
            body["questions"]["pick"] = question;
            assert!(SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_err());
        }
    }

    #[test]
    fn instructions_are_optional_and_a_score_may_have_one_level() {
        // TypeSafe's API accepts both; its SDK omits instructions for criteria-only questions.
        for question in [
            json!({"type":"noul"}),
            json!({"type":"noul","criteria":{"true":"Angry","false":"Calm"}}),
            json!({"type":"choice","criteria":{"billing":"Charges","access":"Login"}}),
            json!({"type":"score","criteria":["calm","annoyed","furious"]}),
            json!({"type":"score","instructions":"Rate","criteria":["only"]}),
        ] {
            let mut body = request_value();
            body["questions"]["pick"] = question.clone();
            assert!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_ok(),
                "{question}"
            );
        }
    }

    #[test]
    fn list_choice_criteria_become_undescribed_options_in_order() {
        let mut body = request_value();
        body["questions"]["pick"] = json!({"type":"choice","criteria":["technical","billing"]});
        let request = SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).unwrap();

        let criteria = &request.questions()["pick"]["criteria"];
        assert_eq!(criteria, &json!({"technical":null,"billing":null}));
        assert_eq!(
            criteria.as_object().unwrap().keys().collect::<Vec<_>>(),
            ["technical", "billing"]
        );
        assert_eq!(
            request.answer_shapes()[0],
            (
                "pick".to_owned(),
                AnswerShape::Choice {
                    options: vec!["technical".to_owned(), "billing".to_owned()]
                }
            )
        );
        // Other questions are forwarded unchanged.
        assert_eq!(
            request.questions()["level"],
            request_value()["questions"]["level"]
        );
    }

    #[test]
    fn list_choice_criteria_follow_the_object_bounds() {
        let labels =
            |count: usize| Value::from((0..count).map(|i| i.to_string()).collect::<Vec<_>>());
        for (criteria, accepted) in [
            (json!(["only"]), true),
            (labels(255), true),
            (json!(["😀", " ", "a".repeat(10_000)]), true),
            (json!([]), false),
            (labels(256), false),
            (json!(["a", "a"]), false),
            (json!(["a", "b", "a"]), false),
            (json!([""]), false),
            (json!(["a", ""]), false),
            (json!(["a", null]), false),
            (json!(["a", 1]), false),
            (json!(["a", ["b"]]), false),
            (json!(["a", {"b":null}]), false),
            (json!([true]), false),
        ] {
            let mut body = request_value();
            body["questions"]["pick"]["criteria"] = criteria.clone();
            assert_eq!(
                SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).is_ok(),
                accepted,
                "criteria: {criteria}"
            );
        }
        // Only choice criteria have a list form for labels; score lists stay level descriptions.
        let mut body = request_value();
        body["questions"]["level"]["criteria"] = json!(["low", "low"]);
        let request = SystemOneRequest::parse(&serde_json::to_vec(&body).unwrap()).unwrap();
        assert_eq!(
            request.questions()["level"]["criteria"],
            json!(["low", "low"])
        );
    }

    #[test]
    fn question_bound_matches_typescript() {
        // The shared fixtures stop at 65 questions; this keeps the bound itself in step.
        let contract = include_str!("../../../packages/contracts/src/systemone.ts");
        assert!(contract.contains(&format!(
            "export const SYSTEMONE_MAX_QUESTIONS = {MAX_QUESTIONS};"
        )));
        let mock = include_str!("../test/integration/mock-runtimes/kev.ts");
        assert!(mock.contains(&format!("const MAX_QUESTIONS = {MAX_QUESTIONS};")));
    }

    #[test]
    fn request_count_and_name_boundaries() {
        for (count, valid) in [
            (1, true),
            (64, true),
            (65, true),
            (MAX_QUESTIONS, true),
            (MAX_QUESTIONS + 1, false),
        ] {
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
