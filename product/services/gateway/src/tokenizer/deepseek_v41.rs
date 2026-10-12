//! Text prompt encoding for the pinned vLLM DeepSeek V4.1 release.
//! Adapted from vLLM's Apache-2.0 deepseek_v41_encoding.py.
use std::collections::HashMap;

use serde_json::{json, Map, Value};

use super::{
    deepseek::{ASSISTANT, BOS, EOS, USER},
    InferenceRequest, TokenizerRequestError,
};

const SYSTEM: &str = "<｜System｜>";

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

struct ToolCall<'a> {
    name: &'a str,
    arguments: Map<String, Value>,
}

impl<'a> ToolCall<'a> {
    fn parse_all(value: &'a Value) -> Result<Vec<Self>, TokenizerRequestError> {
        match value {
            Value::Null => Ok(Vec::new()),
            Value::Array(calls) => calls.iter().map(Self::parse).collect(),
            _ => Err(TokenizerRequestError::InvalidInput),
        }
    }

    fn parse(call: &'a Value) -> Result<Self, TokenizerRequestError> {
        let function = &call["function"];
        let name = function["name"]
            .as_str()
            .ok_or(TokenizerRequestError::InvalidInput)?;

        // The chat endpoint runs chat_utils._postprocess_messages before the
        // DeepSeek encoder. It parses arguments once and replaces malformed or
        // non-object history with {} so an incomplete tool call does not poison
        // every later turn. Counting the encoder's raw-string fallback here
        // disagrees with the prompt actually served by vLLM.
        let arguments = match &function["arguments"] {
            Value::Object(arguments) => arguments.clone(),
            Value::String(text) => serde_json::from_str::<Value>(text)
                .ok()
                .and_then(|value| value.as_object().cloned())
                .unwrap_or_default(),
            _ => Map::new(),
        };

        Ok(Self { name, arguments })
    }

    fn render(&self) -> String {
        let parameters = self
            .arguments
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

        format!(
            "<｜DSML｜ invoke name=\"{}\">\n{parameters}\n</｜DSML｜ invoke>",
            self.name
        )
    }
}

fn render_calls(calls: &[ToolCall<'_>]) -> String {
    if calls.is_empty() {
        return String::new();
    }

    let rendered = calls
        .iter()
        .map(ToolCall::render)
        .collect::<Vec<_>>()
        .join("\n");

    format!("\n\n<｜DSML｜ calls>\n{rendered}\n</｜DSML｜ calls>")
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

enum Turn<'a> {
    System {
        content: String,
        tools: Option<&'a [Value]>,
    },
    Developer(String),
    User(Vec<Block>),
    Assistant {
        reasoning: &'a Value,
        content: String,
        calls: Vec<ToolCall<'a>>,
    },
}

enum Block {
    Text(String),
    ToolResult { order: usize, content: String },
}

struct RenderOptions<'a> {
    thinking: bool,
    budget: u64,
    drop_thinking: bool,
    tools: Option<&'a [Value]>,
}

impl<'a> RenderOptions<'a> {
    fn new(request: &'a InferenceRequest) -> Result<Self, TokenizerRequestError> {
        let kwargs = request.parameters.get("chat_template_kwargs");
        let option = |name: &str| kwargs.and_then(|v| v.get(name));

        for (name, param) in [
            ("thinking", "chat_template_kwargs.thinking"),
            ("enable_thinking", "chat_template_kwargs.enable_thinking"),
        ] {
            if option(name).is_some_and(|value| !value.is_boolean() && !value.is_null()) {
                return Err(TokenizerRequestError::InvalidParameter(param));
            }
        }

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
            .map(Vec::as_slice)
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

    reject_encoder_controls(&request.messages)?;
    let mut turns = parse_turns(&request.messages, options.tools)?;
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

/// Consecutive user and tool messages fold into one user turn. A tool result
/// carries the position of its call in the preceding assistant turn. The
/// encoder renders tool definitions inside the first system turn, so a request
/// with tools and no system message gets an empty one.
fn parse_turns<'a>(
    messages: &'a [Value],
    tools: Option<&'a [Value]>,
) -> Result<Vec<Turn<'a>>, TokenizerRequestError> {
    let mut turns = Vec::with_capacity(messages.len() + 1);
    let mut tools = tools;
    if tools.is_some() && !messages.iter().any(|m| m["role"] == "system") {
        turns.push(Turn::System {
            content: String::new(),
            tools: tools.take(),
        });
    }

