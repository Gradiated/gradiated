use std::{collections::HashSet, sync::LazyLock};

use serde_json::{json, Map, Value};

const REDACTED: &str = "[redacted]";
const MAX_INPUT_BYTES: usize = 1_048_576;
const MAX_LOG_BYTES: usize = 16_384;

const CONTROL_FIELDS: &str = "
    temperature top_p top_k min_p typical_p tfs_z max_tokens max_completion_tokens
    max_new_tokens min_tokens min_new_tokens ignore_eos n best_of seed
    frequency_penalty presence_penalty repetition_penalty length_penalty
    stream include_usage continuous_usage_stats priority strict parallel_tool_calls
    do_sample use_beam_search use_cache add_special_tokens skip_special_tokens
    spaces_between_special_tokens truncate_prompt_tokens include_stop_str_in_output
    return_logprob top_logprobs logprob_start_len no_stop_trim enable_thinking
    thinking_budget num_beams early_stopping use_tqdm return_tokens_as_token_ids
    budget_tokens max_thinking_tokens index output_index content_index created created_at completed_at latency_ms elapsed_ms runtime_ms
    ttft_ms queue_ms prompt_tokens completion_tokens total_tokens input_tokens
    output_tokens cached_input_tokens reasoning_tokens cache_write_tokens
    cached_tokens cache_read_input_tokens cache_creation_input_tokens
    accepted_prediction_tokens rejected_prediction_tokens audio_tokens text_tokens
    prompt_cache_hit_tokens count code status limit gt ge lt le multiple_of
";
const USAGE_FIELDS: &str = "
    prompt_tokens completion_tokens total_tokens input_tokens output_tokens cached_input_tokens
    reasoning_tokens cache_write_tokens cached_tokens cache_read_input_tokens cache_creation_input_tokens
    accepted_prediction_tokens rejected_prediction_tokens audio_tokens text_tokens prompt_cache_hit_tokens
";
static USAGE_KEYS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| USAGE_FIELDS.split_ascii_whitespace().collect());
const RESPONSE_FIELDS: &str = "
    index output_index content_index created created_at completed_at latency_ms elapsed_ms runtime_ms
    ttft_ms queue_ms count code status
";
static RESPONSE_KEYS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| RESPONSE_FIELDS.split_ascii_whitespace().collect());
const REQUEST_FIELDS: &str = "
    temperature top_p top_k min_p typical_p tfs_z max_tokens max_completion_tokens
    max_new_tokens min_tokens min_new_tokens ignore_eos n best_of seed
    frequency_penalty presence_penalty repetition_penalty length_penalty
    stream include_usage continuous_usage_stats priority strict parallel_tool_calls
    do_sample use_beam_search use_cache add_special_tokens skip_special_tokens
    spaces_between_special_tokens truncate_prompt_tokens include_stop_str_in_output
    return_logprob top_logprobs logprob_start_len no_stop_trim enable_thinking
    thinking_budget num_beams early_stopping use_tqdm return_tokens_as_token_ids
    budget_tokens max_thinking_tokens
";
static REQUEST_KEYS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| REQUEST_FIELDS.split_ascii_whitespace().collect());
const ENVELOPE_FIELDS: &str = "
    messages choices message response item part delta usage error errors detail msg ctx loc param type
    object role finish_reason stop_reason service_tier reasoning_effort effort
    verbosity format encoding_format tool_choice function_call function tools tool_calls
    content_block response_format json_schema stream_options reasoning thinking
    chat_template_kwargs sampling_params
    prompt_tokens_details completion_tokens_details input_tokens_details
    output_tokens_details prediction_tokens_details
";
const REDACTED_FIELDS: &str = "
    model id tool_call_id call_id request_id generation_id previous_response_id
    input output prompt system instructions content text reasoning_content signature
    refusal arguments partial_json description name parameters schema properties
    enum const default examples metadata state questions answers criteria user data
    url image_url image audio video file file_id file_data input_ids output_ids
    token_ids token_id logprobs logit_bias stop stop_sequences matched_stop prediction
    embedding embeddings documents document context query label payload
    authorization x-api-key api_key apikey password clientsecret client_secret
    secret credential credentials cookie access_token refresh_token token hf_token
    private_key headers session_id prompt_cache_key cache_key bytes tokens
