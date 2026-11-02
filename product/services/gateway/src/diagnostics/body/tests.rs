use super::*;

fn redact(value: &Value) -> Value {
    super::redact("runtime_response", value)
}

fn redact_bytes(bytes: &[u8]) -> Value {
    super::redact_bytes("runtime_response", bytes)
}

#[test]
fn request_stages_do_not_trust_response_metadata() {
    let value = json!({
        "temperature":0.25, "max_tokens":128, "stream":true,
        "stream_options":{"include_usage":true},
        "usage":{"total_tokens":123456789}, "total_tokens":123456789,
        "created":123456789, "code":123456789,
        "error":{"ctx":{"limit":123456789}},
        "response":{"usage":{"total_tokens":123456789}},
        "sampling_params":{"completion_tokens":123456789},
        "messages":[{"usage":{"total_tokens":123456789}}]
    });
    for stage in ["client_request", "runtime_request"] {
        for result in [
            super::redact(stage, &value),
            super::redact_bytes(stage, value.to_string().as_bytes()),
        ] {
            assert!(
                !result.to_string().contains("123456789"),
                "{stage}: {result}"
            );
            assert_eq!(result["temperature"], 0.25);
            assert_eq!(result["max_tokens"], 128);
            assert_eq!(result["stream_options"]["include_usage"], true);
        }
    }
    let response = super::redact("runtime_response", &value);
    assert_eq!(response["usage"]["total_tokens"], 123456789_u64);
}

#[test]
fn keeps_request_shape_and_settings_while_redacting_content() {
    let value = json!({
        "model": "dealignai/glm-5.3-flash-uncensored",
        "temperature": -0.5, "max_tokens": 4096, "stream": true,
        "future_setting": {"enabled": true, "level": 7},
        "messages": [
            {"role": "system", "content": "synthetic private instruction"},
            {"role": "user", "content": [{"type": "input_text", "text": "synthetic private input"}]}
        ],
        "tools": [{"type": "function", "function": {
            "name": "synthetic_private_tool", "description": "synthetic private description",
            "parameters": {"properties": {"synthetic_private_property": {"type": "string"}}}, "strict": true
        }}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "synthetic_private_schema", "strict": true, "schema": {"private": 1}
        }},
        "reasoning": {"effort": "high"}
    });
    let result = super::redact("client_request", &value);

    assert_eq!(result["temperature"], -0.5);
    assert_eq!(result["max_tokens"], 4096);
    assert!(!result.to_string().contains("future_setting"));
    assert_eq!(result["messages"][0]["role"], "system");
    assert_eq!(result["messages"][0]["content"], REDACTED);
    assert_eq!(result["tools"][0]["function"]["strict"], true);
    assert_eq!(result["response_format"]["json_schema"]["strict"], true);
    assert_eq!(result["reasoning"]["effort"], "high");
    assert!(!result.to_string().contains("synthetic"));
}

