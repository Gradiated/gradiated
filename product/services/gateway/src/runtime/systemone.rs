use serde::Serialize;
use serde_json::{json, Map, Number, Value};

use super::{
    client::{read_bounded_body, rejected_response, send, Call, ModelNames},
    ProtocolViolation, RuntimeCompletion, RuntimeFailure, SglangClient,
};
use crate::{
    json::strict_json,
    model::MAX_SAFE_INTEGER,
    systemone::{AnswerShape, SystemOneRequest},
    NormalizedUsage,
};

const SYSTEMONE: &str = "v1/systemone";
const RESPONSE_KEYS: [&str; 4] = ["model", "answers", "usage", "latency_ms"];
const USAGE_KEYS: [&str; 3] = ["input_tokens", "cached_input_tokens", "output_tokens"];

impl SglangClient {
    pub(super) async fn complete_system_one(
        &self,
        call: Call<'_>,
        decision: &SystemOneRequest,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let models = ModelNames::new(&call);
        let body = serde_json::to_vec(&json!({
            "model": models.runtime,
            "state": decision.state,
            "questions": decision.questions(),
            "priority": call.request.service_tier.runtime_priority(),
        }))
        .map_err(|_| ProtocolViolation::Json)?;

        let upstream = self.post(call.deployment, SYSTEMONE, body);
        let response = send(upstream).await?;
        let status = response.status();
        if !status.is_success() {
            return Err(rejected_response(response).await);
        }

        let body = read_bounded_body(response).await?;
        let (response, usage) = normalize_response(&body, decision, &models)?;

        Ok(RuntimeCompletion {
            response,
            usage,
            finish_reason: "stop".to_owned(),
            upstream_cost_nano_usd: None,
        })
    }
}

#[derive(Serialize)]
struct DecisionResponse {
    model: String,
    answers: Map<String, Value>,
    usage: DecisionUsage,
    #[serde(skip_serializing_if = "Option::is_none")]
    latency_ms: Option<Number>,
}

#[derive(Serialize)]
struct DecisionUsage {
    input_tokens: u64,
    cached_input_tokens: u64,
    output_tokens: u64,
}

/// SystemOne generates no model tokens, so serialized answer size must never be
/// accepted as output usage.
pub(super) fn normalize_response(
    body: &[u8],
    request: &SystemOneRequest,
    models: &ModelNames,
) -> Result<(Value, NormalizedUsage), RuntimeFailure> {
    let Value::Object(mut object) = strict_json(body).map_err(|_| ProtocolViolation::Json)? else {
        return Err(ProtocolViolation::ResponseShape.into());
    };
    ensure(
        object
            .keys()
            .all(|key| RESPONSE_KEYS.contains(&key.as_str())),
        ProtocolViolation::ResponseShape,
    )?;
    ensure(
        object.get("model").and_then(Value::as_str) == Some(models.runtime.as_str()),
        ProtocolViolation::ModelMismatch,
    )?;

    let Some(Value::Object(answers)) = object.remove("answers") else {
        return Err(ProtocolViolation::DecisionAnswer.into());
    };
    validate_answers(&answers, request.answer_shapes())?;

    let usage = decision_usage(object.get("usage"))?;
    let latency_ms = object.remove("latency_ms").map(latency).transpose()?;

    let response = DecisionResponse {
        model: models.requested.clone(),
        answers,
        usage: DecisionUsage {
            input_tokens: usage.input_tokens(),
            cached_input_tokens: usage.cached_input_tokens(),
            output_tokens: 0,
        },
        latency_ms,
    };
    let response = serde_json::to_value(response).map_err(|_| ProtocolViolation::Json)?;

    Ok((response, usage))
}

fn latency(value: Value) -> Result<Number, RuntimeFailure> {
    match value {
        Value::Number(latency) if bounded_number(&latency, f64::MAX) => Ok(latency),
        _ => Err(ProtocolViolation::ResponseShape.into()),
    }
}

fn decision_usage(usage: Option<&Value>) -> Result<NormalizedUsage, RuntimeFailure> {
    let usage = usage
        .and_then(Value::as_object)
        .ok_or(ProtocolViolation::Usage)?;
    ensure(exact_keys(usage, &USAGE_KEYS), ProtocolViolation::Usage)?;

    let integer = |key: &str| {
        usage
            .get(key)
            .and_then(Value::as_u64)
            .filter(|value| *value <= MAX_SAFE_INTEGER)
            .ok_or(ProtocolViolation::Usage)
    };
    let input = integer("input_tokens")?;
    let cached = integer("cached_input_tokens")?;
    ensure(
        integer("output_tokens")? == 0 && cached <= input,
        ProtocolViolation::Usage,
    )?;

    NormalizedUsage::new(input, cached, 0, 0, 0).map_err(|_| ProtocolViolation::Usage.into())
}

