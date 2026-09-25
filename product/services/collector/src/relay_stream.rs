use std::collections::BTreeMap;

use serde_json::{json, Value};

use crate::{record::RecordError, relay::invalid};

type Result<T> = std::result::Result<T, RecordError>;

pub fn rebuild(protocol: &str, body: &str) -> Result<Value> {
    let normalized = body.replace("\r\n", "\n").replace('\r', "\n");
    let mut events = Vec::new();
    for frame in normalized.split("\n\n") {
        let data = frame
            .lines()
            .filter_map(|line| {
                line.strip_prefix("data:")
                    .map(|data| data.strip_prefix(' ').unwrap_or(data))
            })
            .collect::<Vec<_>>()
            .join("\n");
        if data.is_empty() || data == "[DONE]" {
            continue;
        }

        let event: Value = serde_json::from_str(&data).map_err(|_| invalid("invalid SSE data"))?;
        if !event.is_object() {
            return Err(invalid("SSE data must be an object"));
        }
        events.push(event);
    }

    if events.is_empty() {
        return Err(invalid("empty event stream"));
    }

    match protocol {
        "anthropic.messages" => messages(events),
        "openai.chat" => chat(events),
        "openai.responses" => responses(events),
        _ => Err(invalid("unsupported streaming protocol")),
    }
}

fn index(event: &Value, key: &str) -> Result<u64> {
    event[key]
        .as_u64()
        .ok_or_else(|| invalid("missing stream index"))
}

fn append(target: &mut Value, delta: &Value) -> Result<()> {
    let text = delta
        .as_str()
        .ok_or_else(|| invalid("delta must be a string"))?;
    if target.is_null() {
        *target = Value::String(String::new());
    }
    let Value::String(current) = target else {
        return Err(invalid("delta target must be a string"));
    };
    current.push_str(text);

    Ok(())
}

fn merge(target: &mut Value, fields: &Value) -> Result<()> {
    let fields = fields
        .as_object()
        .ok_or_else(|| invalid("expected an object"))?;
    let target = target
        .as_object_mut()
        .ok_or_else(|| invalid("missing stream start"))?;
    target.extend(fields.clone());

    Ok(())
}

fn messages(events: Vec<Value>) -> Result<Value> {
    let mut message = Value::Null;
    let mut blocks = BTreeMap::new();
    let mut inputs: BTreeMap<u64, String> = BTreeMap::new();
    for event in events {
        match event["type"].as_str() {
            Some("message_start") => {
                if !event["message"].is_object() {
                    return Err(invalid("invalid message start"));
                }
                message = event["message"].clone();
            }
            Some("content_block_start") => {
                if !event["content_block"].is_object() {
                    return Err(invalid("invalid content block"));
                }
                blocks.insert(index(&event, "index")?, event["content_block"].clone());
            }
            Some("content_block_delta") => {
                let position = index(&event, "index")?;
                let block = blocks
                    .get_mut(&position)
                    .ok_or_else(|| invalid("missing content block"))?;
                let delta = &event["delta"];
                match delta["type"].as_str() {
                    Some("text_delta") => append(&mut block["text"], &delta["text"])?,
                    Some("thinking_delta") => append(&mut block["thinking"], &delta["thinking"])?,
                    Some("signature_delta") => {
                        append(&mut block["signature"], &delta["signature"])?
                    }
                    Some("input_json_delta") => inputs.entry(position).or_default().push_str(
                        delta["partial_json"]
                            .as_str()
                            .ok_or_else(|| invalid("invalid tool input delta"))?,
                    ),
                    Some("citations_delta") => {
                        if block["citations"].is_null() {
                            block["citations"] = json!([]);
                        }
                        block["citations"]
                            .as_array_mut()
                            .ok_or_else(|| invalid("invalid citations"))?
                            .push(delta["citation"].clone());
                    }
                    _ => return Err(invalid("unsupported message delta")),
                }
            }
            Some("message_delta") => {
                merge(&mut message, &event["delta"])?;
                if let Some(usage) = event.get("usage") {
                    if message["usage"].is_null() {
                        message["usage"] = json!({});
                    }
                    merge(&mut message["usage"], usage)?;
                }
            }
            Some("error") => {
                if message.is_null() {
                    return Ok(event);
                }
                message["error"] = event["error"].clone();
            }
            Some("ping" | "content_block_stop" | "message_stop") => {}
            _ => return Err(invalid("unsupported message event")),
        }
    }
    if !message.is_object() {
        return Err(invalid("missing message start"));
    }
    for (position, input) in inputs {
        blocks.get_mut(&position).unwrap()["input"] =
            serde_json::from_str(&input).map_err(|_| invalid("incomplete tool input"))?;
    }
    message["content"] = Value::Array(blocks.into_values().collect());

    Ok(message)
}