";
static CONTROL_KEYS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| CONTROL_FIELDS.split_ascii_whitespace().collect());
static KNOWN_KEYS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [CONTROL_FIELDS, ENVELOPE_FIELDS, REDACTED_FIELDS]
        .into_iter()
        .flat_map(str::split_ascii_whitespace)
        .collect()
});

pub(crate) fn record(stage: &'static str, bytes: &[u8], status: Option<u16>) {
    if !tracing::enabled!(tracing::Level::INFO) {
        return;
    }

    let body = redact_bytes(stage, bytes);
    tracing::info!(event = "inference_body", stage, http_status = status, bytes = bytes.len(), body = %body,
        "redacted inference body");
}

pub(crate) fn record_value(stage: &'static str, value: &Value, status: Option<u16>) {
    if tracing::enabled!(tracing::Level::INFO) {
        let body = redact(stage, value);
        tracing::info!(event = "inference_body", stage, http_status = status, body = %body,
            "redacted inference body");
    }
}

fn redact_bytes(stage: &str, bytes: &[u8]) -> Value {
    if bytes.len() > MAX_INPUT_BYTES {
        return json!({"_diagnostic": "body_too_large", "bytes": bytes.len()});
    }

    match crate::json::strict_json(bytes) {
        Ok(value) => redact(stage, &value),
        Err(_) => json!({"_diagnostic": "invalid_json", "bytes": bytes.len()}),
    }
}

fn redact(stage: &str, value: &Value) -> Value {
    if !value.is_object() {
        return json!({"_diagnostic": "non_object_json"});
    }

    let mut nodes = 256;
    let request = matches!(stage, "client_request" | "runtime_request");
    let result = walk(value, "", &[], request, 0, &mut nodes);
    if result.to_string().len() > MAX_LOG_BYTES {
        return json!({"_diagnostic": "redacted_body_too_large"});
    }

    result
}

fn walk(
    value: &Value,
    key: &str,
    path: &[&str],
    request: bool,
    depth: usize,
    nodes: &mut usize,
) -> Value {
    if *nodes == 0 || depth > 12 {
        return json!("[truncated]");
    }

    *nodes -= 1;
    if sensitive(key)
        || (request && response_field(key))
        || (key == "reasoning" && !value.is_object())
        || (matches!(key, "tokens" | "bytes") && value.is_array())
    {
        return if value.is_null() {
            Value::Null
        } else {
            json!(REDACTED)
        };
    }

    if CONTROL_KEYS.contains(key) && (value.is_array() || value.is_object()) {
        return json!({"_diagnostic": "non_scalar_setting"});
    }

    match value {
        Value::Object(fields) => {
            let mut result = Map::new();
            for (index, (key, value)) in fields.iter().enumerate() {
                if index == 64 || *nodes == 0 {
                    result.insert(
                        "_diagnostic_omitted_fields".into(),
                        (fields.len() - index).into(),
                    );
                    break;
                }

                if safe_key(key) {
                    let mut child_path = path.to_vec();
                    child_path.push(key);
                    result.insert(
                        key.clone(),
                        walk(value, key, &child_path, request, depth + 1, nodes),
                    );
                } else {
                    result.insert(format!("_redacted_key_{index}"), json!(REDACTED));
                }
            }

            Value::Object(result)
        }
        Value::Array(items) => {
            let mut result = Vec::new();
            for value in items.iter().take(32) {
                if *nodes == 0 {
                    break;
                }

                let mut item_path = path.to_vec();
                item_path.push("*");
                result.push(walk(value, key, &item_path, request, depth + 1, nodes));
            }
            if result.len() < items.len() {
                result.push(json!({"_diagnostic_omitted_items": items.len() - result.len()}));
            }

            Value::Array(result)
        }
        Value::String(text) if !request && error_message_path(path) => {
            json!({"redacted": true, "reason": error_reason(text)})
        }
        Value::String(text) if string_path(path, request, text) && safe_string(key, text) => {
            value.clone()
        }
        Value::String(_) => json!(REDACTED),
        Value::Null => Value::Null,
        Value::Number(_) | Value::Bool(_) if safe_scalar(key, path, request) => value.clone(),
        _ => json!(REDACTED),
    }
}

