//! Text prompt encoding for the pinned vLLM DeepSeek V4.1 release.
//! Adapted from vLLM's Apache-2.0 deepseek_v41_encoding.py.
use super::{ChatCompletionRequest, TokenizerRequestError};
use serde_json::{json, Value};

const BOS: &str = "<｜begin▁of▁sentence｜>";
const EOS: &str = "<｜end▁of▁sentence｜>";
const USER: &str = "<｜User｜>";
const SYSTEM: &str = "<｜System｜>";
const ASSISTANT: &str = "<｜Assistant｜>";

fn content(value: &Value) -> Result<String, TokenizerRequestError> {
    match value {
        Value::Null => Ok(String::new()),
        Value::String(text) => Ok(text.clone()),
        Value::Array(parts) => parts
            .iter()
            .map(|part| {
                if !matches!(part["type"].as_str(), Some("text")) {
                    return Err(TokenizerRequestError::Rejected);
                }
                part["text"]
                    .as_str()
                    .map(str::to_owned)
                    .ok_or(TokenizerRequestError::InvalidInput)
            })
            .collect::<Result<Vec<_>, _>>()
            .map(|parts| parts.join("\n\n")),
        _ => Err(TokenizerRequestError::InvalidInput),
    }
}

// Match json.dumps(..., ensure_ascii=False), including separator whitespace.
fn python_json(value: &Value) -> String {
    match value {
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_json)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!("{}: {}", json!(key), python_json(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        _ => value.to_string(),
    }
}

fn calls(value: &Value) -> Result<String, TokenizerRequestError> {
    let Some(calls) = value.as_array().filter(|v| !v.is_empty()) else {
        return Ok(String::new());
    };
    let mut rendered = Vec::new();
    for call in calls {
        let function = &call["function"];
        let name = function["name"]
            .as_str()
            .ok_or(TokenizerRequestError::InvalidInput)?;
        let mut args = function["arguments"].clone();
        for _ in 0..2 {
            if let Some(text) = args.as_str() {
                match serde_json::from_str(text) {
                    Ok(parsed) => args = parsed,
                    Err(_) => break,
                }
            }
        }
        if !args.is_object() {
            args = json!({"arguments": function["arguments"]});
        }
        let args = args
            .as_object()
            .ok_or(TokenizerRequestError::InvalidInput)?;
        let parameters = args
            .iter()
            .map(|(key, value)| {
                format!(
                    "<｜DSML｜ parameter name=\"{key}\" string=\"{}\">{}</｜DSML｜ parameter>",
                    value.is_string(),
                    value
                        .as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| python_json(value))
                )
            })
            .collect::<Vec<_>>()
            .join("\n");
        rendered.push(format!(
            "<｜DSML｜ invoke name=\"{name}\">\n{parameters}\n</｜DSML｜ invoke>"
        ));
    }
    Ok(format!(
        "\n\n<｜DSML｜ calls>\n{}\n</｜DSML｜ calls>",
        rendered.join("\n")
    ))
}

// Match the pinned vLLM FunctionDefinition serializer before prompt encoding.
// Optional description/parameters become null; strict/defer_loading are omitted
// when null, and unrecognized fields are not part of the rendered definition.
fn tool_schema(tool: &Value) -> Result<String, TokenizerRequestError> {
    let function = tool["function"]
        .as_object()
        .ok_or(TokenizerRequestError::InvalidInput)?;
    let name = function
        .get("name")
        .and_then(Value::as_str)
        .ok_or(TokenizerRequestError::InvalidInput)?;
    let mut normalized = json!({
        "name": name,
        "description": function.get("description").unwrap_or(&Value::Null),
        "parameters": function.get("parameters").unwrap_or(&Value::Null),
    });
    for key in ["strict", "defer_loading"] {
        if let Some(value) = function.get(key).filter(|value| !value.is_null()) {
            normalized[key] = value.clone();
        }
    }
    Ok(python_json(&normalized))
}