    let mut call_order = HashMap::new();
    for message in messages {
        let role = message["role"]
            .as_str()
            .ok_or(TokenizerRequestError::InvalidInput)?;
        let text = || content(&message["content"]);

        match role {
            "system" => turns.push(Turn::System {
                content: text()?,
                tools: tools.take(),
            }),
            "developer" => turns.push(Turn::Developer(text()?)),
            "assistant" => {
                let content = text()?;
                if let Some(calls) = message["tool_calls"].as_array() {
                    call_order = calls
                        .iter()
                        .enumerate()
                        .filter_map(|(index, call)| Some((call["id"].as_str()?, index)))
                        .collect();
                }

                turns.push(Turn::Assistant {
                    reasoning: message
                        .get("reasoning")
                        .unwrap_or(&message["reasoning_content"]),
                    content,
                    calls: ToolCall::parse_all(&message["tool_calls"])?,
                });
            }
            "user" => push_block(&mut turns, Block::Text(text()?)),
            "tool" => {
                let call_id = message["tool_call_id"].as_str().unwrap_or("");
                let order = call_order.get(call_id).copied().unwrap_or(0);
                push_block(
                    &mut turns,
                    Block::ToolResult {
                        order,
                        content: text()?,
                    },
                );
            }
            _ => return Err(TokenizerRequestError::Rejected),
        }
    }

    Ok(turns)
}

fn push_block(turns: &mut Vec<Turn<'_>>, block: Block) {
    if let Some(Turn::User(blocks)) = turns.last_mut() {
        blocks.push(block);
        return;
    }

    turns.push(Turn::User(vec![block]));
}