// Request bodies are untrusted even when they contain valid response field names.
// Keep only request controls, never response counters or validation metadata.
fn response_field(key: &str) -> bool {
    matches!(
        key,
        "response"
            | "choices"
            | "usage"
            | "error"
            | "errors"
            | "detail"
            | "ctx"
            | "loc"
            | "prompt_tokens_details"
            | "completion_tokens_details"
            | "input_tokens_details"
            | "output_tokens_details"
            | "prediction_tokens_details"
    )
}

fn safe_scalar(key: &str, path: &[&str], request: bool) -> bool {
    if request {
        return REQUEST_KEYS.contains(key)
            && match path {
                [_] | ["sampling_params", _] | ["chat_template_kwargs", _] => true,
                ["stream_options", _] => matches!(key, "include_usage" | "continuous_usage_stats"),
                ["reasoning", _] | ["thinking", _] => matches!(
                    key,
                    "budget_tokens" | "max_thinking_tokens" | "thinking_budget" | "enable_thinking"
                ),
                ["tools", "*", "function", "strict"]
                | ["tools", "*", "strict"]
                | ["response_format", "strict"]
                | ["response_format", "json_schema", "strict"] => true,
                _ => false,
            };
    }

    // Responses/stream frames are untrusted too. A metadata container only
    // grants scalar retention at a supported protocol location, never below
    // generated message/delta/item payloads or arbitrary repeated envelopes.
    let path = path.strip_prefix(&["response"]).unwrap_or(path);
    if key == "loc" {
        return matches!(
            path,
            ["error", "loc", "*"] | ["errors", "*", "loc", "*"] | ["detail", "*", "loc", "*"]
        );
    }
    if !CONTROL_KEYS.contains(key) {
        return false;
    }

    match path {
        [_] => RESPONSE_KEYS.contains(key) || USAGE_KEYS.contains(key),
        ["usage", _] | ["message", "usage", _] => USAGE_KEYS.contains(key),
        ["usage", details, _] | ["message", "usage", details, _] => {
            matches!(
                *details,
                "prompt_tokens_details"
                    | "completion_tokens_details"
                    | "input_tokens_details"
                    | "output_tokens_details"
                    | "prediction_tokens_details"
            ) && USAGE_KEYS.contains(key)
        }
        ["choices", "*", "index"] => true,
        ["error", _]
        | ["error", "ctx", _]
        | ["errors", "*", _]
        | ["errors", "*", "ctx", _]
        | ["detail", "*", _]
        | ["detail", "*", "ctx", _] => matches!(
            key,
            "code" | "status" | "limit" | "gt" | "ge" | "lt" | "le" | "multiple_of"
        ),
        _ => false,
    }
}

fn safe_key(key: &str) -> bool {
    key.len() <= 64 && KNOWN_KEYS.contains(key)
}