#[test]
fn keeps_response_usage_and_finish_metadata_without_generated_content() {
    let result = redact(&json!({
        "choices": [{"index": 0, "delta": {"role": "assistant",
            "content": "synthetic private output", "reasoning_content": "synthetic private reasoning",
            "tool_calls": [{"type": "function", "function": {
                "name": "synthetic_private_tool", "arguments": "{\"secret\":42}"
            }}]}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
            "completion_tokens_details": {"reasoning_tokens": 12}}
    }));

    assert_eq!(result["usage"]["total_tokens"], 120);
    assert_eq!(result["choices"][0]["finish_reason"], "tool_calls");
    assert_eq!(result["choices"][0]["delta"]["role"], "assistant");
    assert!(!result.to_string().contains("synthetic"));
    assert!(!result.to_string().contains("secret"));
}

#[test]
fn redacts_credentials_and_encoded_content_at_every_depth() {
    let result = redact(&json!({
        "Authorization": "synthetic bearer", "error": {
            "x-api-key": "synthetic key", "clientSecret": "synthetic secret",
            "hf_token": 987654, "private_key": [98, 99],
            "input_ids": [101, 202], "token_id": 12345, "output_ids": [303], "bytes": [65, 66],
            "tokens": [123, 456], "logit_bias": {"123": 5}, "metadata": {"text": "synthetic"}
        },
        "state": {"private_numeric_input": 98765},
        "answers": {"private_numeric_output": 98766},
        "image_url": {"url": "https://synthetic.invalid/private?token=secret"}
    }));

    assert_eq!(result["error"]["input_ids"], REDACTED);
    assert_eq!(result["error"]["bytes"], REDACTED);
    assert_eq!(result["state"], REDACTED);
    assert_eq!(result["answers"], REDACTED);
    for sentinel in [
        "synthetic",
        "98765",
        "98766",
        "101",
        "202",
        "303",
        "123",
        "456",
    ] {
        assert!(!result.to_string().contains(sentinel), "{sentinel}");
    }
}

#[test]
fn error_bodies_keep_codes_and_parameters_but_not_echoed_input() {
    let result = redact(&json!({"error": {
        "code": 400, "type": "BadRequestError", "param": "temperature",
        "message": "temperature is invalid; echoed input: synthetic private text",
        "input": {"prompt": "synthetic private text"}
    }}));

    assert_eq!(result["error"]["code"], 400);
    assert_eq!(result["error"]["param"], "temperature");
    assert_eq!(result["error"]["message"]["reason"], "sampling_parameter");
    assert!(!result.to_string().contains("synthetic"));
}

#[test]
fn unknown_keys_and_customer_primitives_are_redacted_while_response_metadata_survives() {
    let result = redact(&json!({
        "patient_id": 123456, "patient_age": 987654, "ssn_123_45_6789": true,
        "new_option": {"temperature": 987653, "secret": "synthetic private text"},
        "created":123, "temperature": 0.25, "max_tokens": 128, "stream": true,
        "top_k": [987649], "usage":{"output_tokens":[987648]},
        "messages": [{"role":"user", "temperature":987651}],
        "choices": [{"index":0,"delta":{"max_tokens":987650}}],
        "error": {"private_field_123456": 987652, "code": 400}
    }));

    assert_eq!(result["created"], 123);
    assert_eq!(result["temperature"], REDACTED);
    assert_eq!(result["max_tokens"], REDACTED);
    assert_eq!(result["stream"], REDACTED);
    assert_eq!(result["error"]["code"], 400);
    assert_eq!(result["messages"][0]["temperature"], REDACTED);
    assert_eq!(result["choices"][0]["delta"]["max_tokens"], REDACTED);
    assert_eq!(result["top_k"]["_diagnostic"], "non_scalar_setting");
    assert_eq!(
        result["usage"]["output_tokens"]["_diagnostic"],
        "non_scalar_setting"
    );
    for sentinel in [
        "patient",
        "123456",
        "ssn",
        "987654",
        "987653",
        "987652",
        "987651",
        "987650",
        "987649",
        "987648",
        "synthetic",
        "new_option",
    ] {
        assert!(!result.to_string().contains(sentinel), "{sentinel}");
    }
}

#[test]
fn malformed_duplicate_and_oversized_bodies_never_fall_back_to_raw_text() {
    for bytes in [
        b"synthetic private text".as_slice(),
        br#"{"prompt":"synthetic","prompt":42}"#,
    ] {
        let result = redact_bytes(bytes);
        assert_eq!(result["_diagnostic"], "invalid_json");
        assert!(!result.to_string().contains("synthetic"));
    }
    assert_eq!(
        redact_bytes(&vec![b'x'; MAX_INPUT_BYTES + 1])["_diagnostic"],
        "body_too_large"
    );
}

#[test]
fn large_and_deep_structures_produce_bounded_valid_json() {
    let wide = Value::Object(
        (0..1000)
            .map(|i| (format!("setting_{i}"), json!(vec![1; 32])))
            .collect(),
    );
    let result = redact(&wide);
    assert!(result.to_string().len() <= MAX_LOG_BYTES);
    assert!(result.to_string().contains("diagnostic"));

    let mut deep = json!({"content": "synthetic private text"});
    for _ in 0..50 {
        deep = json!({"error": deep});
    }
    let result = redact(&deep);
    assert!(result.to_string().contains("truncated"));
    assert!(!result.to_string().contains("synthetic"));
}

#[test]
fn recorded_events_contain_only_the_redacted_body() {
    let logs = super::super::capture::Logs::default();
    let _guard = logs.start();
    record("runtime_response", br#"{"error":{"code":400,"message":"max_tokens invalid: synthetic secret","input":"synthetic input"}}"#, Some(400));
    let events = logs.events();
    let event = events
        .iter()
        .find(|e| e["fields"]["event"] == "inference_body")
        .unwrap();
    assert_eq!(event["fields"]["http_status"], 400);
    assert!(!event.to_string().contains("synthetic"));
    let body: Value = serde_json::from_str(event["fields"]["body"].as_str().unwrap()).unwrap();
    assert_eq!(body["error"]["code"], 400);
    assert_eq!(body["error"]["message"]["reason"], "token_limit");
}

#[test]
fn opaque_identifiers_and_unverified_model_names_never_bypass_redaction() {
    let result = redact(&json!({
        "id": "chatcmpl_PRIVATE_PROMPT", "tool_call_id": "call_PRIVATE_PROMPT",
        "call_id": "call_PRIVATE_PROMPT", "request_id": "msg_PRIVATE_PROMPT",
        "generation_id": "resp_PRIVATE_PROMPT", "model": "PRIVATE_PROMPT/model",
        "previous_response_id": 987654321, "stop_token_ids": [987654321],
        "nested": {"id": 987654321, "model": {"encoded_input": [65, 66]}},
        "choices": [{"delta": {"tool_calls": [{"id": "call_PRIVATE_PROMPT"}]}}]
    }));
    assert!(!result.to_string().contains("PRIVATE_PROMPT"));
    assert!(!result.to_string().contains("987654321"));
    assert_eq!(result["model"], REDACTED);
    assert!(!result.to_string().contains("nested"));
    assert_eq!(
        redact(&json!({"id":"019a19d3-0000-7000-8000-000000000001"}))["id"],
        REDACTED
    );
}

#[test]
fn non_object_json_cannot_smuggle_customer_data_as_an_envelope() {
    let result = redact(&json!([{"temperature":987654}]));
    assert_eq!(result["_diagnostic"], "non_object_json");
    assert!(!result.to_string().contains("987654"));
}

#[test]
fn responses_and_anthropic_envelopes_keep_protocol_metadata_without_output_content() {
    let responses = redact(&json!({"type":"response.completed", "response":{
        "id":"resp_PRIVATE_PROMPT", "created_at":123, "status":"completed",
        "output":[{"text":"PRIVATE_PROMPT"}],
        "usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15}
    }}));
    assert_eq!(responses["type"], "response.completed");
    assert_eq!(responses["response"]["created_at"], 123);
    assert_eq!(responses["response"]["usage"]["total_tokens"], 15);
    let anthropic = redact(&json!({"type":"message_start", "message":{
        "id":"msg_PRIVATE_PROMPT", "role":"assistant", "content":[{"text":"PRIVATE_PROMPT"}],
        "usage":{"input_tokens":10,"output_tokens":5}
    }}));
    assert_eq!(anthropic["type"], "message_start");
    assert_eq!(anthropic["message"]["usage"]["input_tokens"], 10);
    assert!(!responses.to_string().contains("PRIVATE_PROMPT"));
    assert!(!anthropic.to_string().contains("PRIVATE_PROMPT"));
}

#[test]
fn request_scalars_require_exact_ancestor_paths() {
    let value = json!({
        "seed":7, "sampling_params":{"seed":8},
        "chat_template_kwargs":{"enable_thinking":true},
        "tools":[{"type":"function","function":{"strict":true}}],
        "messages":[{
            "sampling_params":{"seed":123456789},
            "chat_template_kwargs":{"temperature":123456789},
            "tools":[{"function":{"strict":123456789}}],
            "response_format":{"json_schema":{"strict":123456789}}
        }],
        "reasoning":{"sampling_params":{"seed":123456789}},
        "stream_options":{"chat_template_kwargs":{"temperature":123456789}}
    });
    for stage in ["client_request", "runtime_request"] {
        for result in [
            super::redact(stage, &value),
            super::redact_bytes(stage, value.to_string().as_bytes()),
        ] {
            assert!(
                !result.to_string().contains("123456789"),
                "{stage}: {result}"
            );
            assert_eq!(result["seed"], 7);
            assert_eq!(result["sampling_params"]["seed"], 8);
            assert_eq!(result["chat_template_kwargs"]["enable_thinking"], true);
            assert_eq!(result["tools"][0]["function"]["strict"], true);
        }
    }
}

#[test]
fn retained_field_names_require_exact_canonical_spelling() {
    let value = json!({"TemPERaTURE":123456789,"temperature":0.25,
        "messages":[{"rOLe":"user","role":"user","cONtent":"synthetic"}],
        "UsAGe":{"total_tokens":123456789},
        "usage":{"Total_TOKENS":123456789,"total_tokens":42}});
    for stage in [
        "client_request",
        "runtime_request",
        "runtime_response",
        "client_response",
    ] {
        let result = super::redact(stage, &value);
        let encoded = result.to_string();
        for forbidden in [
            "TemPERaTURE",
            "rOLe",
            "cONtent",
            "UsAGe",
            "Total_TOKENS",
            "123456789",
            "synthetic",
        ] {
            assert!(!encoded.contains(forbidden), "{stage}: {result}");
        }
        if stage.ends_with("request") {
            assert_eq!(result["temperature"], 0.25);
        } else {
            assert_eq!(result["temperature"], REDACTED);
        }
        assert_eq!(
            result["messages"][0]["role"],
            if stage.ends_with("request") {
                "user"
            } else {
                REDACTED
            }
        );
    }
}

#[test]
fn response_scalars_require_exact_protocol_paths() {
    let value = json!({
        "created":123, "temperature":123456789, "choices":[{"index":0,"delta":{
            "usage":{"total_tokens":123456789},
            "error":{"code":123456789}, "response":{"created":123456789}
        }}],
        "message":{"usage":{"input_tokens":10},"sampling_params":{"seed":123456789}},
        "usage":{"total_tokens":15,"max_tokens":123456789,"completion_tokens_details":{"reasoning_tokens":5,"min_tokens":123456789}},
        "error":{"code":400,"ctx":{"limit":42},"loc":["body",0,"temperature"]},
        "detail":[{"ctx":{"ge":0},"loc":["body",1,"temperature"]}],
        "response":{"created_at":124,"usage":{"total_tokens":16},
            "response":{"created":123456789}},
        "item":{"usage":{"total_tokens":123456789}},
        "sampling_params":{"usage":{"total_tokens":123456789}}
    });
    for stage in [
        "runtime_response",
        "client_response",
        "client_error",
        "runtime_response_frame",
        "runtime_response_invalid_frame",
        "client_response_frame",
    ] {
        for result in [
            super::redact(stage, &value),
            super::redact_bytes(stage, value.to_string().as_bytes()),
        ] {
            assert!(
                !result.to_string().contains("123456789"),
                "{stage}: {result}"
            );
            assert_eq!(result["created"], 123);
            assert_eq!(result["choices"][0]["index"], 0);
            assert_eq!(result["usage"]["total_tokens"], 15);
            assert_eq!(
                result["usage"]["completion_tokens_details"]["reasoning_tokens"],
                5
            );
            assert_eq!(result["message"]["usage"]["input_tokens"], 10);
            assert_eq!(result["response"]["created_at"], 124);
            assert_eq!(result["response"]["usage"]["total_tokens"], 16);
            assert_eq!(result["error"]["code"], 400);
            assert_eq!(result["error"]["loc"][1], 0);
            assert_eq!(result["detail"][0]["ctx"]["ge"], 0);
            assert_eq!(result["detail"][0]["loc"][1], 1);
        }
    }
}

#[test]
fn enum_strings_and_error_hints_require_stage_specific_full_paths() {
    let misplaced = json!({
        "delta":[{"role":"user"},{"role":"assistant"}],
        "messages":[{"delta":{"role":"assistant"},"service_tier":"priority"}],
        "reasoning":{"tool_choice":"required"},
        "tools":[{"type":"message_start"}],"response_format":{"type":"BadRequestError"},
        "item":{"error":{"type":"BadRequestError","message":"max_tokens invalid"}},
        "response":{"response":{"status":"completed"}},
        "message":"max_tokens invalid"
    });
    for stage in ["client_request", "runtime_request"] {
        let result = super::redact(stage, &misplaced);
        for forbidden in [
            "user",
            "assistant",
            "priority",
            "required",
            "BadRequestError",
            "message_start",
            "completed",
            "token_limit",
        ] {
            assert!(!result.to_string().contains(forbidden), "{stage}: {result}");
        }
    }
    for stage in [
        "runtime_response",
        "client_response",
        "runtime_response_frame",
        "runtime_response_invalid_frame",
    ] {
        let result = super::redact(stage, &misplaced);
        for forbidden in [
            "user",
            "assistant",
            "priority",
            "required",
            "BadRequestError",
            "completed",
        ] {
            assert!(!result.to_string().contains(forbidden), "{stage}: {result}");
        }
        assert_eq!(result["item"]["error"]["message"], REDACTED);
        assert_eq!(result["message"]["reason"], "token_limit");
    }
    let request = super::redact(
        "client_request",
        &json!({
            "messages":[{"role":"user"}],"tools":[{"type":"function"}],
            "response_format":{"type":"json_schema"},"reasoning":{"effort":"high"},
            "service_tier":"priority","tool_choice":"required"
        }),
    );
    assert_eq!(request["messages"][0]["role"], "user");
    assert_eq!(request["tools"][0]["type"], "function");
    assert_eq!(request["response_format"]["type"], "json_schema");
    assert_eq!(request["reasoning"]["effort"], "high");
    assert_eq!(request["service_tier"], "priority");
    assert_eq!(request["tool_choice"], "required");
}
