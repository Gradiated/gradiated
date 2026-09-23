use serde_json::Value;

use super::{
    deepseek::{ASSISTANT, BOS, EOS, USER},
    TokenizerRequestError,
};
use crate::InferenceRequest;

const CHAT_MODE: &str = "</think>";

#[derive(Clone, Copy, Eq, PartialEq)]
enum Role {
    System,
    Developer,
    User,
    Assistant,
}

struct Message {
    role: Role,
    content: String,
}

pub(super) fn render(request: &InferenceRequest) -> Result<String, TokenizerRequestError> {
    let messages = normalize_messages(&request.messages)?;
    let mut prompt = String::from(BOS);

    for (index, message) in messages.iter().enumerate() {
        match message.role {
            Role::System => prompt.push_str(&message.content),
            Role::Developer | Role::User => {
                prompt.push_str(USER);
                prompt.push_str(&message.content);
            }
            Role::Assistant => {
                prompt.push_str(&message.content);
                prompt.push_str(EOS);
            }
        }

        let next_role = messages.get(index + 1).map(|next| next.role);
        if matches!(message.role, Role::Developer | Role::User)
            && (next_role.is_none() || next_role == Some(Role::Assistant))
        {
            prompt.push_str(ASSISTANT);
            prompt.push_str(CHAT_MODE);
        }
    }

    Ok(prompt)
}

fn normalize_messages(messages: &[Value]) -> Result<Vec<Message>, TokenizerRequestError> {
    let mut normalized: Vec<Message> = Vec::with_capacity(messages.len());

    for message in messages {
        let object = message
            .as_object()
            .ok_or(TokenizerRequestError::InvalidInput)?;
        let role = object
            .get("role")
            .and_then(Value::as_str)
            .ok_or(TokenizerRequestError::InvalidInput)?;
        let content = content(object.get("content"))?;

        match role {
            "system" => normalized.push(Message {
                role: Role::System,
                content,
            }),
            "developer" => {
                if content.is_empty() {
                    return Err(TokenizerRequestError::Rejected);
                }

                normalized.push(Message {
                    role: Role::Developer,
                    content,
                });
            }
            "user" => merge_user_content(&mut normalized, content),
            "tool" => merge_user_content(
                &mut normalized,
                format!("<tool_result>{content}</tool_result>"),
            ),
            "assistant" => {
                if object
                    .get("tool_calls")
                    .is_some_and(|calls| calls.as_array().is_none_or(|values| !values.is_empty()))
                {
                    return Err(TokenizerRequestError::Rejected);
                }

                normalized.push(Message {
                    role: Role::Assistant,
                    content,
                });
            }
            _ => return Err(TokenizerRequestError::Rejected),
        }
    }

    Ok(normalized)
}

fn merge_user_content(messages: &mut Vec<Message>, content: String) {
    if let Some(previous) = messages.last_mut().filter(|last| last.role == Role::User) {
        previous.content.push_str("\n\n");
        previous.content.push_str(&content);
        return;
    }

    messages.push(Message {
        role: Role::User,
        content,
    });
}

fn content(value: Option<&Value>) -> Result<String, TokenizerRequestError> {
    match value {
        None | Some(Value::Null) => Ok(String::new()),
        Some(Value::String(content)) => Ok(content.clone()),
        Some(Value::Array(parts)) => {
            let mut content = String::new();
            for part in parts {
                let part = part
                    .as_object()
                    .ok_or(TokenizerRequestError::InvalidInput)?;
                if part.get("type").and_then(Value::as_str) != Some("text") {
                    return Err(TokenizerRequestError::Rejected);
                }

                content.push_str(
                    part.get("text")
                        .and_then(Value::as_str)
                        .ok_or(TokenizerRequestError::InvalidInput)?,
                );
            }

            Ok(content)
        }
        Some(_) => Err(TokenizerRequestError::InvalidInput),
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn request(messages: Value) -> InferenceRequest {
        serde_json::from_value(json!({"model": "test", "messages": messages})).unwrap()
    }

    #[test]
    fn renders_the_chat_mode_prompt() {
        let chat = request(json!([
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Continue"},
        ]));

        assert_eq!(
            render(&chat),
            Ok(concat!(
                "<｜begin▁of▁sentence｜>",
                "Be concise.",
                "<｜User｜>Hello",
                "<｜Assistant｜></think>",
                "Hi<｜end▁of▁sentence｜>",
                "<｜User｜>Continue",
                "<｜Assistant｜></think>"
            )
            .to_owned())
        );
    }

    #[test]
    fn merges_user_and_tool_result_messages() {
        let chat = request(json!([
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
            {"role": "tool", "content": "Result"},
        ]));

        assert_eq!(
            render(&chat),
            Ok(concat!(
                "<｜begin▁of▁sentence｜>",
                "<｜User｜>First\n\nSecond\n\n<tool_result>Result</tool_result>",
                "<｜Assistant｜></think>"
            )
            .to_owned())
        );
    }

    #[test]
    fn rejects_what_the_chat_mode_prompt_cannot_express() {
        for (case, messages) in [
            (
                "empty developer message",
                json!([{"role": "developer", "content": ""}]),
            ),
            (
                "assistant tool calls",
                json!([{"role": "assistant", "content": "", "tool_calls": [{"id": "call"}]}]),
            ),
            (
                "non-text content part",
                json!([{"role": "user", "content": [{"type": "image_url", "image_url": {}}]}]),
            ),
        ] {
            assert_eq!(
                render(&request(messages)),
                Err(TokenizerRequestError::Rejected),
                "{case}"
            );
        }
    }
}
