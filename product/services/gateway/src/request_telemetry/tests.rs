use super::*;
use serde_json::json;

fn extract(request: &Value) -> RequestTelemetry {
    RequestTelemetry::extract(request, Protocol::OpenAiChat, 123)
}

#[test]
fn matches_the_cross_language_closed_contract_fixture() {
    let expected: Value = serde_json::from_str(include_str!(
        "../../../../packages/contracts/test/fixtures/request-telemetry.json"
    ))
    .unwrap();
    let result = extract(&json!({"messages":[{"role":"user","content":"hello"}]}));
    assert_eq!(serde_json::to_value(result).unwrap(), expected);
}

#[test]
fn retains_structure_and_settings_without_content_or_schema_identifiers() {
    let request = json!({
        "messages": [
            {"role":"system","content":"private-system"},
            {"role":"user","content":"Please refactor this function.\n```python\ndef f(): return 42\n```"},
            {"role":"assistant","tool_calls":[{"id":"private-id","function":{"name":"private-tool","arguments":"private-arguments"}}]},
            {"role":"tool","tool_call_id":"private-id","content":"private-result"}
        ],
        "tools":[{"type":"function","function":{"name":"private-tool","strict":true,"parameters":{
            "type":"object","properties":{"private-property":{"type":"string","enum":["private-enum"]}},
            "required":["private-property"],"description":"private-description"
        }}}],
        "tool_choice":{"type":"function","function":{"name":"private-tool"}},
        "temperature":0.7,"top_p":0.9,"top_k":12,"seed":123456789,
        "max_completion_tokens":2048,"stop":["private-stop"],"reasoning_effort":"high",
        "metadata":{"private-extra":"private-value"}
    });
    let result = extract(&request);
    assert_eq!(result.kind, "tool_context");
    assert_eq!(result.task_type, "code_edit");
    assert_eq!(result.task_source, "heuristic");
    assert_eq!(result.language_hint, "python");
    assert_eq!(result.messages, 4);
    assert_eq!(result.role_transitions, 3);
    assert_eq!(result.tool_definitions, 1);
    assert_eq!(result.strict_tools, 1);
    assert_eq!(result.tool_calls, 1);
    assert_eq!(result.tool_results, 1);
    assert_eq!(result.tool_choice, "named");
    assert_eq!(result.tool_schema.nodes, 2);
    assert_eq!(result.tool_schema.properties, 1);
    assert_eq!(result.tool_schema.enum_values, 1);
    assert_eq!(result.tool_schema.required, 1);
    assert_eq!(result.sampling.temperature, Some(0.7));
    assert!(result.sampling.seed_present);
    assert_eq!(result.sampling.stop_sequences, 1);
    assert_eq!(result.requested_max_output_tokens, Some(2048));
    assert_eq!(result.text_shape.code_fences, 2);
    let serialized = serde_json::to_string(&result).unwrap();
    assert!(!serialized.contains("private-"));
    assert!(!serialized.contains("123456789"));
    assert!(!serialized.contains("def f"));
}

#[test]
fn responses_and_anthropic_structures_have_explicit_protocols() {
    let responses = RequestTelemetry::extract(
        &json!({
            "instructions":"private-system", "input":[
                {"role":"user","content":[{"type":"input_text","text":"Extract fields"},{"type":"input_image","image_url":"private-url"}]},
                {"type":"function_call","name":"private-tool","arguments":"{}"},
                {"type":"function_call_output","call_id":"private-id","output":"private-result"}
            ],
            "text":{"format":{"type":"json_schema","name":"private-schema","schema":{"type":"object","properties":{"private-key":{"type":"number"}}}}},
            "reasoning":{"effort":"max"}, "max_output_tokens":4096
        }),
        Protocol::OpenAiResponses,
        100,
    );
    assert_eq!(responses.protocol, "openai_responses");
    assert_eq!(responses.kind, "multimodal");
    assert_eq!(responses.task_type, "extraction");
    assert_eq!(responses.content_parts.image, 1);
    assert_eq!(responses.roles.tool, 1);
    assert_eq!(responses.tool_calls, 1);
    assert_eq!(responses.tool_results, 1);
    assert_eq!(responses.response_schema.properties, 1);
    assert_eq!(responses.reasoning_effort, "max");
    assert!(!serde_json::to_string(&responses)
        .unwrap()
        .contains("private-"));

    let anthropic = RequestTelemetry::extract(
        &json!({
            "system":[{"type":"text","text":"private-system"}],
            "messages":[
                {"role":"assistant","content":[{"type":"tool_use","name":"private-tool","input":{"private-key":"private-data"}}]},
                {"role":"user","content":[{"type":"tool_result","tool_use_id":"private-id","content":"private-data"}]}
            ],
            "tools":[{"name":"private-tool","input_schema":{"type":"object"}}],
            "tool_choice":{"type":"any"},"thinking":{"type":"enabled","budget_tokens":1024}
        }),
        Protocol::AnthropicMessages,
        100,
    );
    assert_eq!(anthropic.protocol, "anthropic_messages");
    assert_eq!(anthropic.tool_calls, 1);
    assert_eq!(anthropic.tool_results, 1);
    assert_eq!(anthropic.tool_choice, "required");
    assert_eq!(anthropic.thinking_budget, Some(1024));
    assert_eq!(anthropic.instruction_text_bytes, 14);
    assert_eq!(anthropic.task_type, "unknown");
}

