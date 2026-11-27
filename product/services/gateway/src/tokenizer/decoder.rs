use std::sync::Arc;

use super::{compiled::CompiledTokenizer, ModelTokenizerError};

pub(crate) struct TokenDecoder {
    tokenizer: Arc<CompiledTokenizer>,
    ids: Vec<u32>,
    prefix: String,
    prefix_index: usize,
}

impl TokenDecoder {
    pub(super) fn new(tokenizer: Arc<CompiledTokenizer>) -> Self {
        Self {
            tokenizer,
            ids: Vec::new(),
            prefix: String::new(),
            prefix_index: 0,
        }
    }

    pub(crate) async fn decode(self, token_ids: Vec<u32>) -> Result<String, ModelTokenizerError> {
        let tokenizer = self.tokenizer;

        tokio::task::spawn_blocking(move || tokenizer.decode(&token_ids))
            .await
            .map_err(ModelTokenizerError::Task)?
    }

    pub(crate) fn step(&mut self, token_id: u32) -> Result<Option<String>, ModelTokenizerError> {
        self.tokenizer.step_decode(
            token_id,
            &mut self.ids,
            &mut self.prefix,
            &mut self.prefix_index,
        )
    }
}
