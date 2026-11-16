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
fn malformed_envelopes_are_rejected() {
    let valid = relay("{}", "openai", "/v1/responses", "application/json");
    for (key, value) in [
        (
            "generation_id",
            json!("123e4567-e89b-42d3-a456-426614174000"),
        ),
        ("retention_days", json!(7)),
        ("outcome", json!("invented")),
        ("request_base64", json!("AAAA")),
        ("response", json!(null)),
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

#[test]
fn hosted_chat_is_trainable_with_canonical_text_and_tools() {
    for streamed in [false, true] {
        let message = json!({"role":"assistant","content":"Refund approved","tool_calls":null});
        let response = if streamed {
            stream(&[json!({"choices":[{"index":0,"delta":message,"finish_reason":"stop"}]})])
                + "data: [DONE]\n\n"
        } else {
            json!({"choices":[{"message":message,"finish_reason":"stop"}]}).to_string()
        };
        let mut input = relay(
            &response,
            "openai",
            "/v1/chat/completions",
            if streamed {
                "text/event-stream"
            } else {
                "application/json"
            },
        );
        input["schema"] = json!("gradiated.hosted/1");
        input["request"] = json!(json!({"model":"synthetic-model","messages":[{"role":"user","content":"Refund my order"}],"tools":null}).to_string());
        let output: Value =
            serde_json::from_slice(&normalize(&serde_json::to_vec(&input).unwrap()).unwrap())
                .unwrap();
        assert_eq!(output["source"], "hosted");
        assert_eq!(output["provider"], "gradiated");
        assert_eq!(output["trainable"], true);
        assert_eq!(
            output["canonical"]["messages"][0]["content"],
            "Refund my order"
        );
        assert_eq!(output["canonical"]["output"]["content"], "Refund approved");
        assert_eq!(output["canonical"]["tools"], json!([]));
        assert_eq!(output["canonical"]["output"]["tool_calls"], json!([]));
    }
}

#[test]
fn hosted_tool_calls_are_retained_and_length_limited_answers_are_truncated() {
    let tool = json!({"type":"function","function":{"name":"lookup"}});
    let call = json!({"id":"c","type":"function","function":{"name":"lookup","arguments":"{}"}});
    let mut input = relay(&json!({"choices":[{"message":{"role":"assistant","content":null,"tool_calls":[call]},"finish_reason":"tool_calls"}]}).to_string(),"openai","/v1/chat/completions","application/json");
    input["schema"] = json!("gradiated.hosted/1");
    input["request"] = json!(json!({"model":"synthetic-model","messages":[{"role":"user","content":"Lookup"}],"tools":[tool]}).to_string());
    let output: Value =
        serde_json::from_slice(&normalize(&serde_json::to_vec(&input).unwrap()).unwrap()).unwrap();
    assert_eq!(output["canonical"]["tools"], json!([tool]));
    assert_eq!(output["canonical"]["output"]["tool_calls"], json!([call]));
    input["response"] = json!(json!({"choices":[{"message":{"role":"assistant","content":"partial"},"finish_reason":"length"}]}).to_string());
    let output: Value =
        serde_json::from_slice(&normalize(&serde_json::to_vec(&input).unwrap()).unwrap()).unwrap();
    assert_eq!(output["outcome"], "truncated");
}

#[test]
fn hosted_bare_endpoints_preserve_protocol_and_classify_token_limits() {
    for (provider, path, response) in [
        (
            "openai",
            "/chat/completions",
            json!({"choices":[{"message":{"role":"assistant","content":"partial"},"finish_reason":"length"}]}),
        ),
        (
            "anthropic",
            "/messages",
            json!({"content":[{"type":"text","text":"partial"}],"stop_reason":"max_tokens"}),
        ),
        (
            "openai",
            "/responses",
            json!({"status":"incomplete","incomplete_details":{"reason":"max_output_tokens"},"output":[]}),
        ),
    ] {
        let mut input = relay(&response.to_string(), provider, path, "application/json");
        input["schema"] = json!("gradiated.hosted/1");
        let output: Value =
            serde_json::from_slice(&normalize(&serde_json::to_vec(&input).unwrap()).unwrap())
                .unwrap();
        assert_eq!(output["outcome"], "truncated");
        assert_eq!(output["source"], "hosted");
    }
}

fn raw(input: &Value) -> Value {
    serde_json::from_slice(&normalize(&serde_json::to_vec(input).unwrap()).unwrap()).unwrap()
}

#[test]
fn bodies_that_do_not_parse_as_their_protocol_are_kept_raw() {
    for (key, value) in [
        ("request", json!("{")),
        ("response", json!("[]")),
        ("path", json!("/v1/unknown")),
    ] {
        let mut input = relay("{}", "openai", "/v1/responses", "application/json");
        input[key] = value.clone();
        let record = raw(&input);
        assert_eq!(record["protocol"], "openai.http", "{key}");
        assert_eq!(record["raw"]["path"], input["path"], "{key}");
        assert_eq!(record["canonical"], Value::Null, "{key}");
    }

    let mut stream = relay(
        "data: nope\n\n",
        "openai",
        "/v1/chat/completions",
        "text/event-stream",
    );
    stream["outcome"] = json!("error");
    let record = raw(&stream);
    assert_eq!(record["protocol"], "openai.http");
    assert_eq!(record["streamed"], true);
    assert_eq!(record["outcome"], "error");
    assert_eq!(record["raw"]["response"], "data: nope\n\n");
}

#[test]
fn embeddings_keep_json_bodies_model_and_usage() {
    let mut input = relay(
        r#"{"data":[{"embedding":[0.1]}],"usage":{"prompt_tokens":3,"total_tokens":3}}"#,
        "openai",
        "/v1/embeddings",
        "application/json",
    );
    input["request"] = json!(r#"{"model":"text-embedding-3-small","input":"hi"}"#);
    let record = raw(&input);

    assert_eq!(record["model"], "text-embedding-3-small");
    assert_eq!(record["raw"]["request"]["input"], "hi");
    assert_eq!(record["raw"]["response"]["data"][0]["embedding"][0], 0.1);
    assert_eq!(record["usage"]["input"], 3);
    assert_eq!(record["source"], "relay");
    assert_eq!(record["trainable"], false);
}

#[test]
fn multipart_uploads_and_binary_responses_keep_exact_bytes() {
    use base64::{engine::general_purpose::STANDARD, Engine};

    let upload = b"--b0und\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n--b0und\r\nContent-Disposition: form-data; name=\"file\"; filename=\"tone.wav\"\r\nContent-Type: audio/wav\r\n\r\nRIFF\xff\xfe\x00\x01\r\n--b0und--\r\n";
    let audio = b"ID3\x04\x00\xff\xfb\x90";
    let mut input = relay("", "openai", "/v1/audio/transcriptions", "audio/mpeg");
    input.as_object_mut().unwrap().remove("request");
    input.as_object_mut().unwrap().remove("response");
    input["request_base64"] = json!(STANDARD.encode(upload));
    input["request_content_type"] = json!("multipart/form-data; boundary=b0und");
    input["response_base64"] = json!(STANDARD.encode(audio));
    let record = raw(&input);

    assert_eq!(record["protocol"], "openai.http");
    assert_eq!(record["model"], "whisper-1");
    assert_eq!(
        record["raw"]["request_content_type"],
        "multipart/form-data; boundary=b0und"
    );
    assert_eq!(record["raw"]["request"]["encoding"], "base64");
    let stored = STANDARD
        .decode(record["raw"]["request"]["data"].as_str().unwrap())
        .unwrap();
    assert_eq!(stored, upload);
    let stored = STANDARD
        .decode(record["raw"]["response"]["data"].as_str().unwrap())
        .unwrap();
    assert_eq!(stored, audio);
    assert_eq!(record["usage"], Value::Null);
}

#[test]
fn text_bodies_and_requests_without_a_model_are_kept() {
    let mut input = relay("Beep.", "openai", "/v1/audio/transcriptions", "text/plain");
    input["request"] = json!("");
    input["request_content_type"] = Value::Null;
    let record = raw(&input);

    assert_eq!(record["model"], "unknown");
    assert_eq!(record["raw"]["request"], "");
    assert_eq!(record["raw"]["response"], "Beep.");
}

#[test]
fn a_request_that_does_not_decode_is_kept_raw_with_its_coding() {
    use base64::{engine::general_purpose::STANDARD, Engine};

    let mut input = relay("{}", "openai", "/v1/responses", "application/json");
    input.as_object_mut().unwrap().remove("request");
    input["request_base64"] = json!(STANDARD.encode(b"\x1f\x8b\x08\x00"));
    input["request_content_encoding"] = json!("gzip");
    let record = raw(&input);

    assert_eq!(record["protocol"], "openai.http");
    assert_eq!(record["raw"]["request_content_encoding"], "gzip");
    assert_eq!(record["raw"]["request"]["encoding"], "base64");

    let mut identity = relay("{}", "openai", "/v1/responses", "application/json");
    identity["request_content_encoding"] = json!("identity");
    assert_eq!(raw(&identity)["protocol"], "openai.responses");
}

fn gzip(bytes: &[u8]) -> Vec<u8> {
    use std::io::Write;

    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(bytes).unwrap();
    encoder.finish().unwrap()
}

fn compressed(response: &[u8], provider: &str, path: &str, mime: &str, coding: &str) -> Value {
    use base64::{engine::general_purpose::STANDARD, Engine};

    let mut input = relay("", provider, path, mime);
    input.as_object_mut().unwrap().remove("response");
    input["response_base64"] = json!(STANDARD.encode(response));
    input["response_content_encoding"] = json!(coding);
    input
}

#[test]
fn gzip_json_and_event_stream_responses_are_decoded_and_parsed() {
    let body = br#"{"choices":[{"message":{"role":"assistant","content":"Decoded"},"finish_reason":"stop"}],"usage":{"prompt_tokens":4,"completion_tokens":1}}"#;
    let record = raw(&compressed(
        &gzip(body),
        "openai",
        "/v1/chat/completions",
        "application/json",
        "gzip",
    ));
    assert_eq!(record["protocol"], "openai.chat");
    assert_eq!(
        record["raw"]["response"]["choices"][0]["message"]["content"],
        "Decoded"
    );
    assert_eq!(record["usage"]["input"], 4);

    let events = stream(&[
        json!({"type": "message_start", "message": {"id": "msg_1", "role": "assistant", "content": [], "usage": {"input_tokens": 3, "output_tokens": 0}}}),
        json!({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        json!({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hi"}}),
        json!({"type": "content_block_stop", "index": 0}),
        json!({"type": "message_stop"}),
    ]);
    let record = raw(&compressed(
        &gzip(events.as_bytes()),
        "anthropic",
        "/v1/messages",
        "text/event-stream",
        "gzip",
    ));
    assert_eq!(record["protocol"], "anthropic.messages");
    assert_eq!(record["streamed"], true);
    assert_eq!(record["raw"]["response"]["content"][0]["text"], "Hi");
}

#[test]
fn a_gzip_request_is_decoded_and_parsed() {
    use base64::{engine::general_purpose::STANDARD, Engine};

    let mut input = relay("{}", "openai", "/v1/responses", "application/json");
    input.as_object_mut().unwrap().remove("request");
    input["request_base64"] = json!(STANDARD.encode(gzip(br#"{"model":"gpt-test","input":"hi"}"#)));
    input["request_content_encoding"] = json!("gzip");
    let record = raw(&input);

    assert_eq!(record["protocol"], "openai.responses");
    assert_eq!(record["model"], "gpt-test");
    assert_eq!(record["raw"]["request"]["input"], "hi");
}

#[test]
fn a_cancelled_compressed_stream_keeps_what_decoded() {
    let events: String = (0..2000)
        .map(|n| {
            format!(
                "data: {}\n\n",
                json!({"choices": [{"index": 0, "delta": {"content": format!("{n} ")}}]})
            )
        })
        .collect();
    let encoded = gzip(events.as_bytes());
    let mut input = compressed(
        &encoded[..encoded.len() / 2],
        "openai",
        "/v1/chat/completions",
        "text/event-stream",
        "gzip",
    );
    input["outcome"] = json!("cancelled");
    let record = raw(&input);

    assert_eq!(record["protocol"], "openai.chat");
    assert_eq!(record["outcome"], "cancelled");
    let text = record["raw"]["response"]["choices"][0]["message"]["content"]
        .as_str()
        .unwrap();
    assert!(text.starts_with("0 1 2 "), "{text}");
}

#[test]
fn bodies_that_do_not_decode_are_kept_with_their_coding() {
    let encoded = gzip(br#"{"choices":[]}"#);
    let truncated = compressed(
        &encoded[..encoded.len() - 4],
        "openai",
        "/v1/chat/completions",
        "application/json",
        "gzip",
    );
    let unknown = compressed(
        b"\x1f\x9d\x90",
        "openai",
        "/v1/chat/completions",
        "application/json",
        "compress",
    );

    for (input, coding) in [(truncated, "gzip"), (unknown, "compress")] {
        let record = raw(&input);
        assert_eq!(record["protocol"], "openai.http", "{coding}");
        assert_eq!(record["raw"]["response_content_encoding"], coding);
        assert_eq!(record["raw"]["response"]["encoding"], "base64");
    }
}

#[test]
fn an_interrupted_stream_cut_mid_event_keeps_its_whole_events() {
    let mut input = relay(
        "data: {\"choices\":[{\"index\":0,\"delta\":{\"content\":\"Kept\"}}]}\n\ndata: {\"choi",
        "openai",
        "/v1/chat/completions",
        "text/event-stream",
    );
    input["outcome"] = json!("cancelled");
    let record = raw(&input);

    assert_eq!(record["protocol"], "openai.chat");
    assert_eq!(
        record["raw"]["response"]["choices"][0]["message"]["content"],
        "Kept"
    );
}
