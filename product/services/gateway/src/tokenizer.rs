use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    sync::{Arc, RwLock},
};

use hf_chat_template::{ChatTemplate, Error as ChatTemplateError, RenderInput, TokenizerConfig};
mod deepseek_v41;
use hf_hub::{
    api::tokio::{Api, ApiBuilder, ApiError},
    Repo, RepoType,
};
use serde_json::{Map, Value};
use thiserror::Error;
use tokenizers::Tokenizer;
use tracing::error;

use crate::{
    GatewayError, InferenceRequest, ModelDeploymentRelease, OutputTokenLimit, QualifiedRequest,
    TokenizerMode,
};

const TOKENIZER_FILE: &str = "tokenizer.json";
const TOKENIZER_CONFIG_FILE: &str = "tokenizer_config.json";
const CHAT_TEMPLATE_FILE: &str = "chat_template.jinja";

#[derive(Clone, Debug, PartialEq)]
pub struct BoundedRequest {
    pub qualified: QualifiedRequest,
    /// Present only when the gateway tokenizes the actual native input payload.
    pub input_tokens: Option<u64>,
}

#[derive(Clone)]
pub struct ModelTokenizer {
    hub: Api,
    loaded: Arc<RwLock<HashMap<TokenizerRelease, Arc<CompiledTokenizer>>>>,
}

#[derive(Default)]
pub(crate) struct TokenizerDecodeState {
    ids: Vec<u32>,
    prefix: String,
    prefix_index: usize,
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
        mut qualified: QualifiedRequest,
    ) -> Result<BoundedRequest, GatewayError> {
        let input_ids = self.encode(&qualified).await?;
        let input_tokens =
            u64::try_from(input_ids.len()).map_err(|_| GatewayError::ServingStateUnavailable)?;
        qualified.request.encoded_input_ids = Some(input_ids);

        enforce_bounds(qualified, input_tokens)
    }

    pub async fn count(&self, qualified: &QualifiedRequest) -> Result<u64, GatewayError> {
        let input_ids = self.encode(qualified).await?;

        u64::try_from(input_ids.len()).map_err(|_| GatewayError::ServingStateUnavailable)
    }

    async fn encode(&self, qualified: &QualifiedRequest) -> Result<Vec<u32>, GatewayError> {
        let release = &qualified.deployment.release;
        let tokenizer = self.tokenizer(release).await.map_err(|source| {
            error!(
                model_path = %release.model_path,
                tokenizer_path = %release.tokenizer_path,
                tokenizer_revision = %release.tokenizer_revision,
                error = %source,
                "model tokenizer is unavailable"
            );
            GatewayError::ServingStateUnavailable
        })?;

        // Rendering and tokenizing a long prompt is CPU work that must not hold an
        // async worker other requests are waiting on.
        let request = qualified.request.clone();
        tokio::task::spawn_blocking(move || tokenizer.encode_input(&request))
            .await
            .map_err(|_| GatewayError::ServingStateUnavailable)?
            .map_err(map_request_error)
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

    pub(crate) async fn decode(
        &self,
        release: &ModelDeploymentRelease,
        token_ids: Vec<u32>,
    ) -> Result<String, ModelTokenizerError> {
        let tokenizer = self.tokenizer(release).await?;

        tokio::task::spawn_blocking(move || {
            tokenizer
                .decode(&token_ids)
                .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string()))
        })
        .await
        .map_err(ModelTokenizerError::LoaderTask)?
    }

    pub(crate) async fn decode_step(
        &self,
        release: &ModelDeploymentRelease,
        mut state: TokenizerDecodeState,
        token_id: u32,
    ) -> Result<(TokenizerDecodeState, Option<String>), ModelTokenizerError> {
        let tokenizer = self.tokenizer(release).await?;

        tokio::task::spawn_blocking(move || {
            let chunk = tokenizer
                .decode_step(&mut state, token_id)
                .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string()))?;
            Ok((state, chunk))
        })
        .await
        .map_err(ModelTokenizerError::LoaderTask)?
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
        let mode = key.mode;
        let tokenizer =
            tokio::task::spawn_blocking(move || CompiledTokenizer::load(&artifacts, mode))
                .await
                .map_err(ModelTokenizerError::LoaderTask)??;
        let tokenizer = Arc::new(tokenizer);

        // Two requests can load the same release at once; the first one stored wins.
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
    mode: Option<TokenizerMode>,
}