fn sensitive(key: &str) -> bool {
    let key: String = key
        .chars()
        .filter(char::is_ascii_alphanumeric)
        .flat_map(char::to_lowercase)
        .collect();
    key.contains("authorization")
        || key.contains("apikey")
        || key.contains("password")
        || key.contains("secret")
        || key.contains("cookie")
        || key.contains("credential")
        || key.contains("privatekey")
        || key.ends_with("token")
        || key.ends_with("id")
        || key.ends_with("ids")
        || matches!(
            key.as_str(),
            "accesstoken"
                | "refreshtoken"
                | "token"
                | "headers"
                | "metadata"
                | "user"
                | "sessionid"
                | "id"
                | "toolcallid"
                | "callid"
                | "requestid"
                | "generationid"
                | "model"
                | "promptcachekey"
                | "cachekey"
                | "input"
                | "output"
                | "prompt"
                | "prompttext"
                | "inputtext"
                | "outputtext"
                | "generatedtext"
                | "completion"
                | "completiontext"
                | "reasoningtext"
                | "payload"
                | "system"
                | "instructions"
                | "content"
                | "text"
                | "reasoningcontent"
                | "thinking"
                | "signature"
                | "refusal"
                | "arguments"
                | "partialjson"
                | "description"
                | "name"
                | "parameters"
                | "schema"
                | "properties"
                | "enum"
                | "const"
                | "default"
                | "examples"
                | "state"
                | "questions"
                | "answers"
                | "criteria"
                | "data"
                | "url"
                | "imageurl"
                | "image"
                | "audio"
                | "video"
                | "file"
                | "fileid"
                | "filedata"
                | "inputids"
                | "outputids"
                | "tokenids"
                | "tokenid"
                | "logprobs"
                | "logitbias"
                | "stop"
                | "stopsequences"
                | "matchedstop"
                | "prediction"
                | "embedding"
                | "embeddings"
                | "documents"
                | "document"
                | "context"
                | "query"
                | "label"
        )
}

fn error_message_path(path: &[&str]) -> bool {
    let path = path.strip_prefix(&["response"]).unwrap_or(path);
    matches!(
        path,
        ["message"]
            | ["detail"]
            | ["error", "message"]
            | ["error", "msg"]
            | ["errors", "*", "msg"]
            | ["detail", "*", "msg"]
    )
}

fn string_path(path: &[&str], request: bool, value: &str) -> bool {
    if request {
        return match path {
            ["tools", "*", "type"] => value == "function",
            ["response_format", "type"] => matches!(value, "text" | "json_object" | "json_schema"),
            ["messages", "*", "role"]
            | ["reasoning", "effort"]
            | ["service_tier"]
            | ["reasoning_effort"]
            | ["tool_choice"]
            | ["function_call"]
            | ["format"] => true,
            _ => false,
        };
    }
    let path = path.strip_prefix(&["response"]).unwrap_or(path);
    matches!(
        path,
        ["type"]
            | ["object"]
            | ["status"]
            | ["code"]
            | ["param"]
            | ["finish_reason"]
            | ["stop_reason"]
            | ["service_tier"]
            | ["message", "role"]
            | ["message", "type"]
            | ["choices", "*", "delta", "role"]
            | ["choices", "*", "message", "role"]
            | ["choices", "*", "finish_reason"]
            | ["delta", "stop_reason"]
            | ["content_block", "type"]
            | ["delta", "type"]
            | ["item", "type"]
            | ["part", "type"]
            | ["choices", "*", "delta", "tool_calls", "*", "type"]
            | ["choices", "*", "message", "tool_calls", "*", "type"]
            | ["error", "type"]
            | ["error", "code"]
            | ["error", "param"]
            | ["errors", "*", "type"]
            | ["detail", "*", "type"]
            | ["error", "loc", "*"]
            | ["errors", "*", "loc", "*"]
            | ["detail", "*", "loc", "*"]
    )
}