fn chat(events: Vec<Value>) -> Result<Value> {
    let mut response = json!({"object": "chat.completion"});
    let mut choices: BTreeMap<u64, Value> = BTreeMap::new();
    let mut tools: BTreeMap<(u64, u64), Value> = BTreeMap::new();
    for event in events {
        if event.get("error").is_some() {
            response["error"] = event["error"].clone();
            continue;
        }
        for field in [
            "id",
            "created",
            "model",
            "system_fingerprint",
            "service_tier",
            "usage",
        ] {
            if let Some(value) = event.get(field).filter(|v| !v.is_null()) {
                response[field] = value.clone();
            }
        }
        for delta in event["choices"]
            .as_array()
            .ok_or_else(|| invalid("missing chat choices"))?
        {
            let position = index(delta, "index")?;
            let choice = choices.entry(position).or_insert_with(|| json!({
                "index": position, "message": {"role": "assistant", "content": null}, "finish_reason": null
            }));
            if !delta["finish_reason"].is_null() {
                choice["finish_reason"] = delta["finish_reason"].clone();
            }
            if let Some(logprobs) = delta.get("logprobs").filter(|v| !v.is_null()) {
                if choice["logprobs"].is_null() {
                    choice["logprobs"] = json!({});
                }
                for key in ["content", "refusal"] {
                    if let Some(values) = logprobs[key].as_array() {
                        if choice["logprobs"][key].is_null() {
                            choice["logprobs"][key] = json!([]);
                        }
                        choice["logprobs"][key]
                            .as_array_mut()
                            .unwrap()
                            .extend(values.clone());
                    }
                }
            }
            let fields = delta["delta"]
                .as_object()
                .ok_or_else(|| invalid("missing chat delta"))?;
            for (field, value) in fields {
                if value.is_null() {
                    continue;
                }
                match field.as_str() {
                    "content" | "refusal" | "reasoning_content" | "reasoning" => {
                        append(&mut choice["message"][field], value)?
                    }
                    "tool_calls" => {
                        for tool in value
                            .as_array()
                            .ok_or_else(|| invalid("invalid tool calls"))?
                        {
                            let key = (position, index(tool, "index")?);
                            let target =
                                tools.entry(key).or_insert_with(|| json!({"function": {}}));
                            for key in ["id", "type"] {
                                if let Some(value) = tool.get(key) {
                                    target[key] = value.clone();
                                }
                            }
                            if let Some(function) = tool.get("function") {
                                for key in ["name", "arguments"] {
                                    if let Some(value) = function.get(key) {
                                        append(&mut target["function"][key], value)?;
                                    }
                                }
                            }
                        }
                    }
                    "function_call" => {
                        if choice["message"][field].is_null() {
                            choice["message"][field] = json!({});
                        }
                        for key in ["name", "arguments"] {
                            if let Some(value) = value.get(key) {
                                append(&mut choice["message"][field][key], value)?;
                            }
                        }
                    }
                    "role" => choice["message"][field] = value.clone(),
                    _ => return Err(invalid("unsupported chat delta")),
                }
            }
        }
    }
    for ((position, _), tool) in tools {
        let message = &mut choices.get_mut(&position).unwrap()["message"];
        if message["tool_calls"].is_null() {
            message["tool_calls"] = json!([]);
        }
        message["tool_calls"].as_array_mut().unwrap().push(tool);
    }
    response["choices"] = Value::Array(choices.into_values().collect());

    Ok(response)
}

