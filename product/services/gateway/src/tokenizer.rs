use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    sync::{Arc, RwLock},
};

use hf_chat_template::{ChatTemplate, Error as ChatTemplateError, RenderInput, TokenizerConfig};
use hf_hub::{
    api::tokio::{Api, ApiBuilder, ApiError},
    Repo, RepoType,
};
use serde_json::{Map, Value};
use thiserror::Error;
use tokenizers::Tokenizer;
use tracing::error;

use crate::{
    ChatCompletionRequest, GatewayError, ModelDeploymentRelease, OutputTokenLimit, QualifiedRequest,
};

const TOKENIZER_FILE: &str = "tokenizer.json";
const TOKENIZER_CONFIG_FILE: &str = "tokenizer_config.json";
const CHAT_TEMPLATE_FILE: &str = "chat_template.jinja";

#[derive(Clone, Debug, PartialEq)]
pub struct BoundedRequest {
    pub qualified: QualifiedRequest,
    pub input_tokens: u64,
}

#[derive(Clone)]
pub struct ModelTokenizer {
    hub: Api,
    loaded: Arc<RwLock<HashMap<TokenizerRelease, Arc<CompiledTokenizer>>>>,
}

impl ModelTokenizer {
    pub fn new() -> Result<Self, ModelTokenizerError> {
        Ok(Self {
            hub: ApiBuilder::from_env().with_progress(false).build()?,
            loaded: Arc::new(RwLock::new(HashMap::new())),
        })
    }

    pub async fn enforce(
        &self,
        qualified: QualifiedRequest,
    ) -> Result<BoundedRequest, GatewayError> {
        let tokenizer = self
            .tokenizer(&qualified.deployment.release)
            .await
            .map_err(|source| {
                error!(
                    model_path = %qualified.deployment.release.model_path,
                    tokenizer_path = %qualified.deployment.release.tokenizer_path,
                    tokenizer_revision = %qualified.deployment.release.tokenizer_revision,
                    error = %source,
                    "model tokenizer is unavailable"
                );
                GatewayError::ServingStateUnavailable
            })?;
        let input_tokens = tokenizer
            .count_input_tokens(&qualified.request)
            .map_err(map_request_error)?;
        enforce_bounds(qualified, input_tokens)
    }

    pub async fn preload(
        &self,
        releases: impl IntoIterator<Item = &ModelDeploymentRelease>,
    ) -> Result<(), ModelTokenizerError> {
        for release in releases {
            self.tokenizer(release).await?;
        }
        Ok(())
    }

    async fn tokenizer(
        &self,
        release: &ModelDeploymentRelease,
    ) -> Result<Arc<CompiledTokenizer>, ModelTokenizerError> {
        let key = TokenizerRelease::from(release);
        let cached = {
            let loaded = self
                .loaded
                .read()
                .map_err(|_| ModelTokenizerError::RegistryLock)?;
            loaded.get(&key).cloned()
        };
        if let Some(tokenizer) = cached {
            return Ok(tokenizer);
        }

        let artifacts = self.download(&key).await?;
        let tokenizer = tokio::task::spawn_blocking(move || CompiledTokenizer::load(&artifacts))
            .await
            .map_err(ModelTokenizerError::LoaderTask)??;
        let tokenizer = Arc::new(tokenizer);
        let mut loaded = self
            .loaded
            .write()
            .map_err(|_| ModelTokenizerError::RegistryLock)?;
        Ok(loaded.entry(key).or_insert(tokenizer).clone())
    }

