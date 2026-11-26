use serde_json::json;

use crate::{
    tokenizer::{test_support::qualified, ModelTokenizer},
    QualifiedRequest, TokenizerMode,
};

fn pinned(repository: &str, revision: &str) -> QualifiedRequest {
    let mut qualified = qualified(Some(64));
    let release = &mut qualified.local_capacity_mut().deployment.release;
    release.model_path = repository.to_owned();
    release.model_revision = revision.to_owned();
    release.tokenizer_path = repository.to_owned();
    release.tokenizer_revision = revision.to_owned();

    qualified
}

async fn pinned_input_ids(qualified: QualifiedRequest) -> Vec<u32> {
    let bounded = ModelTokenizer::new()
        .unwrap()
        .enforce(qualified)
        .await
        .unwrap();

    bounded.qualified.request.encoded_input_ids.unwrap()
}

#[tokio::test]
#[ignore = "downloads the pinned local-model tokenizer from Hugging Face"]
async fn loads_and_renders_the_pinned_qwen_release() {
    let mut qualified = pinned(
        "mlx-community/Qwen3-0.6B-4bit",
        "73e3e38d981303bc594367cd910ea6eb48349da8",
    );
    qualified.max_context_tokens = 131_072;
    qualified.max_prompt_tokens = 131_008;
    qualified.request.parameters.insert(
        "tools".to_owned(),
        json!([{
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Read the weather",
                "parameters": {"type": "object", "properties": {}}
            }
        }]),
    );

    assert!(!pinned_input_ids(qualified).await.is_empty());
}

#[tokio::test]
#[ignore = "downloads the pinned production Gemma tokenizer from Hugging Face"]
async fn loads_and_renders_the_pinned_gemma4_release() {
    let mut qualified = pinned(
        "google/gemma-4-31B-it",
        "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
    );
    qualified.max_context_tokens = 8_192;
    qualified.max_prompt_tokens = 4_096;

    assert!(!pinned_input_ids(qualified).await.is_empty());
}

#[tokio::test]
#[ignore = "downloads the pinned production GLM tokenizer from Hugging Face"]
async fn loads_and_renders_the_pinned_glm_tool_continuation() {
    let mut qualified = pinned(
        "zai-org/GLM-5.3-Flash",
        "84c6a6aa9497188e15a635ba793b0f95a79b1033",
    );
    qualified.max_context_tokens = 1_048_576;
    qualified.max_prompt_tokens = 1_048_512;
    qualified.request.messages = vec![
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
    qualified.request.parameters.insert(
        "tools".to_owned(),
        json!([{
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"]
                }
            }
        }]),
    );

    assert!(!pinned_input_ids(qualified).await.is_empty());
}

#[tokio::test]
#[ignore = "downloads the pinned production DeepSeek V4 tokenizer from Hugging Face"]
async fn loads_and_renders_the_pinned_deepseek_v4_release() {
    let mut qualified = pinned(
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "7872f01b1d1fe23eabc4c98b48bffcef5a386062",
    );
    qualified.max_context_tokens = 262_144;
    qualified.max_prompt_tokens = 262_080;
    qualified
        .local_capacity_mut()
        .deployment
        .release
        .tokenizer_mode = Some(TokenizerMode::DeepseekV4);
    qualified.request.messages = vec![
        json!({"role": "system", "content": "Be concise."}),
        json!({"role": "user", "content": "Hello"}),
        json!({"role": "assistant", "content": "Hi"}),
        json!({"role": "user", "content": "Continue"}),
    ];

    assert_eq!(
        pinned_input_ids(qualified).await,
        [
            0, 7153, 47468, 16, 128_803, 19_923, 128_804, 128_822, 23_166, 1, 128_803, 56_761,
            128_804, 128_822,
        ]
    );
}

async fn deepseek_v41_input_ids(repository: &str, revision: &str) -> Vec<u32> {
    let mut qualified = pinned(repository, revision);
    qualified.max_context_tokens = 1_048_576;
    qualified.max_prompt_tokens = 1_048_512;
    qualified
        .local_capacity_mut()
        .deployment
        .release
        .tokenizer_mode = Some(TokenizerMode::DeepseekV41);
    qualified.request.messages = vec![
        json!({"role": "system", "content": "Be concise."}),
        json!({"role": "user", "content": "Hello"}),
        json!({"role": "assistant", "content": "Hi"}),
        json!({"role": "user", "content": "Continue"}),
    ];

    pinned_input_ids(qualified).await
}

#[tokio::test]
#[ignore = "downloads the pinned DeepSeek V4.1 Flash tokenizers from Hugging Face"]
async fn deepseek_v41_flash_1017_tokenizes_like_the_release_it_replaced() {
    let replacement = deepseek_v41_input_ids(
        "deepseek-ai/DeepSeek-V4.1-Flash-1017",
        "1bae0e1088993b9b82de08f59de5be5a34e42170",
    )
    .await;

    assert!(!replacement.is_empty());
    assert_eq!(
        replacement,
        deepseek_v41_input_ids(
            "deepseek-ai/DeepSeek-V4.1-Flash",
            "dba1be0a40aa45a94ad051997016db3960a90277",
        )
        .await
    );
}

#[tokio::test]
#[ignore = "downloads the pinned Kimi K3.1 tiktoken tokenizers from Hugging Face"]
async fn loads_and_renders_the_pinned_kimi_k31_releases() {
    let tokenizer = ModelTokenizer::new().unwrap();
    let count_for = |path: &str, revision: &str, message: &str| {
        let mut request = qualified(None);
        request.local = None;
        request.tokenizer = Some(crate::PinnedTokenizer {
            path: path.to_owned(),
            revision: revision.to_owned(),
        });
        request.request.messages = vec![json!({"role": "user", "content": message})];
        request
    };

    let stock = count_for(
        "moonshotai/Kimi-K3.1-Pro",
        "d9e99b0792a5e93b78ea9bea62a68167e36ddd9e",
        "Hello from count_tokens check!",
    );
    let cyber = count_for(
        "yetalabs/Kimi-K3.1-Pro-abliterated",
        "0911ef0765f49d26dfa25bb0d071f29463f8000b",
        "Hello from count_tokens check!",
    );

    // Verified against live SGLang /v1/messages/count_tokens on 8xB300 (94 tokens).
    assert_eq!(tokenizer.count(&stock).await, Ok(94));
    assert_eq!(tokenizer.count(&cyber).await, Ok(94));

    // Also verify Unicode/CJK, tools, and special-token literal escaping match across both pins.
    let mut complex_stock = count_for(
        "moonshotai/Kimi-K3.1-Pro",
        "d9e99b0792a5e93b78ea9bea62a68167e36ddd9e",
        "你好世界 <|open|> check 12345",
    );
    complex_stock.request.parameters.insert(
        "tools".to_owned(),
        json!([{
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Read the weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
            }
        }]),
    );
    let mut complex_cyber = complex_stock.clone();
    complex_cyber.tokenizer = cyber.tokenizer.clone();

    let stock_count = tokenizer.count(&complex_stock).await.unwrap();
    let cyber_count = tokenizer.count(&complex_cyber).await.unwrap();
    assert!(stock_count > 120);
    assert_eq!(stock_count, cyber_count);
}