/// Matches the pinned runtime's history pruning: developer turns before the
/// last user turn are dropped.
fn prune_developer_turns(turns: Vec<Turn<'_>>) -> Vec<Turn<'_>> {
    let last_user = last_user_index(&turns);

    turns
        .into_iter()
        .enumerate()
        .filter_map(|(index, turn)| {
            let pruned =
                matches!(turn, Turn::Developer(_)) && last_user.is_some_and(|last| index < last);
            (!pruned).then_some(turn)
        })
        .collect()
}

/// A system message acts as a user turn when it follows another turn, or when
/// it is the whole conversation, so a system-only request still gets a reply.
fn system_acts_as_user(index: usize, turns: &[Turn<'_>]) -> bool {
    index > 0 || turns.len() == 1
}

/// The last user turn, including a system message that acts as one.
fn last_user_index(turns: &[Turn<'_>]) -> Option<usize> {
    turns
        .iter()
        .enumerate()
        .rfind(|(index, turn)| match turn {
            Turn::User(_) => true,
            Turn::System { .. } => system_acts_as_user(*index, turns),
            Turn::Developer(_) | Turn::Assistant { .. } => false,
        })
        .map(|(index, _)| index)
}

fn encode(turns: &[Turn<'_>], options: &RenderOptions) -> Result<String, TokenizerRequestError> {
    let RenderOptions {
        thinking,
        budget,
        drop_thinking,
        ..
    } = *options;
    let last_user = last_user_index(turns);
    let mut prompt = String::from(BOS);

    for (index, turn) in turns.iter().enumerate() {
        if index == 0 && (thinking || matches!(turn, Turn::System { .. })) {
            prompt.push_str(SYSTEM);
        }

        if index == 0 && thinking {
            prompt.push_str(&format!("Reasoning Effort: {budget} (range 1-100, the higher the value, the more thorough the reasoning)\n\n"));
        }

        match turn {
            Turn::System { content, tools } => {
                if index > 0 {
                    prompt.push_str(SYSTEM);
                }

                encode_instructions(&mut prompt, content, *tools)?;
            }
            Turn::Developer(content) => {
                if content.is_empty() {
                    return Err(TokenizerRequestError::Rejected);
                }

                prompt.push_str(USER);
                encode_instructions(&mut prompt, content, None)?;
            }
            Turn::User(blocks) => encode_user(&mut prompt, blocks),
            Turn::Assistant {
                reasoning,
                content: text,
                calls,
            } => {
                if thinking && (!drop_thinking || last_user.is_none_or(|last| index > last)) {
                    prompt.push_str(&content(reasoning)?);
                    prompt.push_str("</think>");
                }

                prompt.push_str(text);
                prompt.push_str(&render_calls(calls));
                prompt.push_str(EOS);
            }
        }

        // A turn that expects a reply opens the assistant turn, with reasoning
        // open only where the runtime keeps it.
        let expects_reply = match turn {
            Turn::User(_) | Turn::Developer(_) => true,
            Turn::System { .. } => system_acts_as_user(index, turns),
            Turn::Assistant { .. } => false,
        };
        let next_is_reply = turns
            .get(index + 1)
            .is_none_or(|next| matches!(next, Turn::Assistant { .. }));
        if expects_reply && next_is_reply {
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
    content: &str,
    tools: Option<&[Value]>,
) -> Result<(), TokenizerRequestError> {
    prompt.push_str(content);

    if let Some(tools) = tools {
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
fn encode_user(prompt: &mut String, blocks: &[Block]) {
    let mut results: Vec<(usize, &str)> = blocks
        .iter()
        .filter_map(|block| match block {
            Block::ToolResult { order, content } => Some((*order, content.as_str())),
            Block::Text(_) => None,
        })
        .collect();
    results.sort_by_key(|(order, _)| *order);

    let positions = blocks
        .iter()
        .enumerate()
        .filter(|(_, block)| matches!(block, Block::ToolResult { .. }))
        .map(|(position, _)| position);
    let mut parts: Vec<String> = blocks
        .iter()
        .map(|block| match block {
            Block::Text(text) => text.clone(),
            Block::ToolResult { .. } => String::new(),
        })
        .collect();
    for (position, (_, result)) in positions.zip(results) {
        parts[position] = format!("<tool_result>{result}</tool_result>");
    }

    prompt.push_str(USER);
    prompt.push_str(&parts.join("\n\n"));
}

#[cfg(test)]
mod tests {
    use super::*;

    const THINKING: &str = "<｜begin▁of▁sentence｜><｜System｜>Reasoning Effort: 50 (range 1-100, the higher the value, the more thorough the reasoning)\n\n";

    fn thinking(rest: &str) -> String {
        format!("{THINKING}{rest}")
    }

    fn rendered(calls: &Value) -> String {
        render_calls(&ToolCall::parse_all(calls).unwrap())
    }

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
            assert_eq!(rendered(&call(arguments.clone())), expected, "{arguments}");
        }
        assert!(rendered(&call(json!("{\"cmd\":\"ls\"}")))
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
    fn rejects_malformed_tool_calls_and_thinking_flags() {
        let request = |message: Value, kwargs: Value| -> InferenceRequest {
            serde_json::from_value(json!({
                "model": "test",
                "chat_template_kwargs": kwargs,
                "messages": [{"role": "user", "content": "Go"}, message],
            }))
            .unwrap()
        };
        let assistant = |tool_calls: Value| json!({"role": "assistant", "content": "A", "tool_calls": tool_calls});

        for tool_calls in [json!({"id": "a"}), json!("a"), json!(1)] {
            assert_eq!(
                render(&request(assistant(tool_calls.clone()), json!({}))),
                Err(TokenizerRequestError::InvalidInput),
                "{tool_calls}"
            );
        }
        assert!(render(&request(assistant(Value::Null), json!({}))).is_ok());

        for (name, param) in [
            ("thinking", "chat_template_kwargs.thinking"),
            ("enable_thinking", "chat_template_kwargs.enable_thinking"),
        ] {
            for value in [json!("yes"), json!(1)] {
                assert_eq!(
                    render(&request(assistant(json!([])), json!({name: value}))),
                    Err(TokenizerRequestError::InvalidParameter(param)),
                    "{name}: {value}"
                );
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
    fn rejects_image_input() {
        let request: InferenceRequest = serde_json::from_value(json!({
            "model": "test",
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.com/image.png"}}]}],
        }))
        .unwrap();

        assert_eq!(render(&request), Err(TokenizerRequestError::Rejected));
    }

    fn characterization_cases() -> Vec<(&'static str, Value, String)> {
        let call = |id: &str, name: &str| json!({"id": id, "type": "function", "function": {"name": name, "arguments": "{}"}});
        vec![
            ("drop_thinking false keeps earlier reasoning", json!({
                "model": "test",
                "chat_template_kwargs": {"drop_thinking": false},
                "messages": [
                    {"role": "user", "content": "One"},
                    {"role": "assistant", "content": "A", "reasoning_content": "think A"},
                    {"role": "user", "content": "Two"},
                ],
            }), thinking("<｜User｜>One<｜Assistant｜><think>think A</think>A<｜end▁of▁sentence｜><｜User｜>Two<｜Assistant｜><think>")),
            ("reasoning after the last user turn is kept", json!({
                "model": "test",
                "messages": [
                    {"role": "user", "content": "One"},
                    {"role": "assistant", "content": "A", "reasoning_content": "think A"},
                    {"role": "user", "content": "Two"},
                    {"role": "assistant", "content": "B", "reasoning_content": "think B"},
                ],
            }), thinking("<｜User｜>One<｜Assistant｜></think>A<｜end▁of▁sentence｜><｜User｜>Two<｜Assistant｜><think>think B</think>B<｜end▁of▁sentence｜>")),
            ("developer turns before the last user turn are pruned", json!({
                "model": "test",
                "messages": [
                    {"role": "developer", "content": "Early rule"},
                    {"role": "user", "content": "One"},
                    {"role": "assistant", "content": "A"},
                    {"role": "developer", "content": "Late rule"},
                    {"role": "user", "content": "Two"},
                ],
            }), thinking("<｜User｜>One<｜Assistant｜></think>A<｜end▁of▁sentence｜><｜User｜>Two<｜Assistant｜><think>")),
            ("a later system message counts as a user turn", json!({
                "model": "test",
                "messages": [
                    {"role": "system", "content": "First"},
                    {"role": "user", "content": "One"},
                    {"role": "assistant", "content": "A", "reasoning_content": "think A"},
                    {"role": "system", "content": "Second"},
                ],
            }), thinking("First<｜User｜>One<｜Assistant｜></think>A<｜end▁of▁sentence｜><｜System｜>Second<｜Assistant｜><think>")),
            ("a system-only conversation opens the assistant turn", json!({
                "model": "test",
                "messages": [{"role": "system", "content": "Write a greeting."}],
            }), thinking("Write a greeting.<｜Assistant｜><think>")),
            ("a system-only conversation without thinking opens the assistant turn", json!({
                "model": "test",
                "reasoning_effort": "none",
                "messages": [{"role": "system", "content": "Write a greeting."}],
            }), "<｜begin▁of▁sentence｜><｜System｜>Write a greeting.<｜Assistant｜></think>".to_owned()),
            ("a leading system message followed by an assistant turn expects no reply", json!({
                "model": "test",
                "messages": [
                    {"role": "system", "content": "Rules"},
                    {"role": "assistant", "content": "A"},
                ],
            }), thinking("Rules</think>A<｜end▁of▁sentence｜>")),
            ("tool results follow call order", json!({
                "model": "test",
                "messages": [
                    {"role": "user", "content": "Go"},
                    {"role": "assistant", "content": "", "tool_calls": [call("a", "first"), call("b", "second")]},
                    {"role": "tool", "tool_call_id": "b", "content": "result b"},
                    {"role": "user", "content": "between"},
                    {"role": "tool", "tool_call_id": "a", "content": "result a"},
                ],
            }), thinking("<｜User｜>Go<｜Assistant｜></think>\n\n<｜DSML｜ calls>\n<｜DSML｜ invoke name=\"first\">\n\n</｜DSML｜ invoke>\n<｜DSML｜ invoke name=\"second\">\n\n</｜DSML｜ invoke>\n</｜DSML｜ calls><｜end▁of▁sentence｜><｜User｜><tool_result>result a</tool_result>\n\nbetween\n\n<tool_result>result b</tool_result><｜Assistant｜><think>")),
            ("an unmatched tool call id sorts first", json!({
                "model": "test",
                "messages": [
                    {"role": "user", "content": "Go"},
                    {"role": "assistant", "content": "", "tool_calls": [call("a", "first"), call("b", "second")]},
                    {"role": "tool", "tool_call_id": "b", "content": "result b"},
                    {"role": "tool", "tool_call_id": "missing", "content": "result missing"},
                ],
            }), thinking("<｜User｜>Go<｜Assistant｜></think>\n\n<｜DSML｜ calls>\n<｜DSML｜ invoke name=\"first\">\n\n</｜DSML｜ invoke>\n<｜DSML｜ invoke name=\"second\">\n\n</｜DSML｜ invoke>\n</｜DSML｜ calls><｜end▁of▁sentence｜><｜User｜><tool_result>result missing</tool_result>\n\n<tool_result>result b</tool_result><｜Assistant｜><think>")),
            ("the reasoning alias overrides reasoning_content", json!({
                "model": "test",
                "messages": [
                    {"role": "user", "content": "One"},
                    {"role": "assistant", "content": "A", "reasoning_content": "old", "reasoning": "new"},
                ],
            }), thinking("<｜User｜>One<｜Assistant｜><think>new</think>A<｜end▁of▁sentence｜>")),
            ("array content joins with a blank line", json!({
                "model": "test",
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]},
                ],
            }), thinking("<｜User｜>first\n\nsecond<｜Assistant｜><think>")),
            ("tools without a system message add an empty system turn", json!({
                "model": "test",
                "tools": [{"type": "function", "function": {"name": "weather", "parameters": {"type": "object"}}}],
                "messages": [{"role": "user", "content": "Weather?"}],
            }), thinking("\n\n## Tools\n\nYou have access to a set of tools to help answer the user's question. You can invoke tools by writing a \"<｜DSML｜ calls>\" block like the following:\n\n<｜DSML｜ calls>\n<｜DSML｜ invoke name=\"$TOOL_NAME\">\n<｜DSML｜ parameter name=\"$PARAMETER_NAME\" string=\"true|false\">$PARAMETER_VALUE</｜DSML｜ parameter>\n...\n</｜DSML｜ invoke>\n<｜DSML｜ invoke name=\"$TOOL_NAME2\">\n...\n</｜DSML｜ invoke>\n</｜DSML｜ calls>\n\nString parameters should be specified as is and set `string=\"true\"`. For all other types (numbers, booleans, arrays, objects), pass the value in JSON format and set `string=\"false\"`.\n\nIf thinking_mode is enabled (triggered by <think>), you MUST output your complete reasoning inside <think>...</think> BEFORE any tool calls or final response.\n\nOtherwise, output directly after </think> with tool calls or final response.\n\n### Available Tool Schemas\n\n{\"name\": \"weather\", \"description\": null, \"parameters\": {\"type\": \"object\"}}\n\nYou MUST strictly follow the above defined tool name and parameter schemas to invoke tool calls.\n<｜User｜>Weather?<｜Assistant｜><think>")),
            ("reasoning effort none disables thinking", json!({
                "model": "test",
                "reasoning_effort": "none",
                "messages": [
                    {"role": "user", "content": "One"},
                    {"role": "assistant", "content": "A", "reasoning_content": "think A"},
                    {"role": "user", "content": "Two"},
                ],
            }), "<｜begin▁of▁sentence｜><｜User｜>One<｜Assistant｜></think>A<｜end▁of▁sentence｜><｜User｜>Two<｜Assistant｜></think>".to_owned()),
        ]
    }

    #[test]
    fn characterizes_branches_outside_the_pinned_vllm_cases() {
        for (name, request, expected) in characterization_cases() {
            let request: InferenceRequest = serde_json::from_value(request).unwrap();

            assert_eq!(render(&request).unwrap(), expected, "{name}");
        }
    }
}
