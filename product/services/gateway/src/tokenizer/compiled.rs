use std::{
    fs,
    path::{Path, PathBuf},
};

use hf_chat_template::TokenizerConfig;
use tokenizers::Tokenizer;

use super::{renderer::PromptRenderer, ModelTokenizerError, TokenizerRequestError};
use crate::{InferenceRequest, TokenizerMode};

pub(super) struct TokenizerArtifacts {
    pub(super) tokenizer: PathBuf,
    pub(super) config: PathBuf,
    pub(super) template: Option<PathBuf>,
}

pub(super) struct CompiledTokenizer {
    pub(super) tokenizer: Tokenizer,
    renderer: PromptRenderer,
}

impl CompiledTokenizer {
    pub(super) fn load(
        artifacts: &TokenizerArtifacts,
        mode: Option<TokenizerMode>,
    ) -> Result<Self, ModelTokenizerError> {
        let tokenizer = Tokenizer::from_file(&artifacts.tokenizer)
            .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string()))?;
        let config = read_tokenizer_config(&artifacts.config)?;
        let template = artifacts
            .template
            .as_deref()
            .map(fs::read_to_string)
            .transpose()?;

        Ok(Self {
            tokenizer,
            renderer: PromptRenderer::new(mode, template.as_deref(), &config)?,
        })
    }

    #[cfg(test)]
    pub(super) fn from_tokenizer(
        tokenizer: Tokenizer,
        chat_template: &str,
    ) -> Result<Self, ModelTokenizerError> {
        let config: TokenizerConfig =
            serde_json::from_value(serde_json::json!({ "chat_template": chat_template }))?;

        Ok(Self {
            tokenizer,
            renderer: PromptRenderer::new(None, None, &config)?,
        })
    }

    pub(super) fn encode_input(
        &self,
        request: &InferenceRequest,
    ) -> Result<Vec<u32>, TokenizerRequestError> {
        let prompt = self.renderer.render(request)?;

        // The rendered prompt already contains its model's special tokens.
        let encoding = self
            .tokenizer
            .encode(prompt, false)
            .map_err(|_| TokenizerRequestError::Encode)?;

        Ok(encoding.get_ids().to_vec())
    }
}

fn read_tokenizer_config(path: &Path) -> Result<TokenizerConfig, ModelTokenizerError> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}
