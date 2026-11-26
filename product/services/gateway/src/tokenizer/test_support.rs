use std::{
    fs,
    future::pending,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
};

use axum::{http::StatusCode, response::IntoResponse, Router};
use hf_hub::{api::tokio::ApiBuilder, Cache, Repo, RepoType};
use tokenizers::{
    decoders::{bpe::BPEDecoder, byte_fallback::ByteFallback},
    models::{
        bpe::{Vocab, BPE},
        wordlevel::WordLevel,
    },
    pre_tokenizers::whitespace::WhitespaceSplit,
    Tokenizer,
};
use uuid::Uuid;

use crate::coordinator::LocalCapacity;

use super::{
    compiled::CompiledTokenizer,
    registry::{TIKTOKEN_FILE, TOKENIZER_CONFIG_FILE, TOKENIZER_FILE},
    ModelTokenizer,
};
use crate::{
    auth::AuthenticatedIdentity, generation::fixtures::token_prices, routing, test_support,
    ModelDeploymentRelease, QualifiedRequest,
};

pub(crate) const TOKEN_H: u32 = 0;
pub(crate) const TOKEN_I: u32 = 1;
pub(crate) const E_ACUTE: [u32; 2] = [2, 3];

pub(super) const TEMPLATE: &str = "{% for message in messages %}<|{{ message.role }}|> {{ message.content }} {% endfor %}{% if add_generation_prompt %}<|assistant|>{% endif %}";
pub(super) const VOCABULARY: [&str; 4] = ["[UNK]", "<|user|>", "hello", "<|assistant|>"];

const BYTE_FALLBACK_VOCABULARY: [&str; 4] = ["h", "i", "<0xC3>", "<0xA9>"];
const SUFFIX_VOCABULARY: [&str; 2] = ["a</w>b</w>", "c"];

pub(super) fn chat_tokenizer() -> CompiledTokenizer {
    word_level(&VOCABULARY, TEMPLATE)
}

pub(super) fn tool_continuation_tokenizer() -> CompiledTokenizer {
    word_level(
        &["[UNK]"],
        "{% for message in messages %}{% if message.tool_calls %}{% for call in message.tool_calls %}{% for key, value in call.function.arguments.items() %}{{ key }}={{ value }}{% endfor %}{% endfor %}{% else %}{{ message.content }}{% endif %}{% endfor %}",
    )
}

pub(super) fn qualified(max_tokens: Option<u64>) -> QualifiedRequest {
    QualifiedRequest {
        is_verification: false,
        adapter: None,
        metadata: test_support::metadata(),
        identity: AuthenticatedIdentity {
            api_key_id: test_support::API_KEY_ID,
            organization_id: test_support::ORGANIZATION_ID,
            workspace_id: test_support::WORKSPACE_ID,
        },
        local: Some(LocalCapacity {
            deployment: routing::fixtures::deployment(0),
            deployments: Vec::new(),
            release_digest: "sha256:test".to_owned(),
        }),
        base: None,
        external: None,
        tokenizer: None,
        max_context_tokens: 10,
        max_prompt_tokens: 8,
        effective_output_tokens: max_tokens.unwrap_or(4),
        pricing: token_prices(0, 0, 0),
        request: serde_json::from_value(serde_json::json!({
            "model": "model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_completion_tokens": max_tokens,
        }))
        .unwrap(),
    }
}

pub(super) fn word_level(vocabulary: &[&str], chat_template: &str) -> CompiledTokenizer {
    CompiledTokenizer::from_tokenizer(word_level_tokenizer(vocabulary), chat_template).unwrap()
}

fn word_level_tokenizer(vocabulary: &[&str]) -> Tokenizer {
    let model = WordLevel::builder()
        .vocab(ids(vocabulary))
        .unk_token(vocabulary[0].to_owned())
        .build()
        .unwrap();
    let mut tokenizer = Tokenizer::new(model);
    tokenizer.with_pre_tokenizer(Some(WhitespaceSplit));

    tokenizer
}

/// A tokenizer whose `é` spans two byte tokens, so decoding it takes two steps.
pub(crate) fn byte_fallback(release: &ModelDeploymentRelease) -> ModelTokenizer {
    let model = BPE::builder()
        .vocab_and_merges(ids(&BYTE_FALLBACK_VOCABULARY), Vec::new())
        .byte_fallback(true)
        .build()
        .unwrap();
    let mut tokenizer = Tokenizer::new(model);
    tokenizer.with_decoder(Some(ByteFallback::new()));

    let compiled = CompiledTokenizer::from_tokenizer(tokenizer, "").unwrap();
    ModelTokenizer::seeded(release, compiled)
}

