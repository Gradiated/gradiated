//! Text prompt encoding for the pinned vLLM DeepSeek V4.1 release.
//! Adapted from vLLM's Apache-2.0 deepseek_v41_encoding.py.
use std::collections::HashMap;

use serde_json::{json, Value};

use super::{InferenceRequest, TokenizerRequestError};

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
        // The chat endpoint runs chat_utils._postprocess_messages before the
        // DeepSeek encoder. It parses arguments once and replaces malformed or
        // non-object history with {} so an incomplete tool call does not poison
        // every later turn. Counting the encoder's raw-string fallback here
        // disagrees with the prompt actually served by vLLM.
        let args = match &function["arguments"] {
            Value::Object(args) => args.clone(),
            Value::String(text) => serde_json::from_str::<Value>(text)
                .ok()
                .and_then(|value| value.as_object().cloned())
                .unwrap_or_default(),
            _ => Default::default(),
        };
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

/// How the prompt treats reasoning, taken from the request's template options.
struct RenderOptions<'a> {
    thinking: bool,
    budget: u64,
    drop_thinking: bool,
    tools: Option<&'a Vec<Value>>,
}

impl<'a> RenderOptions<'a> {
    fn new(request: &'a InferenceRequest) -> Result<Self, TokenizerRequestError> {
        let kwargs = request.parameters.get("chat_template_kwargs");
        let option = |name: &str| kwargs.and_then(|v| v.get(name));

        let mut thinking = match (option("thinking"), option("enable_thinking")) {
            (None, None) => true,
            (a, b) => {
                a.and_then(Value::as_bool).unwrap_or(false)
                    || b.and_then(Value::as_bool).unwrap_or(false)
            }
        };

        let (effort, effort_param) = match option("reasoning_effort") {
            Some(value) => (Some(value), "chat_template_kwargs.reasoning_effort"),
            None => (
                request.parameters.get("reasoning_effort"),
                "reasoning_effort",
            ),
        };
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
                _ => return Err(TokenizerRequestError::InvalidParameter(effort_param)),
            },
            Some(value) => value
                .as_u64()
                .filter(|n| (1..=100).contains(n))
                .ok_or(TokenizerRequestError::InvalidParameter(effort_param))?,
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

        Ok(Self {
            thinking,
            budget,
            drop_thinking,
            tools,
        })
    }
}

pub(super) fn render(request: &InferenceRequest) -> Result<String, TokenizerRequestError> {
    let options = RenderOptions::new(request)?;

    let mut messages = request.messages.clone();
    reject_encoder_controls(&messages)?;
    if let Some(tools) = options.tools {
        attach_tools(&mut messages, tools);
    }

    let mut turns = merge_turns(messages)?;
    if options.thinking && options.drop_thinking {
        turns = prune_developer_turns(turns);
    }

    encode(&turns, &options)
}

/// These are internal encoder controls, not OpenAI message fields.
fn reject_encoder_controls(messages: &[Value]) -> Result<(), TokenizerRequestError> {
    const CONTROLS: [&str; 5] = [
        "task",
        "wo_eos",
        "content_blocks",
        "response_format",
        "tools",
    ];

    let controlled = messages
        .iter()
        .any(|message| CONTROLS.iter().any(|key| message.get(key).is_some()));
    if controlled {
        return Err(TokenizerRequestError::Rejected);
    }

    Ok(())
}

/// The encoder renders tool definitions inside the system turn, so a request
/// with tools and no system message gets an empty one.
fn attach_tools(messages: &mut Vec<Value>, tools: &[Value]) {
    if !messages.iter().any(|m| m["role"] == "system") {
        messages.insert(0, json!({"role":"system", "content":""}));
    }

    if let Some(system) = messages.iter_mut().find(|m| m["role"] == "system") {
        system["tools"] = json!(tools);
    }
}

/// Normalizes each message and folds consecutive user and tool messages into
/// one user turn of blocks. A tool result carries the position of its call in
/// the preceding assistant turn.
fn merge_turns(messages: Vec<Value>) -> Result<Vec<Value>, TokenizerRequestError> {
    let mut merged: Vec<Value> = Vec::new();
    let mut call_order = HashMap::new();

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

        let block = match role.as_str() {
            "tool" => {
                let call_id = message["tool_call_id"].as_str().unwrap_or("");
                let order = call_order.get(call_id).copied().unwrap_or(0);
                json!({"type":"tool_result", "content":message["content"], "order":order})
            }
            "user" => json!({"type":"text", "content":message["content"]}),
            _ => {
                merged.push(message);
                continue;
            }
        };

        match merged.last_mut().filter(|m| m["role"] == "user") {
            Some(last) => last["blocks"]
                .as_array_mut()
                .ok_or(TokenizerRequestError::InvalidInput)?
                .push(block),
            None => merged.push(json!({"role":"user", "blocks":[block]})),
        }
    }

    Ok(merged)
}

/// Matches the pinned runtime's history pruning: developer turns before the
/// last user turn are dropped.
fn prune_developer_turns(turns: Vec<Value>) -> Vec<Value> {
    let last_user = last_user_index(&turns);

    turns
        .into_iter()
        .enumerate()
        .filter_map(|(i, m)| {
            (m["role"] != "developer" || last_user.is_none_or(|last| i >= last)).then_some(m)
        })
        .collect()
}

/// The last user turn, where a later system message also counts as one.
fn last_user_index(turns: &[Value]) -> Option<usize> {
    turns
        .iter()
        .enumerate()
        .rfind(|(i, m)| m["role"] == "user" || (*i > 0 && m["role"] == "system"))
        .map(|(i, _)| i)
}