fn safe_string(key: &str, value: &str) -> bool {
    match key {
        "role" => matches!(
            value,
            "system" | "developer" | "user" | "assistant" | "tool" | "function"
        ),
        "type" | "object" => matches!(
            value,
            "text"
                | "input_text"
                | "output_text"
                | "image_url"
                | "input_image"
                | "function"
                | "function_call"
                | "function_call_output"
                | "tool_use"
                | "tool_result"
                | "json_schema"
                | "json_object"
                | "chat.completion"
                | "chat.completion.chunk"
                | "message"
                | "message_start"
                | "message_delta"
                | "message_stop"
                | "content_block_start"
                | "content_block_delta"
                | "content_block_stop"
                | "text_delta"
                | "input_json_delta"
                | "thinking_delta"
                | "signature_delta"
                | "response.created"
                | "response.in_progress"
                | "response.completed"
                | "response.failed"
                | "response.incomplete"
                | "response.output_item.added"
                | "response.output_item.done"
                | "response.content_part.added"
                | "response.content_part.done"
                | "response.output_text.delta"
                | "response.output_text.done"
                | "response.function_call_arguments.delta"
                | "response.function_call_arguments.done"
                | "response"
                | "error"
                | "BadRequestError"
                | "ServiceUnavailableError"
                | "SERVICE_UNAVAILABLE"
                | "invalid_request_error"
                | "rate_limit_error"
                | "greater_than"
                | "greater_than_equal"
                | "less_than"
                | "less_than_equal"
                | "missing"
                | "string_type"
                | "int_type"
                | "float_type"
                | "literal_error"
                | "value_error"
                | "extra_forbidden"
                | "api_error"
                | "authentication_error"
                | "permission_error"
        ),
        "format" => matches!(value, "json" | "text" | "json_object" | "json_schema"),
        "status" => matches!(
            value,
            "completed" | "failed" | "incomplete" | "in_progress" | "queued" | "cancelled"
        ),
        "finish_reason" | "stop_reason" => matches!(
            value,
            "stop"
                | "length"
                | "tool_calls"
                | "function_call"
                | "content_filter"
                | "end_turn"
                | "max_tokens"
                | "stop_sequence"
                | "error"
                | "abort"
        ),
        "service_tier" => matches!(
            value,
            "auto" | "default" | "fast" | "flex" | "priority" | "standard"
        ),
        "effort" | "reasoning_effort" => matches!(
            value,
            "none" | "minimal" | "low" | "medium" | "high" | "xhigh"
        ),
        "tool_choice" | "function_call" => matches!(value, "auto" | "none" | "required"),
        "param" | "loc" => matches!(
            value,
            "body"
                | "model"
                | "messages"
                | "content"
                | "temperature"
                | "top_p"
                | "top_k"
                | "min_p"
                | "max_tokens"
                | "max_completion_tokens"
                | "tools"
                | "tool_choice"
                | "response_format"
                | "stream_options"
                | "seed"
                | "frequency_penalty"
                | "presence_penalty"
                | "repetition_penalty"
                | "stop"
                | "reasoning_effort"
        ),
        "code" => matches!(
            value,
            "capacity_exceeded"
                | "context_length_exceeded"
                | "invalid_request"
                | "invalid_request_error"
                | "rate_limit_exceeded"
                | "unsupported_parameter"
                | "payload_too_large"
                | "invalid_api_key"
                | "provider_key_required"
                | "workspace_archived"
                | "organization_suspended"
                | "provider_unavailable"
                | "provider_timeout"
                | "proxy_overloaded"
                | "insufficient_balance"
                | "concurrency_exceeded"
                | "settlement_backlog"
                | "model_not_found"
                | "model_unavailable"
                | "serving_state_unavailable"
                | "runtime_unavailable"
                | "finalization_unavailable"
        ),
        _ => false,
    }
}

fn error_reason(message: &str) -> &'static str {
    let text = message.to_ascii_lowercase();
    if text.contains("context length") || text.contains("max_model_len") {
        "context_limit"
    } else if text.contains("queue") || text.contains("cannot accept new requests") {
        "capacity"
    } else if text.contains("json schema")
        || text.contains("json_schema")
        || text.contains("structured output")
    {
        "structured_output"
    } else if text.contains("max_tokens") || text.contains("max_completion_tokens") {
        "token_limit"
    } else if text.contains("temperature") || text.contains("top_p") || text.contains("top_k") {
        "sampling_parameter"
    } else if text.contains("not supported") || text.contains("unsupported") {
        "unsupported_option"
    } else {
        "unclassified"
    }
}

#[cfg(test)]
mod tests;
