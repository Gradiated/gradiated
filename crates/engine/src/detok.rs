use tokenizers::Tokenizer;

/// Incremental detokenizer (the TGI/vLLM prefix-window algorithm): emits text
/// only once it is unambiguous (multi-token unicode sequences buffer until
/// complete). Costs two small decodes per token — only paid by streaming
/// clients, never by the engine loop.
pub struct IncrementalDecoder {
    ids: Vec<u32>,
    prefix_offset: usize,
    read_offset: usize,
}

impl IncrementalDecoder {
    pub fn new() -> Self {
        Self {
            ids: vec![],
            prefix_offset: 0,
            read_offset: 0,
        }
    }

    pub fn push(&mut self, tok: u32, tokenizer: &Tokenizer) -> Option<String> {
        self.ids.push(tok);
        let prefix = tokenizer
            .decode(&self.ids[self.prefix_offset..self.read_offset], false)
            .ok()?;
        let full = tokenizer
            .decode(&self.ids[self.prefix_offset..], false)
            .ok()?;
        if full.len() > prefix.len() && !full.ends_with('\u{FFFD}') {
            let new = full[prefix.len()..].to_string();
            self.prefix_offset = self.read_offset;
            self.read_offset = self.ids.len();
            Some(new)
        } else {
            None
        }
    }
}

/// Chat formatting. A hardcoded per-family table instead of a Jinja engine:
/// we host known OS models; a template interpreter is abstraction tax.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ChatTemplate {
    ChatMl,
    None,
}

impl ChatTemplate {
    pub fn detect(model_dir: &std::path::Path) -> Self {
        let raw = std::fs::read_to_string(model_dir.join("tokenizer_config.json")).unwrap_or_default();
        if raw.contains("im_start") {
            ChatTemplate::ChatMl
        } else {
            ChatTemplate::None
        }
    }

    pub fn render(&self, msgs: &[(String, String)]) -> String {
        match self {
            ChatTemplate::ChatMl => {
                let mut s = String::new();
                for (role, content) in msgs {
                    s.push_str(&format!("<|im_start|>{role}\n{content}<|im_end|>\n"));
                }
                s.push_str("<|im_start|>assistant\n");
                s
            }
            ChatTemplate::None => msgs
                .iter()
                .map(|(_, c)| c.as_str())
                .collect::<Vec<_>>()
                .join("\n"),
        }
    }
}
