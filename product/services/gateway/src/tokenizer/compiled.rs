use std::{
    fs,
    path::{Path, PathBuf},
};

use hf_chat_template::TokenizerConfig;
use tokenizers::Tokenizer;

use super::{
    kimi_k31::KimiK31Tokenizer, renderer::PromptRenderer, ModelTokenizerError,
    TokenizerRequestError,
};
use crate::{InferenceRequest, TokenizerMode};

pub(super) enum TokenizerArtifacts {
    HuggingFace {
        tokenizer: PathBuf,
        config: PathBuf,
        template: Option<PathBuf>,
    },
    KimiK31 {
        vocab: PathBuf,
        config: PathBuf,
    },
}

pub(super) enum CompiledTokenizer {
    HuggingFace {
        tokenizer: Box<Tokenizer>,
        renderer: PromptRenderer,
    },
    KimiK31(Box<KimiK31Tokenizer>),
}

impl CompiledTokenizer {
    pub(super) fn load(
        artifacts: &TokenizerArtifacts,
        mode: Option<TokenizerMode>,
    ) -> Result<Self, ModelTokenizerError> {
        match artifacts {
            TokenizerArtifacts::HuggingFace {
                tokenizer,
                config,
                template,
            } => {
                let tokenizer = Tokenizer::from_file(tokenizer)
                    .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string()))?;
                let config = read_tokenizer_config(config)?;
                let template = template.as_deref().map(fs::read_to_string).transpose()?;

                Ok(Self::HuggingFace {
                    tokenizer: Box::new(tokenizer),
                    renderer: PromptRenderer::new(mode, template.as_deref(), &config)?,
                })
            }
            TokenizerArtifacts::KimiK31 { vocab, config } => Ok(Self::KimiK31(Box::new(
                KimiK31Tokenizer::load(vocab, config)?,
            ))),
        }
    }

    #[cfg(test)]
    pub(super) fn from_tokenizer(
        tokenizer: Tokenizer,
        chat_template: &str,
    ) -> Result<Self, ModelTokenizerError> {
        let config: TokenizerConfig =
            serde_json::from_value(serde_json::json!({ "chat_template": chat_template }))?;

        Ok(Self::HuggingFace {
            tokenizer: Box::new(tokenizer),
            renderer: PromptRenderer::new(None, None, &config)?,
        })
    }

    pub(super) fn encode_input(
        &self,
        request: &InferenceRequest,
    ) -> Result<Vec<u32>, TokenizerRequestError> {
        match self {
            Self::HuggingFace {
                tokenizer,
                renderer,
            } => {
                let prompt = renderer.render(request)?;

                // The rendered prompt already contains its model's special tokens.
                let encoding = tokenizer
                    .encode(prompt, false)
                    .map_err(|_| TokenizerRequestError::Encode)?;

                Ok(encoding.get_ids().to_vec())
            }
            Self::KimiK31(kimi) => kimi.encode_input(request),
        }
    }

    pub(super) fn decode(&self, token_ids: &[u32]) -> Result<String, ModelTokenizerError> {
        match self {
            Self::HuggingFace { tokenizer, .. } => tokenizer
                .decode(token_ids, true)
                .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string())),
            Self::KimiK31(kimi) => kimi.decode(token_ids),
        }
    }

    pub(super) fn step_decode(
        &self,
        token_id: u32,
        ids: &mut Vec<u32>,
        prefix: &mut String,
        prefix_index: &mut usize,
    ) -> Result<Option<String>, ModelTokenizerError> {
        match self {
            Self::HuggingFace { tokenizer, .. } => tokenizers::tokenizer::step_decode_stream(
                tokenizer,
                vec![token_id],
                true,
                ids,
                prefix,
                prefix_index,
            )
            .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string())),
            Self::KimiK31(_) => Err(ModelTokenizerError::Tokenizer(
                "streaming decode is unsupported for Kimi K3.1 tiktoken".to_owned(),
            )),
        }
    }
}

fn read_tokenizer_config(path: &Path) -> Result<TokenizerConfig, ModelTokenizerError> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}