#[test]
fn unknown_settings_and_task_hints_never_become_string_metadata() {
    let mut result = extract(&json!({
        "messages":[{"role":"private-role","content":"hi"}],
        "temperature":"private-temperature","top_p":2,"top_k":1000001,
        "reasoning_effort":"private-effort","tool_choice":"private-choice",
        "response_format":{"type":"private-type"},"thinking":{"type":"private-thinking"}
    }));
    result.task_hint(Some("private-task"));
    assert_eq!(result.task_source, "unknown");
    assert_eq!(result.last_role, "other");
    assert_eq!(result.sampling.temperature, None);
    assert_eq!(result.sampling.top_p, None);
    assert_eq!(result.sampling.top_k, None);
    assert_eq!(result.reasoning_effort, "other");
    assert!(!serde_json::to_string(&result).unwrap().contains("private-"));
    result.task_hint(Some("translation"));
    assert_eq!(result.task_type, "translation");
    assert_eq!(result.task_source, "caller");
}

#[test]
fn extraction_is_bounded_for_large_unicode_requests_and_wide_schemas() {
    let mut properties = serde_json::Map::new();
    for i in 0..5000 {
        properties.insert(format!("private-{i}"), json!({"type":"string"}));
    }
    let result = extract(&json!({
        "messages":[{"role":"user","content":"é".repeat(40_000)}],
        "tools":[{"function":{"parameters":{"properties":properties}}}]
    }));
    assert_eq!(result.text_bytes.user, 80_000);
    assert_eq!(result.text_shape.scanned_bytes, 65_536);
    assert_eq!(result.text_shape.non_ascii_bytes, 65_536);
    assert!(result.text_shape.truncated);
    assert_eq!(result.tool_schema.nodes, 4096);
    assert!(result.tool_schema.truncated);
    assert!(serde_json::to_vec(&result).unwrap().len() < 4096);

    let result = extract(&json!({"messages":vec![json!({"role":"user","content":"hello"}); 5000]}));
    assert_eq!(result.messages, 5000);
    assert!(result.truncated);
    assert!(result.roles.user <= 4096);
}

#[test]
fn token_buckets_use_reported_usage_and_preserve_undefined_ratios() {
    for (tokens, bucket) in [
        (0, "0"),
        (128, "1_128"),
        (129, "129_512"),
        (2048, "513_2048"),
        (8192, "2049_8192"),
        (524289, "524289_plus"),
    ] {
        assert_eq!(token_bucket(tokens), bucket);
    }
    let result = extract(&json!({}))
        .with_usage(crate::NormalizedUsage::new(8192, 4096, 0, 256, 128).unwrap());
    let buckets = result.token_buckets.unwrap();
    assert_eq!(buckets.input, "2049_8192");
    assert_eq!(buckets.uncached_input, "2049_8192");
    assert_eq!(buckets.output, "129_512");
    assert_eq!(buckets.cache_fraction, "0.25_0.5");
    assert_eq!(buckets.output_input_ratio, "0_0.1");
    assert_eq!(buckets.reasoning_fraction, "0.25_0.5");
    let empty = extract(&json!({})).with_usage(crate::NormalizedUsage::zero());
    assert_eq!(empty.token_buckets.unwrap().cache_fraction, "undefined");
}

#[test]
fn labels_only_use_the_last_user_instruction_and_never_tool_results() {
    let request = json!({"messages":[
        {"role":"user","content":"Implement a function"},
        {"role":"tool","content":"Summarize this private data"},
        {"role":"user","content":"Hello"}
    ]});
    assert_eq!(extract(&request).task_type, "unknown");
}