    async fn download(
        &self,
        release: &TokenizerRelease,
    ) -> Result<TokenizerArtifacts, ModelTokenizerError> {
        let repository = self.hub.repo(Repo::with_revision(
            release.path.clone(),
            RepoType::Model,
            release.revision.clone(),
        ));
        let info = repository.info().await?;
        let tokenizer = repository.get(TOKENIZER_FILE).await?;
        let config = repository.get(TOKENIZER_CONFIG_FILE).await?;
        let template = if info
            .siblings
            .iter()
            .any(|file| file.rfilename == CHAT_TEMPLATE_FILE)
        {
            Some(repository.get(CHAT_TEMPLATE_FILE).await?)
        } else {
            None
        };

        Ok(TokenizerArtifacts {
            tokenizer,
            config,
            template,
        })
    }
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct TokenizerRelease {
    path: String,
    revision: String,
}

impl From<&ModelDeploymentRelease> for TokenizerRelease {
    fn from(release: &ModelDeploymentRelease) -> Self {
        Self {
            path: release.tokenizer_path.clone(),
            revision: release.tokenizer_revision.clone(),
        }
    }
}

struct TokenizerArtifacts {
    tokenizer: PathBuf,
    config: PathBuf,
    template: Option<PathBuf>,
}

struct CompiledTokenizer {
    tokenizer: Tokenizer,
    template: ChatTemplate,
}

impl CompiledTokenizer {
    fn load(artifacts: &TokenizerArtifacts) -> Result<Self, ModelTokenizerError> {
        let tokenizer = Tokenizer::from_file(&artifacts.tokenizer)
            .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string()))?;
        let config = read_tokenizer_config(&artifacts.config)?;
        let template = match &artifacts.template {
            Some(path) => {
                let source = fs::read_to_string(path)?;
                ChatTemplate::from_template_and_config(&source, &config)?
            }
            None => ChatTemplate::from_tokenizer_config(&config)?,
        };
        Ok(Self {
            tokenizer,
            template,
        })
    }

    fn count_input_tokens(
        &self,
        request: &ChatCompletionRequest,
    ) -> Result<u64, TokenizerRequestError> {
        let input = render_input(request)?;
        let prompt = self.template.render(&input).map_err(|error| match error {
            ChatTemplateError::TemplateRaised { .. } => TokenizerRequestError::Rejected,
            error => TokenizerRequestError::Render(error.to_string()),
        })?;
        // The rendered HF template already contains its model's special tokens.
        let encoding = self
            .tokenizer
            .encode(prompt, false)
            .map_err(|error| TokenizerRequestError::Encode(error.to_string()))?;
        u64::try_from(encoding.len()).map_err(|_| TokenizerRequestError::CountOverflow)
    }

    #[cfg(test)]
    fn from_bytes(
        tokenizer: &[u8],
        config: &[u8],
        template: Option<&str>,
    ) -> Result<Self, ModelTokenizerError> {
        let tokenizer = Tokenizer::from_bytes(tokenizer)
            .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string()))?;
        let config: TokenizerConfig = serde_json::from_slice(config)?;
        let template = match template {
            Some(source) => ChatTemplate::from_template_and_config(source, &config)?,
            None => ChatTemplate::from_tokenizer_config(&config)?,
        };
        Ok(Self {
            tokenizer,
            template,
        })
    }
}

fn read_tokenizer_config(path: &Path) -> Result<TokenizerConfig, ModelTokenizerError> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}

fn render_input(request: &ChatCompletionRequest) -> Result<RenderInput, TokenizerRequestError> {
    let mut fields: Map<String, Value> = request.parameters.clone();
    fields.insert(
        "messages".to_owned(),
        Value::Array(request.messages.clone()),
    );
    fields.insert("add_generation_prompt".to_owned(), Value::Bool(true));
    serde_json::from_value(Value::Object(fields)).map_err(|_| TokenizerRequestError::InvalidInput)
}

fn map_request_error(error: TokenizerRequestError) -> GatewayError {
    match error {
        TokenizerRequestError::InvalidInput | TokenizerRequestError::Rejected => {
            GatewayError::invalid_request(Some("messages"))
        }
        TokenizerRequestError::Render(_)
        | TokenizerRequestError::Encode(_)
        | TokenizerRequestError::CountOverflow => GatewayError::ServingStateUnavailable,
    }
}

