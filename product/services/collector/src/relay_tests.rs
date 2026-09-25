use serde_json::{json, Value};
use uuid::Uuid;

use crate::{relay::normalize, relay_stream::rebuild, test_support::WORKSPACE};

pub fn relay(response: &str, provider: &str, path: &str, mime: &str) -> Value {
    json!({
        "schema": "gradiated.relay/1", "generation_id": Uuid::now_v7(),
        "workspace_id": WORKSPACE, "task": "relay-test", "trace_id": null,
        "session_id": "session", "provider": provider, "path": path,
        "retention_days": 90, "status": 200, "outcome": "complete",
        "completed_at": "2026-09-25T12:00:00Z", "request": "{\"model\":\"synthetic-model\"}",
        "response_content_type": mime, "response": response
    })
}

fn stream(events: &[Value]) -> String {
    events
        .iter()
        .map(|value| format!("data: {value}\n\n"))
        .collect()
}

#[test]
fn json_relays_derive_metadata_and_preserve_raw_bodies() {
    let response = json!({"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3,
        "prompt_tokens_details": {"cached_tokens": 4}, "completion_tokens_details": {"reasoning_tokens": 2}}});
    let input = relay(
        &response.to_string(),
        "openai",
        "/v1/chat/completions",
        "application/json",
    );
    let output: Value =
        serde_json::from_slice(&normalize(&serde_json::to_vec(&input).unwrap()).unwrap()).unwrap();
    assert_eq!(output["source"], "relay");
    assert_eq!(output["trainable"], false);
    assert_eq!(output["model"], "synthetic-model");
    assert_eq!(output["raw"]["response"], response);
    assert_eq!(
        output["usage"],
        json!({"input":12,"output":3,"reasoning":2,"cache_read":4})
    );
    assert_eq!(output["trace_id"], input["generation_id"]);
    assert_eq!(output["retention_days"], 90);
    assert!(output["canonical"].is_null());
    let id: Uuid = input["generation_id"].as_str().unwrap().parse().unwrap();
    let started: chrono::DateTime<chrono::Utc> =
        serde_json::from_value(output["started_at"].clone()).unwrap();
    let (seconds, nanos) = id.get_timestamp().unwrap().to_unix();
    assert_eq!(
        started.timestamp_millis(),
        seconds as i64 * 1000 + i64::from(nanos / 1_000_000)
    );
}

#[test]
fn chat_rebuilds_multiple_choices_tools_reasoning_and_usage() {
    let body = stream(&[
        json!({"id":"chat-1","model":"model","choices":[{"index":1,"delta":{"role":"assistant","content":"B"}},{"index":0,"delta":{"content":"Hel","reasoning_content":"think","tool_calls":[{"index":3,"id":"call-1","type":"function","function":{"name":"lookup","arguments":"{\"x\":"}}]}}]}),
        json!({"choices":[{"index":0,"delta":{"content":"lo","reasoning_content":"ing","tool_calls":[{"index":3,"function":{"arguments":"1}"}}]},"finish_reason":"tool_calls"}]}),
        json!({"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":5}}),
    ]);
    let result = rebuild("openai.chat", &(body + "data: [DONE]\n\n")).unwrap();
    assert_eq!(result["object"], "chat.completion");
    assert_eq!(result["choices"][0]["message"]["content"], "Hello");
    assert_eq!(
        result["choices"][0]["message"]["reasoning_content"],
        "thinking"
    );
    assert_eq!(
        result["choices"][0]["message"]["tool_calls"][0],
        json!({"id":"call-1","type":"function","function":{"name":"lookup","arguments":"{\"x\":1}"}})
    );
    assert_eq!(result["choices"][1]["message"]["content"], "B");
    assert_eq!(result["usage"]["completion_tokens"], 5);
}