impl From<&ModelDeploymentRelease> for TokenizerRelease {
    fn from(release: &ModelDeploymentRelease) -> Self {
        Self {
            path: release.tokenizer_path.clone(),
            revision: release.tokenizer_revision.clone(),
            mode: release.tokenizer_mode,
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
    renderer: PromptRenderer,
}

enum PromptRenderer {
    HuggingFace(Box<ChatTemplate>),
    DeepseekV4,
    DeepseekV41,
}

impl CompiledTokenizer {
    fn load(
        artifacts: &TokenizerArtifacts,
        mode: Option<TokenizerMode>,
    ) -> Result<Self, ModelTokenizerError> {
        let tokenizer = Tokenizer::from_file(&artifacts.tokenizer)
            .map_err(|error| ModelTokenizerError::Tokenizer(error.to_string()))?;
        let config = read_tokenizer_config(&artifacts.config)?;
        let renderer = match mode {
            Some(TokenizerMode::DeepseekV4) => PromptRenderer::DeepseekV4,
            Some(TokenizerMode::DeepseekV41) => PromptRenderer::DeepseekV41,
            None => PromptRenderer::HuggingFace(Box::new(match &artifacts.template {
                Some(path) => {
                    let source = fs::read_to_string(path)?;
                    ChatTemplate::from_template_and_config(&source, &config)?
                }
                None => ChatTemplate::from_tokenizer_config(&config)?,
            })),
        };

        Ok(Self {
            tokenizer,
            renderer,
        })
    }

    fn encode_input(&self, request: &InferenceRequest) -> Result<Vec<u32>, TokenizerRequestError> {
        let prompt = match &self.renderer {
            PromptRenderer::HuggingFace(template) => {
                let input = render_input(request)?;
                template.render(&input).map_err(|error| match error {
                    ChatTemplateError::TemplateRaised { .. } => TokenizerRequestError::Rejected,
                    error => TokenizerRequestError::Render(error.to_string()),
                })?
            }
            PromptRenderer::DeepseekV4 => render_deepseek_v4(request)?,
            PromptRenderer::DeepseekV41 => deepseek_v41::render(request)?,
        };

        // The selected renderer already contains its model's special tokens.
        let encoding = self
            .tokenizer
            .encode(prompt, false)
            .map_err(|error| TokenizerRequestError::Encode(error.to_string()))?;

        Ok(encoding.get_ids().to_vec())
    }

    fn decode(&self, token_ids: &[u32]) -> Result<String, TokenizerRequestError> {
        self.tokenizer
            .decode(token_ids, true)
            .map_err(|error| TokenizerRequestError::Decode(error.to_string()))
    }

    fn decode_step(
        &self,
        state: &mut TokenizerDecodeState,
        token_id: u32,
    ) -> Result<Option<String>, TokenizerRequestError> {
        tokenizers::tokenizer::step_decode_stream(
            &self.tokenizer,
            vec![token_id],
            true,
            &mut state.ids,
            &mut state.prefix,
            &mut state.prefix_index,
        )
        .map_err(|error| TokenizerRequestError::Decode(error.to_string()))
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
        let renderer = match template {
            Some(source) => PromptRenderer::HuggingFace(Box::new(
                ChatTemplate::from_template_and_config(source, &config)?,
            )),
            None => {
                PromptRenderer::HuggingFace(Box::new(ChatTemplate::from_tokenizer_config(&config)?))
            }
        };

        Ok(Self {
            tokenizer,
            renderer,
        })
    }
}

fn read_tokenizer_config(path: &Path) -> Result<TokenizerConfig, ModelTokenizerError> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}

fn render_input(request: &InferenceRequest) -> Result<RenderInput, TokenizerRequestError> {
    let mut fields: Map<String, Value> = request.parameters.clone();
    let messages = request
        .messages
        .iter()
        .cloned()
        .map(normalize_chat_template_message)
        .collect::<Result<Vec<_>, _>>()?;
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

const DEEPSEEK_V4_BOS: &str = "<｜begin▁of▁sentence｜>";
const DEEPSEEK_V4_EOS: &str = "<｜end▁of▁sentence｜>";
const DEEPSEEK_V4_USER: &str = "<｜User｜>";
const DEEPSEEK_V4_ASSISTANT: &str = "<｜Assistant｜>";
const DEEPSEEK_V4_CHAT: &str = "</think>";

#[derive(Clone, Copy, Eq, PartialEq)]
enum DeepseekV4Role {
    System,
    Developer,
    User,
    Assistant,
}

struct DeepseekV4Message {
    role: DeepseekV4Role,
    content: String,
}

fn render_deepseek_v4(request: &InferenceRequest) -> Result<String, TokenizerRequestError> {
    let messages = normalize_deepseek_v4_messages(&request.messages)?;
    let mut prompt = String::from(DEEPSEEK_V4_BOS);

    for (index, message) in messages.iter().enumerate() {
        match message.role {
            DeepseekV4Role::System => prompt.push_str(&message.content),
            DeepseekV4Role::Developer | DeepseekV4Role::User => {
                prompt.push_str(DEEPSEEK_V4_USER);
                prompt.push_str(&message.content);
            }
            DeepseekV4Role::Assistant => {
                prompt.push_str(&message.content);
                prompt.push_str(DEEPSEEK_V4_EOS);
            }
        }

        let next_role = messages.get(index + 1).map(|next| next.role);
        if matches!(
            message.role,
            DeepseekV4Role::Developer | DeepseekV4Role::User
        ) && (next_role.is_none() || next_role == Some(DeepseekV4Role::Assistant))
        {
            prompt.push_str(DEEPSEEK_V4_ASSISTANT);
            prompt.push_str(DEEPSEEK_V4_CHAT);
        }
    }

    Ok(prompt)
}

fn normalize_deepseek_v4_messages(
    messages: &[Value],
) -> Result<Vec<DeepseekV4Message>, TokenizerRequestError> {
    let mut normalized: Vec<DeepseekV4Message> = Vec::with_capacity(messages.len());

    for message in messages {
        let object = message
            .as_object()
            .ok_or(TokenizerRequestError::InvalidInput)?;
        let role = object
            .get("role")
            .and_then(Value::as_str)
            .ok_or(TokenizerRequestError::InvalidInput)?;
        let content = deepseek_v4_content(object.get("content"))?;

        match role {
            "system" => normalized.push(DeepseekV4Message {
                role: DeepseekV4Role::System,
                content,
            }),
            "developer" => {
                if content.is_empty() {
                    return Err(TokenizerRequestError::Rejected);
                }
                normalized.push(DeepseekV4Message {
                    role: DeepseekV4Role::Developer,
                    content,
                });
            }
            "user" => merge_deepseek_v4_user_content(&mut normalized, content),
            "tool" => merge_deepseek_v4_user_content(
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
                normalized.push(DeepseekV4Message {
                    role: DeepseekV4Role::Assistant,
                    content,
                });
            }
            _ => return Err(TokenizerRequestError::Rejected),
        }
    }

    Ok(normalized)
}

fn merge_deepseek_v4_user_content(messages: &mut Vec<DeepseekV4Message>, content: String) {
    if let Some(previous) = messages.last_mut() {
        if previous.role == DeepseekV4Role::User {
            previous.content.push_str("\n\n");
            previous.content.push_str(&content);
            return;
        }
    }
    messages.push(DeepseekV4Message {
        role: DeepseekV4Role::User,
        content,
    });
}

fn deepseek_v4_content(value: Option<&Value>) -> Result<String, TokenizerRequestError> {
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

fn map_request_error(error: TokenizerRequestError) -> GatewayError {
    match error {
        TokenizerRequestError::InvalidParameter(param) => {
            GatewayError::invalid_request(Some(param))
        }
        TokenizerRequestError::InvalidInput | TokenizerRequestError::Rejected => {
            GatewayError::invalid_request(Some("messages"))
        }
        TokenizerRequestError::Render(_)
        | TokenizerRequestError::Encode(_)
        | TokenizerRequestError::Decode(_) => GatewayError::ServingStateUnavailable,
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
        input_tokens: Some(input_tokens),
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
    #[error("invalid request parameter: {0}")]
    InvalidParameter(&'static str),
    #[error("request cannot be represented as chat-template input")]
    InvalidInput,
    #[error("chat template rejected the request")]
    Rejected,
    #[error("chat template rendering failed: {0}")]
    Render(String),
    #[error("tokenization failed: {0}")]
    Encode(String),
    #[error("detokenization failed: {0}")]
    Decode(String),
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

    fn tool_continuation_tokenizer() -> CompiledTokenizer {
        let vocabulary = [("[UNK]".to_owned(), 0)].into_iter().collect();
        let model = WordLevel::builder()
            .vocab(vocabulary)
            .unk_token("[UNK]".to_owned())
            .build()
            .unwrap();
        let tokenizer = Tokenizer::new(model).to_string(false).unwrap();
        let config = br#"{
            "chat_template": "{% for message in messages %}{% if message.tool_calls %}{% for call in message.tool_calls %}{% for key, value in call.function.arguments.items() %}{{ key }}={{ value }}{% endfor %}{% endfor %}{% else %}{{ message.content }}{% endif %}{% endfor %}"
        }"#;
        CompiledTokenizer::from_bytes(tokenizer.as_bytes(), config, None).unwrap()
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
                provider: "local".to_owned(),
                region: "local".to_owned(),
                fault_domain: "local:runtime-1".to_owned(),
                service_url: "http://127.0.0.1:30000".to_owned(),
                release: ModelDeploymentRelease {
                    schema_version: 1,
                    runtime_revision: "runtime".to_owned(),
                    protocol: None,
                    model_path: "model".to_owned(),
                    model_revision: "model-revision".to_owned(),
                    runtime_model_name: None,
                    tokenizer_path: "tokenizer".to_owned(),
                    tokenizer_revision: "tokenizer-revision".to_owned(),
                    tokenizer_mode: None,
                },
            },
            model_deployments: Vec::new(),
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
            request: InferenceRequest {
                model: "model".to_owned(),
                messages: vec![serde_json::json!({"role": "user", "content": "hello"})],
                stream: false,
                service_tier: crate::ServiceTier::Default,
                session_id: None,
                max_completion_tokens: max_tokens,
                max_tokens: None,
                parameters: Map::new(),
                encoded_input_ids: None,
                decision: None,
            },
        }
    }

    #[test]
    fn renders_and_retains_the_exact_generation_prompt_tokens() {
        assert_eq!(
            tokenizer()
                .encode_input(&request(None).request)
                .map(|ids| ids.len()),
            Ok(3)
        );
    }

    #[test]
    fn rejects_malformed_messages_as_caller_input() {
        let mut request = request(None).request;
        request.messages = vec![serde_json::json!({"content": "hello"})];
        assert!(matches!(
            tokenizer().encode_input(&request),
            Err(TokenizerRequestError::InvalidInput)
        ));
    }

    #[test]
    fn renders_openai_tool_call_arguments_in_follow_up_requests() {
        let mut chat = request(None).request;
        chat.messages = vec![
            serde_json::json!({"role": "user", "content": "List the files."}),
            serde_json::json!({
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
            serde_json::json!({
                "role": "tool",
                "tool_call_id": "call_test",
                "content": "Permission denied"
            }),
        ];

        assert!(tool_continuation_tokenizer().encode_input(&chat).is_ok());
        assert_eq!(
            chat.messages[1]["tool_calls"][0]["function"]["arguments"],
            "{\"command\":\"ls -la\"}"
        );
    }

    #[test]
    fn rejects_invalid_tool_call_argument_json() {
        let mut chat = request(None).request;
        chat.messages = vec![serde_json::json!({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "type": "function",
                "function": {"name": "bash", "arguments": "{"}
            }]
        })];

        assert!(matches!(
            tool_continuation_tokenizer().encode_input(&chat),
            Err(TokenizerRequestError::InvalidInput)
        ));
    }

    #[test]
    fn renders_the_deepseek_v4_chat_mode_prompt() {
        let mut chat = request(None).request;
        chat.messages = vec![
            serde_json::json!({"role": "system", "content": "Be concise."}),
            serde_json::json!({"role": "user", "content": "Hello"}),
            serde_json::json!({"role": "assistant", "content": "Hi"}),
            serde_json::json!({"role": "user", "content": "Continue"}),
        ];

        assert_eq!(
            render_deepseek_v4(&chat),
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
    fn merges_deepseek_v4_user_and_tool_result_messages() {
        let mut chat = request(None).request;
        chat.messages = vec![
            serde_json::json!({"role": "user", "content": "First"}),
            serde_json::json!({"role": "user", "content": "Second"}),
            serde_json::json!({"role": "tool", "content": "Result"}),
        ];

        assert_eq!(
            render_deepseek_v4(&chat),
            Ok(concat!(
                "<｜begin▁of▁sentence｜>",
                "<｜User｜>First\n\nSecond\n\n<tool_result>Result</tool_result>",
                "<｜Assistant｜></think>"
            )
            .to_owned())
        );
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
        assert_eq!(bounded.input_tokens, Some(3));
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
        assert!(bounded.input_tokens.is_some_and(|count| count > 0));
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
        assert!(bounded.input_tokens.is_some_and(|count| count > 0));
    }

    #[tokio::test]
    #[ignore = "downloads the pinned production GLM tokenizer from Hugging Face"]
    async fn loads_and_renders_the_pinned_glm_tool_continuation() {
        let mut qualified = request(Some(64));
        qualified.max_context_tokens = 1_048_576;
        qualified.max_prompt_tokens = 1_048_512;
        qualified.deployment.release.model_path = "zai-org/GLM-5.3-Flash".to_owned();
        qualified.deployment.release.model_revision =
            "84c6a6aa9497188e15a635ba793b0f95a79b1033".to_owned();
        qualified.deployment.release.tokenizer_path = "zai-org/GLM-5.3-Flash".to_owned();
        qualified.deployment.release.tokenizer_revision =
            "84c6a6aa9497188e15a635ba793b0f95a79b1033".to_owned();
        qualified.request.messages = vec![
            serde_json::json!({"role": "user", "content": "List the files."}),
            serde_json::json!({
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
            serde_json::json!({
                "role": "tool",
                "tool_call_id": "call_test",
                "content": "Permission denied"
            }),
        ];
        qualified.request.parameters.insert(
            "tools".to_owned(),
            serde_json::json!([{
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

        let bounded = ModelTokenizer::new()
            .unwrap()
            .enforce(qualified)
            .await
            .unwrap();
        assert!(bounded.input_tokens.is_some_and(|count| count > 0));
    }

    #[tokio::test]
    #[ignore = "downloads the pinned production DeepSeek V4 tokenizer from Hugging Face"]
    async fn loads_and_renders_the_pinned_deepseek_v4_release() {
        let mut qualified = request(Some(64));
        qualified.max_context_tokens = 262_144;
        qualified.max_prompt_tokens = 262_080;
        qualified.deployment.release.model_path = "deepseek-ai/DeepSeek-V4-Flash-0731".to_owned();
        qualified.deployment.release.model_revision =
            "7872f01b1d1fe23eabc4c98b48bffcef5a386062".to_owned();
        qualified.deployment.release.tokenizer_path =
            "deepseek-ai/DeepSeek-V4-Flash-0731".to_owned();
        qualified.deployment.release.tokenizer_revision =
            "7872f01b1d1fe23eabc4c98b48bffcef5a386062".to_owned();
        qualified.deployment.release.tokenizer_mode = Some(TokenizerMode::DeepseekV4);
        qualified.request.messages = vec![
            serde_json::json!({"role": "system", "content": "Be concise."}),
            serde_json::json!({"role": "user", "content": "Hello"}),
            serde_json::json!({"role": "assistant", "content": "Hi"}),
            serde_json::json!({"role": "user", "content": "Continue"}),
        ];

        let bounded = ModelTokenizer::new()
            .unwrap()
            .enforce(qualified)
            .await
            .unwrap();
        assert_eq!(bounded.input_tokens, Some(14));
        assert_eq!(
            bounded.qualified.request.encoded_input_ids,
            Some(vec![
                0, 7153, 47468, 16, 128_803, 19_923, 128_804, 128_822, 23_166, 1, 128_803, 56_761,
                128_804, 128_822,
            ])
        );
    }
}