fn responses(events: Vec<Value>) -> Result<Value> {
    if let Some(response) = events.iter().rev().find(|event| {
        matches!(
            event["type"].as_str(),
            Some("response.completed" | "response.failed" | "response.incomplete")
        )
    }) {
        return response
            .get("response")
            .filter(|value| value.is_object())
            .cloned()
            .ok_or_else(|| invalid("missing terminal response"));
    }

    let mut response = Value::Null;
    let mut items: BTreeMap<u64, Value> = BTreeMap::new();
    let mut parts: BTreeMap<(u64, &str, u64), Value> = BTreeMap::new();
    for event in events {
        match event["type"].as_str() {
            Some("response.created" | "response.in_progress") => {
                if !event["response"].is_object() {
                    return Err(invalid("invalid response start"));
                }
                response = event["response"].clone();
            }
            Some("response.output_item.added" | "response.output_item.done") => {
                if !event["item"].is_object() {
                    return Err(invalid("invalid output item"));
                }
                let position = index(&event, "output_index")?;
                items.insert(position, event["item"].clone());
                if event["type"] == "response.output_item.done" {
                    parts.retain(|(item, _, _), _| *item != position);
                }
            }
            Some(
                "response.content_part.added"
                | "response.content_part.done"
                | "response.reasoning_summary_part.added"
                | "response.reasoning_summary_part.done",
            ) => {
                if !event["part"].is_object() {
                    return Err(invalid("invalid content part"));
                }
                parts.insert(response_part_key(&event)?, event["part"].clone());
            }
            Some(
                "response.output_text.delta"
                | "response.refusal.delta"
                | "response.output_text.done"
                | "response.refusal.done"
                | "response.reasoning_summary_text.delta"
                | "response.reasoning_summary_text.done",
            ) => {
                let part = parts
                    .get_mut(&response_part_key(&event)?)
                    .ok_or_else(|| invalid("missing response part"))?;
                let kind = event["type"].as_str().unwrap();
                let field = if kind.starts_with("response.refusal.") {
                    "refusal"
                } else {
                    "text"
                };
                if kind.ends_with(".delta") {
                    append(&mut part[field], &event["delta"])?;
                } else {
                    part[field] = event[field].clone();
                }
            }
            Some("response.output_text.annotation.added") => {
                let part = parts
                    .get_mut(&response_part_key(&event)?)
                    .ok_or_else(|| invalid("missing response part"))?;
                if part["annotations"].is_null() {
                    part["annotations"] = json!([]);
                }
                part["annotations"]
                    .as_array_mut()
                    .ok_or_else(|| invalid("invalid annotations"))?
                    .push(event["annotation"].clone());
            }
            Some(
                "response.function_call_arguments.delta" | "response.function_call_arguments.done",
            ) => {
                let item = items
                    .get_mut(&index(&event, "output_index")?)
                    .ok_or_else(|| invalid("missing function item"))?;
                if event["type"] == "response.function_call_arguments.delta" {
                    append(&mut item["arguments"], &event["delta"])?;
                } else {
                    item["arguments"] = event["arguments"].clone();
                }
            }
            Some("error") => {
                if response.is_null() {
                    return Ok(event);
                }
                response["error"] = event.clone();
            }
            _ => return Err(invalid("unsupported partial response event")),
        }
    }
    if !response.is_object() {
        return Err(invalid("missing response start"));
    }
    let mut contents: BTreeMap<(u64, &str), Vec<Value>> = BTreeMap::new();
    for ((item, field, _), part) in parts {
        contents.entry((item, field)).or_default().push(part);
    }
    for ((position, field), content) in contents {
        let item = items
            .get_mut(&position)
            .ok_or_else(|| invalid("missing output item"))?;
        item[field] = Value::Array(content);
    }
    response["output"] = Value::Array(items.into_values().collect());

    Ok(response)
}

fn response_part_key(event: &Value) -> Result<(u64, &'static str, u64)> {
    let summary = event["type"]
        .as_str()
        .is_some_and(|kind| kind.starts_with("response.reasoning_summary_"));
    let (field, position) = if summary {
        ("summary", "summary_index")
    } else {
        ("content", "content_index")
    };

    Ok((
        index(event, "output_index")?,
        field,
        index(event, position)?,
    ))
}
