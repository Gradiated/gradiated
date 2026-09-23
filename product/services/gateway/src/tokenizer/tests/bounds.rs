use crate::{
    tokenizer::{enforce_bounds, test_support::qualified},
    GatewayError,
};

#[test]
fn enforces_prompt_and_combined_context_bounds() {
    let mut prompt_too_large = qualified(None);
    prompt_too_large.max_prompt_tokens = 2;
    assert_eq!(
        enforce_bounds(prompt_too_large, 3),
        Err(GatewayError::context_length_exceeded("messages"))
    );

    assert_eq!(
        enforce_bounds(qualified(Some(8)), 3),
        Err(GatewayError::context_length_exceeded(
            "max_completion_tokens"
        ))
    );

    assert!(enforce_bounds(qualified(Some(7)), 3).is_ok());
}

#[test]
fn an_overflowing_context_total_is_a_serving_failure() {
    assert_eq!(
        enforce_bounds(qualified(Some(u64::MAX)), 3),
        Err(GatewayError::ServingStateUnavailable)
    );
}