fn encode(turns: &[Value], options: &RenderOptions) -> Result<String, TokenizerRequestError> {
    let RenderOptions {
        thinking,
        budget,
        drop_thinking,
        ..
    } = *options;
    let last_user = last_user_index(turns);
    let mut prompt = String::from(BOS);

    for (index, message) in turns.iter().enumerate() {
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
            "system" | "developer" => encode_instructions(&mut prompt, message, role, index)?,
            "user" => encode_user(&mut prompt, message)?,
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

        // A turn that expects a reply opens the assistant turn, with reasoning
        // open only where the runtime keeps it.
        let next = turns.get(index + 1).and_then(|m| m["role"].as_str());
        let expects_reply =
            role == "user" || role == "developer" || (role == "system" && index > 0);
        if (next.is_none() || next == Some("assistant")) && expects_reply {
            let reasoning_open =
                thinking && (!drop_thinking || last_user.is_some_and(|last| index >= last));
            prompt.push_str(ASSISTANT);
            prompt.push_str(if reasoning_open {
                "<think>"
            } else {
                "</think>"
            });
        }
    }

    Ok(prompt)
}

fn encode_instructions(
    prompt: &mut String,
    message: &Value,
    role: &str,
    index: usize,
) -> Result<(), TokenizerRequestError> {
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
        prompt
            .push_str(&include_str!("deepseek_v41_tools.txt").replace("{tool_schemas}", &schemas));
    }

    Ok(())
}

/// Tool results are rendered in the order of their calls, in the positions the
/// tool messages held among the turn's blocks.
fn encode_user(prompt: &mut String, message: &Value) -> Result<(), TokenizerRequestError> {
    let blocks = message["blocks"]
        .as_array()
        .ok_or(TokenizerRequestError::InvalidInput)?;

    let mut tool_blocks = blocks
        .iter()
        .filter(|b| b["type"] == "tool_result")
        .collect::<Vec<_>>();
    tool_blocks.sort_by_key(|b| b["order"].as_u64().unwrap_or(0));
    let mut results = tool_blocks.into_iter();

    let mut parts = Vec::with_capacity(blocks.len());
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

    prompt.push_str(USER);
    prompt.push_str(&parts.join("\n\n"));

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn incomplete_tool_history_matches_chat_endpoint_normalization() {
        let call = |arguments: Value| {
            json!([{
                "id": "call_1", "type": "function",
                "function": {"name": "shell", "arguments": arguments}
            }])
        };
        let expected = "\n\n<｜DSML｜ calls>\n<｜DSML｜ invoke name=\"shell\">\n\n</｜DSML｜ invoke>\n</｜DSML｜ calls>";
        for arguments in [
            json!("{\"cmd\": \""), // a truncated nine-character argument string
            json!(""),
            json!("null"),
            json!("[]"),
            json!("42"),
            json!("true"),
            Value::Null,
            json!("\"{\\\"cmd\\\":\\\"ls\\\"}\""), // parsed once, not twice
            json!("{}"),
            json!({}),
        ] {
            assert_eq!(
                calls(&call(arguments.clone())).unwrap(),
                expected,
                "{arguments}"
            );
        }
        assert!(calls(&call(json!("{\"cmd\":\"ls\"}")))
            .unwrap()
            .contains("name=\"cmd\" string=\"true\">ls</"));
    }

    #[test]
    fn invalid_reasoning_effort_identifies_the_parameter() {
        for effort in [json!("medium"), json!(0), json!(101), json!(true)] {
            for nested in [false, true] {
                let mut body = json!({
                    "model": "test",
                    "messages": [{"role": "user", "content": "hi there"}],
                });
                let param = if nested {
                    body["chat_template_kwargs"] = json!({"reasoning_effort": effort});
                    "chat_template_kwargs.reasoning_effort"
                } else {
                    body["reasoning_effort"] = effort.clone();
                    "reasoning_effort"
                };
                let request: InferenceRequest = serde_json::from_value(body).unwrap();
                let error = super::super::map_request_error(render(&request).unwrap_err());
                assert_eq!(error, crate::GatewayError::invalid_request(Some(param)));
            }
        }
    }

    #[test]
    fn responses_reasoning_effort_reaches_the_model_encoder() {
        for effort in ["medium", "high"] {
            let body = json!({
                "model": "deepseek/deepseek-v4.1-flash",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi there"}]}],
                "reasoning": {"effort": effort},
            });
            let translated = crate::protocol::Protocol::OpenAiResponses
                .translate_request(&body)
                .unwrap();
            let request = InferenceRequest::parse(&translated).unwrap();
            if effort == "medium" {
                assert_eq!(
                    super::super::map_request_error(render(&request).unwrap_err()),
                    crate::GatewayError::invalid_request(Some("reasoning_effort")),
                );
            } else {
                assert!(render(&request).unwrap().contains("Reasoning Effort: 50"));
            }
        }
    }

    #[test]
    fn matches_pinned_vllm_encoder() {
        let cases: Value = serde_json::from_str(include_str!(
            "../../test/fixtures/deepseek-v41-prompts.json"
        ))
        .unwrap();
        for case in cases["cases"].as_array().unwrap() {
            let request: InferenceRequest =
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
            let request: InferenceRequest = serde_json::from_value(request).unwrap();
            assert!(render(&request).is_err());
        }
    }
}