fn validate_answers(
    answers: &Map<String, Value>,
    shapes: &[(String, AnswerShape)],
) -> Result<(), RuntimeFailure> {
    ensure_answer(answers.len() == shapes.len())?;

    for (id, shape) in shapes {
        let answer = answers
            .get(id)
            .and_then(Value::as_object)
            .ok_or(ProtocolViolation::DecisionAnswer)?;
        validate_answer(answer, shape)?;
    }

    Ok(())
}

fn validate_answer(answer: &Map<String, Value>, shape: &AnswerShape) -> Result<(), RuntimeFailure> {
    ensure_answer(answer.get("type").and_then(Value::as_str) == Some(shape.type_name()))?;

    match shape {
        AnswerShape::Noul => ensure_answer(
            exact_keys(answer, &["type", "noul"]) && bounded_value(field(answer, "noul")?, 1.0),
        ),
        AnswerShape::Choice { options } => {
            validate_choice(answer, options)?;
            validate_distribution(answer, options)
        }
        AnswerShape::Score { levels } => {
            let outcomes = score_outcomes(answer, *levels)?;
            validate_distribution(answer, &outcomes)
        }
    }
}

fn validate_choice(answer: &Map<String, Value>, options: &[String]) -> Result<(), RuntimeFailure> {
    ensure_answer(exact_keys(
        answer,
        &["type", "choice", "confidence", "probabilities"],
    ))?;

    ensure_answer(
        field(answer, "choice")?
            .as_str()
            .is_some_and(|choice| options.iter().any(|option| option == choice)),
    )
}

fn score_outcomes(
    answer: &Map<String, Value>,
    levels: usize,
) -> Result<Vec<String>, RuntimeFailure> {
    ensure_answer(exact_keys(
        answer,
        &["type", "score", "legend", "confidence", "probabilities"],
    ))?;
    ensure_answer(bounded_value(field(answer, "score")?, (levels - 1) as f64))?;

    let outcomes: Vec<String> = (0..levels).map(|level| level.to_string()).collect();
    let legend = field(answer, "legend")?
        .as_object()
        .ok_or(ProtocolViolation::DecisionAnswer)?;
    ensure_answer(
        legend.len() == outcomes.len()
            && outcomes
                .iter()
                .all(|key| legend.get(key).is_some_and(Value::is_string)),
    )?;

    Ok(outcomes)
}

fn validate_distribution(
    answer: &Map<String, Value>,
    outcomes: &[String],
) -> Result<(), RuntimeFailure> {
    ensure_answer(bounded_value(field(answer, "confidence")?, 1.0))?;

    let probabilities = field(answer, "probabilities")?
        .as_object()
        .ok_or(ProtocolViolation::DecisionAnswer)?;
    ensure_answer(
        probabilities.len() == outcomes.len()
            && outcomes.iter().all(|key| {
                probabilities
                    .get(key)
                    .is_some_and(|value| bounded_value(value, 1.0))
            }),
    )?;

    // Upstream independently rounds each probability to two decimal places.
    // Accumulated rounding error can exceed .02 for larger option sets.
    let sum: f64 = probabilities.values().filter_map(Value::as_f64).sum();
    let tolerance = 0.02_f64.max(outcomes.len() as f64 * 0.005) + 1e-12;

    ensure_answer((sum - 1.0).abs() <= tolerance)
}

fn ensure(condition: bool, violation: ProtocolViolation) -> Result<(), RuntimeFailure> {
    if condition {
        Ok(())
    } else {
        Err(violation.into())
    }
}

fn ensure_answer(condition: bool) -> Result<(), RuntimeFailure> {
    ensure(condition, ProtocolViolation::DecisionAnswer)
}

fn field<'a>(answer: &'a Map<String, Value>, key: &str) -> Result<&'a Value, RuntimeFailure> {
    answer
        .get(key)
        .ok_or_else(|| ProtocolViolation::DecisionAnswer.into())
}

fn exact_keys(object: &Map<String, Value>, keys: &[&str]) -> bool {
    object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key))
}

fn bounded_value(value: &Value, max: f64) -> bool {
    matches!(value, Value::Number(number) if bounded_number(number, max))
}

fn bounded_number(number: &Number, max: f64) -> bool {
    number
        .as_f64()
        .is_some_and(|n| n.is_finite() && (0.0..=max).contains(&n))
}