/// A tokenizer whose second token rewrites the text already decoded for the
/// first, so incremental decoding fails on that token.
pub(crate) fn rewriting_prefix(release: &ModelDeploymentRelease) -> ModelTokenizer {
    let model = BPE::builder()
        .vocab_and_merges(ids(&SUFFIX_VOCABULARY), Vec::new())
        .build()
        .unwrap();
    let mut tokenizer = Tokenizer::new(model);
    tokenizer.with_decoder(Some(BPEDecoder::new("</w>".to_owned())));

    let compiled = CompiledTokenizer::from_tokenizer(tokenizer, "").unwrap();
    ModelTokenizer::seeded(release, compiled)
}

/// A tokenizer registry whose hub refuses every connection.
pub(crate) fn unavailable() -> ModelTokenizer {
    with_hub("http://127.0.0.1:1".to_owned(), &unique_cache())
}

/// A Hugging Face hub stand-in that answers every request with one status.
pub(crate) struct Hub {
    pub(crate) tokenizer: ModelTokenizer,
    cache: PathBuf,
    requests: Arc<AtomicUsize>,
}

impl Hub {
    pub(crate) async fn answering(status: StatusCode) -> Self {
        Self::start(Some(status)).await
    }

    pub(crate) async fn silent() -> Self {
        Self::start(None).await
    }

    async fn start(status: Option<StatusCode>) -> Self {
        let requests = Arc::new(AtomicUsize::new(0));
        let counted = requests.clone();
        let router = Router::new().fallback(move || {
            counted.fetch_add(1, Ordering::SeqCst);
            async move {
                match status {
                    Some(status) => status.into_response(),
                    None => pending().await,
                }
            }
        });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });

        let cache = unique_cache();

        Self {
            tokenizer: with_hub(endpoint, &cache),
            cache,
            requests,
        }
    }

    pub(super) fn cache_release(&self, release: &ModelDeploymentRelease) {
        let commit = "0123456789abcdef0123456789abcdef01234567";
        let repository = Cache::new(self.cache.clone()).repo(Repo::with_revision(
            release.tokenizer_path.clone(),
            RepoType::Model,
            release.tokenizer_revision.clone(),
        ));
        repository.create_ref(commit).unwrap();

        let snapshot = repository.pointer_path(commit);
        fs::create_dir_all(&snapshot).unwrap();
        word_level_tokenizer(&VOCABULARY)
            .save(snapshot.join(TOKENIZER_FILE), false)
            .unwrap();
        fs::write(
            snapshot.join(TOKENIZER_CONFIG_FILE),
            serde_json::json!({ "chat_template": TEMPLATE }).to_string(),
        )
        .unwrap();
    }

    pub(crate) fn cache_kimi_release(&self, path: &str, revision: &str) {
        use base64::{engine::general_purpose::STANDARD, Engine as _};

        let commit = "0123456789abcdef0123456789abcdef01234567";
        let repository = Cache::new(self.cache.clone()).repo(Repo::with_revision(
            path.to_owned(),
            RepoType::Model,
            revision.to_owned(),
        ));
        repository.create_ref(commit).unwrap();

        let snapshot = repository.pointer_path(commit);
        fs::create_dir_all(&snapshot).unwrap();

        let lines: Vec<String> = (0u8..=255)
            .map(|byte| format!("{} {byte}", STANDARD.encode([byte])))
            .collect();
        fs::write(snapshot.join(TIKTOKEN_FILE), lines.join("\n")).unwrap();
        fs::write(
            snapshot.join(TOKENIZER_CONFIG_FILE),
            serde_json::json!({
                "tokenizer_class": "TikTokenTokenizer",
                "auto_map": {
                    "AutoTokenizer": ["tokenization_kimi.TikTokenTokenizer", null]
                },
                "added_tokens_decoder": {
                    "256": { "content": "[BOS]" },
                    "257": { "content": "[EOS]" },
                    "258": { "content": "<|end_of_msg|>" },
                    "259": { "content": "<|open|>" },
                    "260": { "content": "<|close|>" },
                    "261": { "content": "<|sep|>" }
                }
            })
            .to_string(),
        )
        .unwrap();
    }

    pub(crate) fn requests(&self) -> usize {
        self.requests.load(Ordering::SeqCst)
    }
}

impl Drop for Hub {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.cache);
    }
}

fn with_hub(endpoint: String, cache: &Path) -> ModelTokenizer {
    let hub = ApiBuilder::new()
        .with_endpoint(endpoint)
        .with_cache_dir(cache.to_owned())
        .with_token(None)
        .with_progress(false)
        .build()
        .unwrap();

    ModelTokenizer::with_hub(hub)
}

fn unique_cache() -> PathBuf {
    std::env::temp_dir().join(format!("gateway-hub-{}", Uuid::now_v7()))
}

fn ids(vocabulary: &[&str]) -> Vocab {
    vocabulary
        .iter()
        .zip(0..)
        .map(|(token, id)| ((*token).to_owned(), id))
        .collect()
}