fn enforce_bounds(
    qualified: QualifiedRequest,
    input_tokens: u64,
) -> Result<BoundedRequest, GatewayError> {
    if input_tokens > qualified.max_prompt_tokens {
        return Err(GatewayError::context_length_exceeded("messages"));
    }
    let total_tokens = input_tokens
        .checked_add(qualified.effective_output_tokens)
        .ok_or(GatewayError::ServingStateUnavailable)?;
    if total_tokens > qualified.max_context_tokens {
        let parameter = qualified
            .request
            .output_token_limit()
            .map(OutputTokenLimit::parameter_name)
            .unwrap_or("messages");
        return Err(GatewayError::context_length_exceeded(parameter));
    }
    Ok(BoundedRequest {
        qualified,
        input_tokens,
    })
}

#[derive(Debug, Error)]
pub enum ModelTokenizerError {
    #[error("Hugging Face artifact resolution failed: {0}")]
    Hub(#[from] ApiError),
    #[error("tokenizer artifact I/O failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("tokenizer config is invalid: {0}")]
    Config(#[from] serde_json::Error),
    #[error("chat template is invalid: {0}")]
    Template(#[from] ChatTemplateError),
    #[error("tokenizer is invalid: {0}")]
    Tokenizer(String),
    #[error("tokenizer loader task failed: {0}")]
    LoaderTask(tokio::task::JoinError),
    #[error("tokenizer registry lock is unavailable")]
    RegistryLock,
}

#[derive(Debug, Error, Eq, PartialEq)]
enum TokenizerRequestError {
    #[error("request cannot be represented as chat-template input")]
    InvalidInput,
    #[error("chat template rejected the request")]
    Rejected,
    #[error("chat template rendering failed: {0}")]
    Render(String),
    #[error("tokenization failed: {0}")]
    Encode(String),
    #[error("token count overflowed")]
    CountOverflow,
}

#[cfg(test)]
mod tests {
    use chrono::{TimeZone, Utc};
    use tokenizers::{
        models::wordlevel::WordLevel, pre_tokenizers::whitespace::WhitespaceSplit, Tokenizer,
    };
    use uuid::Uuid;

    use super::*;
    use crate::{
        auth::AuthenticatedIdentity,
        coordinator::RequestMetadata,
        deployment::{DeploymentStatus, GatewayModelDeployment},
        CapturedPricing, InputTokenPrice, OutputTokenPrice, TokenUnit,
    };

    fn tokenizer() -> CompiledTokenizer {
        let vocabulary = [
            ("[UNK]".to_owned(), 0),
            ("<|user|>".to_owned(), 1),
            ("hello".to_owned(), 2),
            ("<|assistant|>".to_owned(), 3),
        ]
        .into_iter()
        .collect();
        let model = WordLevel::builder()
            .vocab(vocabulary)
            .unk_token("[UNK]".to_owned())
            .build()
            .unwrap();
        let mut tokenizer = Tokenizer::new(model);
        tokenizer.with_pre_tokenizer(Some(WhitespaceSplit));
        let encoded = tokenizer.to_string(false).unwrap();
        let config = br#"{
            "chat_template": "{% for message in messages %}<|{{ message.role }}|> {{ message.content }} {% endfor %}{% if add_generation_prompt %}<|assistant|>{% endif %}"
        }"#;
        CompiledTokenizer::from_bytes(encoded.as_bytes(), config, None).unwrap()
    }

    fn request(max_tokens: Option<u64>) -> QualifiedRequest {
        QualifiedRequest {
            metadata: RequestMetadata {
                generation_id: Uuid::nil(),
                received_at: Utc.timestamp_opt(0, 0).unwrap(),
            },
            identity: AuthenticatedIdentity {
                api_key_id: Uuid::nil(),
                organization_id: Uuid::nil(),
                workspace_id: Uuid::nil(),
            },
            deployment: GatewayModelDeployment {
                id: Uuid::nil(),
                status: DeploymentStatus::Available,
                service_url: "http://127.0.0.1:30000".to_owned(),
                release: ModelDeploymentRelease {
                    schema_version: 1,
                    runtime_revision: "runtime".to_owned(),
                    model_path: "model".to_owned(),
                    model_revision: "model-revision".to_owned(),
                    tokenizer_path: "tokenizer".to_owned(),
                    tokenizer_revision: "tokenizer-revision".to_owned(),
                },
            },
            served_release_digest: "sha256:test".to_owned(),
            max_context_tokens: 10,
            max_prompt_tokens: 8,
            effective_output_tokens: max_tokens.unwrap_or(4),
            pricing: CapturedPricing::new(
                &[
                    InputTokenPrice::Prompt {
                        unit: TokenUnit::Token,
                        cost: 0,
                    },
                    InputTokenPrice::CachedPrompt {
                        unit: TokenUnit::Token,
                        cost: 0,
                    },
                ],
                &[OutputTokenPrice::Completion {
                    unit: TokenUnit::Token,
                    cost: 0,
                }],
            )
            .unwrap(),
            request: ChatCompletionRequest {
                model: "model".to_owned(),
                messages: vec![serde_json::json!({"role": "user", "content": "hello"})],
                stream: false,
                max_completion_tokens: max_tokens,
                max_tokens: None,
                parameters: Map::new(),
            },
        }
    }

    #[test]
    fn renders_the_generation_prompt_and_counts_without_retaining_tokens() {
        assert_eq!(
            tokenizer().count_input_tokens(&request(None).request),
            Ok(3)
        );
    }

    #[test]
    fn rejects_malformed_messages_as_caller_input() {
        let mut request = request(None).request;
        request.messages = vec![serde_json::json!({"content": "hello"})];
        assert!(matches!(
            tokenizer().count_input_tokens(&request),
            Err(TokenizerRequestError::InvalidInput)
        ));
    }

    #[test]
    fn enforces_prompt_and_combined_context_bounds() {
        let mut prompt_too_large = request(None);
        prompt_too_large.max_prompt_tokens = 2;
        assert_eq!(
            enforce_bounds(prompt_too_large, 3),
            Err(GatewayError::context_length_exceeded("messages"))
        );

        assert_eq!(
            enforce_bounds(request(Some(8)), 3),
            Err(GatewayError::context_length_exceeded(
                "max_completion_tokens"
            ))
        );

        let bounded = enforce_bounds(request(Some(7)), 3).unwrap();
        assert_eq!(bounded.input_tokens, 3);
    }

    #[tokio::test]
    #[ignore = "downloads the pinned local-model tokenizer from Hugging Face"]
    async fn loads_and_renders_the_pinned_qwen_release() {
        let mut qualified = request(Some(64));
        qualified.max_context_tokens = 131_072;
        qualified.max_prompt_tokens = 131_008;
        qualified.deployment.release.tokenizer_path = "mlx-community/Qwen3-0.6B-4bit".to_owned();
        qualified.deployment.release.tokenizer_revision =
            "73e3e38d981303bc594367cd910ea6eb48349da8".to_owned();
        qualified.request.parameters.insert(
            "tools".to_owned(),
            serde_json::json!([{
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Read the weather",
                    "parameters": {"type": "object", "properties": {}}
                }
            }]),
        );

        let bounded = ModelTokenizer::new()
            .unwrap()
            .enforce(qualified)
            .await
            .unwrap();
        assert!(bounded.input_tokens > 0);
    }

    #[tokio::test]
    #[ignore = "downloads the pinned production Gemma tokenizer from Hugging Face"]
    async fn loads_and_renders_the_pinned_gemma4_release() {
        let mut qualified = request(Some(64));
        qualified.max_context_tokens = 8_192;
        qualified.max_prompt_tokens = 4_096;
        qualified.deployment.release.model_path = "google/gemma-4-31B-it".to_owned();
        qualified.deployment.release.model_revision =
            "b9ea41a2887d8607f594846523f94c6cc75ac8a4".to_owned();
        qualified.deployment.release.tokenizer_path = "google/gemma-4-31B-it".to_owned();
        qualified.deployment.release.tokenizer_revision =
            "b9ea41a2887d8607f594846523f94c6cc75ac8a4".to_owned();

        let bounded = ModelTokenizer::new()
            .unwrap()
            .enforce(qualified)
            .await
            .unwrap();
        assert!(bounded.input_tokens > 0);
    }
}
