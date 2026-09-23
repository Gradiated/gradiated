use hf_chat_template::{ChatTemplate, Error as ChatTemplateError, RenderInput, TokenizerConfig};
use serde_json::{Map, Value};

use super::{deepseek_v4, deepseek_v41, TokenizerRequestError};
use crate::{InferenceRequest, TokenizerMode};

pub(super) enum PromptRenderer {
    HuggingFace(Box<ChatTemplate>),
    DeepseekV4,
    DeepseekV41,
}

impl PromptRenderer {
    pub(super) fn new(
        mode: Option<TokenizerMode>,
        template_source: Option<&str>,
        config: &TokenizerConfig,
    ) -> Result<Self, ChatTemplateError> {
        let template = match mode {
            Some(TokenizerMode::DeepseekV4) => return Ok(Self::DeepseekV4),
            Some(TokenizerMode::DeepseekV41) => return Ok(Self::DeepseekV41),
            None => match template_source {
                Some(source) => ChatTemplate::from_template_and_config(source, config)?,
                None => ChatTemplate::from_tokenizer_config(config)?,
            },
        };

        Ok(Self::HuggingFace(Box::new(template)))
    }

    pub(super) fn render(
        &self,
        request: &InferenceRequest,
    ) -> Result<String, TokenizerRequestError> {
        match self {
            Self::HuggingFace(template) => {
                template
                    .render(&render_input(request)?)
                    .map_err(|error| match error {
                        ChatTemplateError::TemplateRaised { .. } => TokenizerRequestError::Rejected,
                        _ => TokenizerRequestError::Render,
                    })
            }
            Self::DeepseekV4 => deepseek_v4::render(request),
            Self::DeepseekV41 => deepseek_v41::render(request),
        }
    }
}

fn render_input(request: &InferenceRequest) -> Result<RenderInput, TokenizerRequestError> {
    let messages = request
        .messages
        .iter()
        .cloned()
        .map(normalize_chat_template_message)
        .collect::<Result<Vec<_>, _>>()?;

    let mut fields: Map<String, Value> = request.parameters.clone();
    fields.insert("messages".to_owned(), Value::Array(messages));
    fields.insert("add_generation_prompt".to_owned(), Value::Bool(true));

    serde_json::from_value(Value::Object(fields)).map_err(|_| TokenizerRequestError::InvalidInput)
}

fn normalize_chat_template_message(mut message: Value) -> Result<Value, TokenizerRequestError> {
    let Some(tool_calls) = message
        .as_object_mut()
        .and_then(|message| message.get_mut("tool_calls"))
    else {
        return Ok(message);
    };

    let Some(tool_calls) = tool_calls.as_array_mut() else {
        return Err(TokenizerRequestError::InvalidInput);
    };

    for tool_call in tool_calls {
        let Some(arguments) = tool_call
            .as_object_mut()
            .and_then(|tool_call| tool_call.get_mut("function"))
            .and_then(Value::as_object_mut)
            .and_then(|function| function.get_mut("arguments"))
        else {
            continue;
        };

        if let Value::String(encoded) = arguments {
            let decoded: Value =
                serde_json::from_str(encoded).map_err(|_| TokenizerRequestError::InvalidInput)?;
            if !decoded.is_object() {
                return Err(TokenizerRequestError::InvalidInput);
            }

            *arguments = decoded;
        }
    }

    Ok(message)
}
