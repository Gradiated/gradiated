use std::{
    collections::HashMap,
    sync::{Arc, Mutex, PoisonError},
    time::Duration,
};

use hf_hub::{
    api::tokio::{Api, ApiBuilder, ApiError},
    Repo, RepoType,
};
use tokio::{sync::OnceCell, time::Instant};

use super::{
    compiled::{CompiledTokenizer, TokenizerArtifacts},
    ModelTokenizerError,
};
use crate::{ModelDeploymentRelease, TokenizerMode};

pub(super) const TOKENIZER_FILE: &str = "tokenizer.json";
pub(super) const TOKENIZER_CONFIG_FILE: &str = "tokenizer_config.json";
const CHAT_TEMPLATE_FILE: &str = "chat_template.jinja";
const LOAD_TIMEOUT: Duration = Duration::from_secs(30);
pub(super) const LOAD_RETRY_BACKOFF: Duration = Duration::from_secs(10);

#[derive(Clone)]
pub struct ModelTokenizer {
    hub: Api,
    pub(super) loaded: Arc<Mutex<HashMap<TokenizerRelease, Arc<TokenizerSlot>>>>,
    pub(super) load_timeout: Duration,
}

#[derive(Default)]
pub(super) struct TokenizerSlot {
    compiled: OnceCell<Arc<CompiledTokenizer>>,
    pub(super) failed_at: Mutex<Option<Instant>>,
}

impl TokenizerSlot {
    fn failed_recently(&self) -> bool {
        self.failed_at
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .is_some_and(|failed_at| failed_at.elapsed() < LOAD_RETRY_BACKOFF)
    }

    fn record_failure(&self) {
        *self
            .failed_at
            .lock()
            .unwrap_or_else(PoisonError::into_inner) = Some(Instant::now());
    }
}

impl ModelTokenizer {
    pub fn new() -> Result<Self, ModelTokenizerError> {
        Ok(Self::with_hub(
            ApiBuilder::from_env().with_progress(false).build()?,
        ))
    }

    pub(super) fn with_hub(hub: Api) -> Self {
        Self {
            hub,
            loaded: Arc::default(),
            load_timeout: LOAD_TIMEOUT,
        }
    }

    #[cfg(test)]
    pub(super) fn seeded(release: &ModelDeploymentRelease, compiled: CompiledTokenizer) -> Self {
        let tokenizer = Self::new().unwrap();
        let slot = TokenizerSlot {
            compiled: OnceCell::new_with(Some(Arc::new(compiled))),
            failed_at: Mutex::default(),
        };
        tokenizer
            .loaded
            .lock()
            .unwrap()
            .insert(TokenizerRelease::from(release), Arc::new(slot));

        tokenizer
    }

    pub(super) async fn tokenizer(
        &self,
        release: &ModelDeploymentRelease,
    ) -> Result<Arc<CompiledTokenizer>, ModelTokenizerError> {
        self.tokenizer_for(TokenizerRelease::from(release)).await
    }

    pub(super) async fn tokenizer_for(
        &self,
        key: TokenizerRelease,
    ) -> Result<Arc<CompiledTokenizer>, ModelTokenizerError> {
        let slot = self
            .loaded
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .entry(key.clone())
            .or_default()
            .clone();

        slot.compiled
            .get_or_try_init(|| self.load_into(&slot, &key))
            .await
            .cloned()
    }

    /// Requests queued behind a failed load fail fast until the backoff ends,
    /// instead of each retrying the hub in turn.
    async fn load_into(
        &self,
        slot: &TokenizerSlot,
        key: &TokenizerRelease,
    ) -> Result<Arc<CompiledTokenizer>, ModelTokenizerError> {
        if slot.failed_recently() {
            return Err(ModelTokenizerError::Backoff);
        }

        let loaded = tokio::time::timeout(self.load_timeout, self.load(key))
            .await
            .unwrap_or(Err(ModelTokenizerError::TimedOut));
        if let Err(error) = &loaded {
            slot.record_failure();
            log_load_failure(key, error);
        }

        loaded
    }

    async fn load(
        &self,
        key: &TokenizerRelease,
    ) -> Result<Arc<CompiledTokenizer>, ModelTokenizerError> {
        let artifacts = self.download(key).await?;
        let mode = key.mode;

        let compiled =
            tokio::task::spawn_blocking(move || CompiledTokenizer::load(&artifacts, mode))
                .await
                .map_err(ModelTokenizerError::Task)??;

        Ok(Arc::new(compiled))
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
        let tokenizer = repository.get(TOKENIZER_FILE).await?;
        let config = repository.get(TOKENIZER_CONFIG_FILE).await?;
        let template = match repository.get(CHAT_TEMPLATE_FILE).await {
            Ok(template) => Some(template),
            Err(ApiError::RequestError(error))
                if error.status().is_some_and(|status| status.as_u16() == 404) =>
            {
                None
            }
            Err(error) => return Err(error.into()),
        };

        Ok(TokenizerArtifacts {
            tokenizer,
            config,
            template,
        })
    }
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub(super) struct TokenizerRelease {
    pub(super) path: String,
    pub(super) revision: String,
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

impl From<&crate::PinnedTokenizer> for TokenizerRelease {
    fn from(pin: &crate::PinnedTokenizer) -> Self {
        Self {
            path: pin.path.clone(),
            revision: pin.revision.clone(),
            mode: None,
        }
    }
}

fn log_load_failure(release: &TokenizerRelease, error: &ModelTokenizerError) {
    crate::diagnostics::limited_error!(
        tokenizer_path = %release.path,
        tokenizer_revision = %release.revision,
        error_code = error.code(),
        error = %error,
        "model tokenizer is unavailable"
    );
}