#[test]
fn anthropic_rebuilds_text_thinking_tools_and_merged_usage() {
    let body = stream(&[
        json!({"type":"message_start","message":{"id":"m","type":"message","role":"assistant","content":[],"usage":{"input_tokens":12,"output_tokens":1}}}),
        json!({"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":"","signature":""}}),
        json!({"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"reason"}}),
        json!({"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"sig"}}),
        json!({"type":"content_block_start","index":1,"content_block":{"type":"text","text":"Hi"}}),
        json!({"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"!"}}),
        json!({"type":"content_block_start","index":2,"content_block":{"type":"tool_use","id":"t","name":"lookup","input":{}}}),
        json!({"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"{\"x\":"}}),
        json!({"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"1}"}}),
        json!({"type":"content_block_stop","index":2}),
        json!({"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":8}}),
        json!({"type":"message_stop"}),
    ]);
    let result = rebuild("anthropic.messages", &body).unwrap();
    assert_eq!(
        result["content"][0],
        json!({"type":"thinking","thinking":"reason","signature":"sig"})
    );
    assert_eq!(result["content"][1]["text"], "Hi!");
    assert_eq!(result["content"][2]["input"], json!({"x":1}));
    assert_eq!(result["stop_reason"], "tool_use");
    assert_eq!(
        result["usage"],
        json!({"input_tokens":12,"output_tokens":8})
    );
}

#[test]
fn responses_uses_the_authoritative_terminal_snapshot() {
    for terminal in [
        "response.completed",
        "response.failed",
        "response.incomplete",
    ] {
        let response = json!({"id":"r","object":"response","output":[{"type":"message","content":[{"type":"output_text","text":"Hello"}]}],"usage":{"input_tokens":5,"output_tokens":2}});
        let body = stream(&[
            json!({"type":"response.created","response":{"id":"r","output":[]}}),
            json!({"type":"response.output_text.delta","delta":"Hello","output_index":0,"content_index":0}),
            json!({"type":terminal,"response":response}),
        ]);
        assert_eq!(rebuild("openai.responses", &body).unwrap(), response);
    }
}

#[test]
fn sse_handles_crlf_comments_multiline_data_and_huge_sparse_indices() {
    let body = ": ping\r\nevent: chunk\r\ndata: {\"choices\":\r\ndata: [{\"index\":18446744073709551615,\"delta\":{\"content\":\"ok\"}}]}\r\n\r\ndata: [DONE]\r\n\r\n";
    let result = rebuild("openai.chat", body).unwrap();
    assert_eq!(result["choices"].as_array().unwrap().len(), 1);
    assert_eq!(result["choices"][0]["message"]["content"], "ok");
}

#[test]
fn malformed_and_unsupported_relays_are_rejected() {
    let valid = relay("{}", "openai", "/v1/responses", "application/json");
    for (key, value) in [
        (
            "generation_id",
            json!("123e4567-e89b-42d3-a456-426614174000"),
        ),
        ("request", json!("{")),
        ("response", json!("[]")),
        ("retention_days", json!(7)),
        ("path", json!("/v1/unknown")),
        ("outcome", json!("invented")),
        ("status", json!(999)),
    ] {
        let mut input = valid.clone();
        input[key] = value;
        assert!(
            normalize(&serde_json::to_vec(&input).unwrap()).is_err(),
            "{key}"
        );
    }
    for (protocol, body) in [
        ("openai.chat", "data: nope\n\n"),
        (
            "anthropic.messages",
            "data: {\"type\":\"message_start\",\"message\":4}\n\n",
        ),
        (
            "anthropic.messages",
            "data: {\"type\":\"content_block_start\",\"index\":0,\"content_block\":4}\n\n",
        ),
    ] {
        assert!(rebuild(protocol, body).is_err());
    }
}

#[test]
fn interrupted_responses_retain_partial_text_and_tool_arguments() {
    let body = stream(&[
        json!({"type":"response.created","response":{"id":"r","status":"in_progress","output":[]}}),
        json!({"type":"response.output_item.added","output_index":0,"item":{"type":"message","id":"m","content":[]}}),
        json!({"type":"response.content_part.added","output_index":0,"content_index":0,"part":{"type":"output_text","text":"","annotations":[]}}),
        json!({"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"part"}),
        json!({"type":"response.output_item.added","output_index":1,"item":{"type":"function_call","id":"f","arguments":""}}),
        json!({"type":"response.function_call_arguments.delta","output_index":1,"delta":"{\"x\":"}),
    ]);
    let result = rebuild("openai.responses", &body).unwrap();
    assert_eq!(result["output"][0]["content"][0]["text"], "part");
    assert_eq!(result["output"][1]["arguments"], "{\"x\":");
}

#[test]
fn interrupted_responses_keep_reasoning_summaries_and_annotations() {
    let body = stream(&[
        json!({"type":"response.created","response":{"id":"r","status":"in_progress","output":[]}}),
        json!({"type":"response.output_item.added","output_index":0,"item":{"type":"reasoning","id":"reason","summary":[]}}),
        json!({"type":"response.reasoning_summary_part.added","output_index":0,"summary_index":0,"part":{"type":"summary_text","text":""}}),
        json!({"type":"response.reasoning_summary_text.delta","output_index":0,"summary_index":0,"delta":"First "}),
        json!({"type":"response.reasoning_summary_text.delta","output_index":0,"summary_index":0,"delta":"thought"}),
        json!({"type":"response.reasoning_summary_text.done","output_index":0,"summary_index":0,"text":"First thought."}),
        json!({"type":"response.reasoning_summary_part.added","output_index":0,"summary_index":1,"part":{"type":"summary_text","text":""}}),
        json!({"type":"response.reasoning_summary_text.delta","output_index":0,"summary_index":1,"delta":"Partial second thought"}),
        json!({"type":"response.output_item.added","output_index":1,"item":{"type":"message","id":"m","content":[]}}),
        json!({"type":"response.content_part.added","output_index":1,"content_index":0,"part":{"type":"output_text","text":"Text","annotations":[]}}),
        json!({"type":"response.output_text.annotation.added","output_index":1,"content_index":0,"annotation":{"type":"url_citation","url":"https://example.com"}}),
    ]);
    let result = rebuild("openai.responses", &body).unwrap();
    assert_eq!(
        result["output"][0]["summary"],
        json!([
            {"type":"summary_text","text":"First thought."},
            {"type":"summary_text","text":"Partial second thought"}
        ])
    );
    assert_eq!(
        result["output"][1]["content"][0]["annotations"][0]["type"],
        "url_citation"
    );
}