pub(super) fn render(request: &ChatCompletionRequest) -> Result<String, TokenizerRequestError> {
    let kwargs = request.parameters.get("chat_template_kwargs");
    let option = |name: &str| kwargs.and_then(|v| v.get(name));
    let mut thinking = match (option("thinking"), option("enable_thinking")) {
        (None, None) => true,
        (a, b) => {
            a.and_then(Value::as_bool).unwrap_or(false)
                || b.and_then(Value::as_bool).unwrap_or(false)
        }
    };
    let effort = option("reasoning_effort").or_else(|| request.parameters.get("reasoning_effort"));
    let budget = match effort {
        None | Some(Value::Null) => 50,
        Some(Value::String(s)) => match s.as_str() {
            "none" => {
                thinking = false;
                50
            }
            "low" => 25,
            "high" => 50,
            "xhigh" => 75,
            "max" => 100,
            _ => return Err(TokenizerRequestError::Rejected),
        },
        Some(value) => value
            .as_u64()
            .filter(|n| (1..=100).contains(n))
            .ok_or(TokenizerRequestError::Rejected)?,
    };
    let tools = request
        .parameters
        .get("tools")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty());
    let drop_thinking = tools.is_none()
        && option("drop_thinking")
            .and_then(Value::as_bool)
            .unwrap_or(true);
    let mut messages = request.messages.clone();
    for message in &messages {
        // These are internal encoder controls, not OpenAI message fields.
        if [
            "task",
            "wo_eos",
            "content_blocks",
            "response_format",
            "tools",
        ]
        .iter()
        .any(|key| message.get(key).is_some())
        {
            return Err(TokenizerRequestError::Rejected);
        }
    }
    if let Some(tools) = tools {
        if !messages.iter().any(|m| m["role"] == "system") {
            messages.insert(0, json!({"role":"system", "content":""}));
        }
        if let Some(system) = messages.iter_mut().find(|m| m["role"] == "system") {
            system["tools"] = json!(tools);
        }
    }
    let mut merged: Vec<Value> = Vec::new();
    let mut call_order = std::collections::HashMap::new();
    for mut message in messages {
        let role = message["role"]
            .as_str()
            .ok_or(TokenizerRequestError::InvalidInput)?
            .to_owned();
        if !matches!(
            role.as_str(),
            "system" | "developer" | "user" | "assistant" | "tool"
        ) {
            return Err(TokenizerRequestError::Rejected);
        }
        message["content"] = json!(content(&message["content"])?);
        if let Some(reasoning) = message.get("reasoning").cloned() {
            message["reasoning_content"] = reasoning;
        }
        if role == "assistant" {
            if let Some(calls) = message["tool_calls"].as_array() {
                call_order.clear();
                for (index, call) in calls.iter().enumerate() {
                    if let Some(id) = call["id"].as_str() {
                        call_order.insert(id.to_owned(), index);
                    }
                }
            }
        }
        if role == "user" || role == "tool" {
            let block = if role == "tool" {
                json!({"type":"tool_result", "content":message["content"], "order":call_order.get(message["tool_call_id"].as_str().unwrap_or("")).copied().unwrap_or(0)})
            } else {
                json!({"type":"text", "content":message["content"]})
            };
            if let Some(last) = merged.last_mut().filter(|m| m["role"] == "user") {
                last["blocks"]
                    .as_array_mut()
                    .ok_or(TokenizerRequestError::InvalidInput)?
                    .push(block);
            } else {
                merged.push(json!({"role":"user", "blocks":[block]}));
            }
        } else {
            merged.push(message);
        }
    }
    let prior_last_user = merged
        .iter()
        .enumerate()
        .rfind(|(i, m)| m["role"] == "user" || (*i > 0 && m["role"] == "system"))
        .map(|(i, _)| i);
    if thinking && drop_thinking {
        // Match the pinned runtime's history pruning, including developer turns.
        merged = merged
            .into_iter()
            .enumerate()
            .filter_map(|(i, m)| {
                (m["role"] != "developer" || prior_last_user.is_none_or(|last| i >= last))
                    .then_some(m)
            })
            .collect();
    }
    let last_user = merged
        .iter()
        .enumerate()
        .rfind(|(i, m)| m["role"] == "user" || (*i > 0 && m["role"] == "system"))
        .map(|(i, _)| i);
    let mut prompt = String::from(BOS);
    for (index, message) in merged.iter().enumerate() {
        let role = message["role"]
            .as_str()
            .ok_or(TokenizerRequestError::InvalidInput)?;
        if index == 0 && (thinking || role == "system") {
            prompt.push_str(SYSTEM);
        }
        if index == 0 && thinking {
            prompt.push_str(&format!("Reasoning Effort: {budget} (range 1-100, the higher the value, the more thorough the reasoning)\n\n"));
        }
        match role {
            "system" | "developer" => {
                if role == "system" && index > 0 {
                    prompt.push_str(SYSTEM);
                }
                if role == "developer" {
                    prompt.push_str(USER);
                }
                let text = content(&message["content"])?;
                if role == "developer" && text.is_empty() {
                    return Err(TokenizerRequestError::Rejected);
                }
                prompt.push_str(&text);
                if let Some(tools) = message["tools"].as_array().filter(|v| !v.is_empty()) {
                    let schemas = tools
                        .iter()
                        .map(tool_schema)
                        .collect::<Result<Vec<_>, _>>()?
                        .join("\n");
                    prompt.push_str("\n\n");
                    prompt.push_str(
                        &include_str!("deepseek_v41_tools.txt").replace("{tool_schemas}", &schemas),
                    );
                }
            }
            "user" => {
                prompt.push_str(USER);
                let blocks = message["blocks"]
                    .as_array()
                    .ok_or(TokenizerRequestError::InvalidInput)?;
                let mut tool_blocks = blocks
                    .iter()
                    .filter(|b| b["type"] == "tool_result")
                    .collect::<Vec<_>>();
                tool_blocks.sort_by_key(|b| b["order"].as_u64().unwrap_or(0));
                let mut results = tool_blocks.into_iter();
                let mut parts = Vec::new();
                for block in blocks {
                    if block["type"] == "tool_result" {
                        let result = results.next().ok_or(TokenizerRequestError::InvalidInput)?;
                        parts.push(format!(
                            "<tool_result>{}</tool_result>",
                            content(&result["content"])?
                        ));
                    } else {
                        parts.push(content(&block["content"])?);
                    }
                }
                prompt.push_str(&parts.join("\n\n"));
            }
            "assistant" => {
                if thinking && (!drop_thinking || last_user.is_none_or(|last| index > last)) {
                    prompt.push_str(&content(&message["reasoning_content"])?);
                    prompt.push_str("</think>");
                }
                prompt.push_str(&content(&message["content"])?);
                prompt.push_str(&calls(&message["tool_calls"])?);
                prompt.push_str(EOS);
            }
            _ => return Err(TokenizerRequestError::Rejected),
        }
        let next = merged.get(index + 1).and_then(|m| m["role"].as_str());
        if (next.is_none() || next == Some("assistant"))
            && (role == "user" || role == "developer" || (role == "system" && index > 0))
        {
            prompt.push_str(ASSISTANT);
            prompt.push_str(
                if thinking && (!drop_thinking || last_user.is_some_and(|last| index >= last)) {
                    "<think>"
                } else {
                    "</think>"
                },
            );
        }
    }
    Ok(prompt)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_pinned_vllm_encoder() {
        let cases: Value = serde_json::from_str(include_str!(
            "../../test/fixtures/deepseek-v41-prompts.json"
        ))
        .unwrap();
        for case in cases["cases"].as_array().unwrap() {
            let request: ChatCompletionRequest =
                serde_json::from_value(case["request"].clone()).unwrap();
            assert_eq!(
                render(&request).unwrap(),
                case["prompt"].as_str().unwrap(),
                "{}",
                case["name"]
            );
        }
    }

    #[test]
    fn rejects_unsupported_effort_and_image_input() {
        for request in [
            json!({"model":"test", "messages":[{"role":"user","content":"Hello"}], "reasoning_effort":"medium"}),
            json!({"model":"test", "messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"https://example.com/image.png"}}]}]}),
        ] {
            let request: ChatCompletionRequest = serde_json::from_value(request).unwrap();
            assert!(render(&request).is_err());
        }
    }
}
