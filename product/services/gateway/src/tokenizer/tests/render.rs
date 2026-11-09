use serde_json::json;

use crate::{
    tokenizer::{
        map_request_error,
        test_support::{chat_tokenizer, qualified, tool_continuation_tokenizer, word_level},
        ModelTokenizer, TokenizerRequestError,
    },
    GatewayError,
};

#[test]
fn renders_and_retains_the_exact_generation_prompt_tokens() {
    assert_eq!(
        chat_tokenizer()
            .encode_input(&qualified(None).request)
            .map(|ids| ids.len()),
        Ok(3)
    );
}

#[test]
fn rejects_malformed_messages_as_caller_input() {
    let mut request = qualified(None).request;
    request.messages = vec![json!({"content": "hello"})];
    assert!(matches!(
        chat_tokenizer().encode_input(&request),
        Err(TokenizerRequestError::InvalidInput)
    ));
}

#[test]
fn renders_openai_tool_call_arguments_in_follow_up_requests() {
    let mut chat = qualified(None).request;
    chat.messages = vec![
        json!({"role": "user", "content": "List the files."}),
        json!({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_test",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": "{\"command\":\"ls -la\"}"
                }
            }]
        }),
        json!({
            "role": "tool",
            "tool_call_id": "call_test",
            "content": "Permission denied"
        }),
    ];

    assert!(tool_continuation_tokenizer().encode_input(&chat).is_ok());
    assert_eq!(
        chat.messages[1]["tool_calls"][0]["function"]["arguments"],
        "{\"command\":\"ls -la\"}"
    );
}

#[test]
fn rejects_invalid_tool_call_argument_json() {
    let mut chat = qualified(None).request;
    chat.messages = vec![json!({
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "type": "function",
            "function": {"name": "bash", "arguments": "{"}
        }]
    })];

    assert!(matches!(
        tool_continuation_tokenizer().encode_input(&chat),
        Err(TokenizerRequestError::InvalidInput)
    ));
}

#[tokio::test]
async fn logs_a_template_render_failure_with_a_bounded_code() {
    let qualified = qualified(None);
    let tokenizer = ModelTokenizer::seeded(
        &qualified.local_capacity().deployment.release,
        word_level(&["[UNK]"], "{{ messages[0].content + 1 }}"),
    );
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();

    let result = tokenizer.count(&qualified).await;

    assert_eq!(result, Err(GatewayError::ServingStateUnavailable));
    let events = logs.events();
    assert_eq!(events.len(), 1);
    assert_eq!(events[0]["fields"]["error_code"], "render");
    assert_eq!(
        events[0]["fields"]["tokenizer_path"],
        qualified.local_capacity().deployment.release.tokenizer_path
    );
    assert!(!events[0].to_string().contains("hello"));
}

#[test]
fn a_template_exception_rejects_the_request() {
    let tokenizer = word_level(&["[UNK]"], "{{ raise_exception('bad roles') }}");

    assert_eq!(
        tokenizer.encode_input(&qualified(None).request),
        Err(TokenizerRequestError::Rejected)
    );
}

#[test]
fn maps_request_errors_to_public_errors() {
    for (error, expected) in [
        (
            TokenizerRequestError::InvalidParameter("reasoning_effort"),
            GatewayError::invalid_request(Some("reasoning_effort")),
        ),
        (
            TokenizerRequestError::InvalidInput,
            GatewayError::invalid_request(Some("messages")),
        ),
        (
            TokenizerRequestError::Rejected,
            GatewayError::invalid_request(Some("messages")),
        ),
        (
            TokenizerRequestError::Render,
            GatewayError::ServingStateUnavailable,
        ),
        (
            TokenizerRequestError::Encode,
            GatewayError::ServingStateUnavailable,
        ),
    ] {
        assert_eq!(map_request_error(error), expected);
    }
}
