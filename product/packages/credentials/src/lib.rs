use aws_sdk_secretsmanager::Client;

#[derive(Clone, Copy)]
pub enum Provider {
    OpenAi,
    Anthropic,
}

impl Provider {
    fn secret_id(self) -> &'static str {
        match self {
            Self::OpenAi => "gradiated/prod/providers/openai",
            Self::Anthropic => "gradiated/prod/providers/anthropic",
        }
    }
}

#[derive(Debug, thiserror::Error)]
#[error("Cannot load provider credential.")]
pub struct CredentialError;

pub struct CredentialLoader {
    client: Client,
}

impl CredentialLoader {
    pub fn new(client: Client) -> Self {
        Self { client }
    }

    pub async fn load(&self, provider: Provider) -> Result<String, CredentialError> {
        let response = self
            .client
            .get_secret_value()
            .secret_id(provider.secret_id())
            .version_stage("AWSCURRENT")
            .send()
            .await
            .map_err(|_| CredentialError)?;

        active_key(response.secret_string().ok_or(CredentialError)?)
    }
}

fn active_key(value: &str) -> Result<String, CredentialError> {
    let stored: serde_json::Value = serde_json::from_str(value).map_err(|_| CredentialError)?;
    let field = match stored.get("activeSlot").and_then(|slot| slot.as_str()) {
        Some("primary") => "primaryApiKey",
        Some("secondary") => "secondaryApiKey",
        _ => return Err(CredentialError),
    };
    let key = stored
        .get(field)
        .and_then(|key| key.as_str())
        .ok_or(CredentialError)?;

    if key.is_empty() || key.trim() != key {
        return Err(CredentialError);
    }

    Ok(key.to_owned())
}

#[cfg(test)]
mod tests;
