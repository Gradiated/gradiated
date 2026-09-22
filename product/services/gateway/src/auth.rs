use axum::http::HeaderMap;
#[cfg(test)]
use axum::http::{header::HeaderName, header::AUTHORIZATION};
use chrono::{DateTime, Utc};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::domain::{GatewayAccount, GatewayCredential, GatewayWorkspace, OrganizationStatus};

#[cfg(test)]
const X_API_KEY: HeaderName = HeaderName::from_static("x-api-key");

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuthenticatedIdentity {
    pub api_key_id: Uuid,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Provider {
    OpenAi,
    Anthropic,
}

impl Provider {
    /// Recognizes a key namespace, not whether the provider accepts the key.
    fn from_key(key: &str) -> Option<Self> {
        if key
            .strip_prefix("sk-ant-")
            .is_some_and(|suffix| !suffix.is_empty())
        {
            Some(Self::Anthropic)
        } else if !key.starts_with("sk-ant-")
            && key
                .strip_prefix("sk-")
                .is_some_and(|suffix| !suffix.is_empty())
        {
            Some(Self::OpenAi)
        } else {
            None
        }
    }
}

pub fn is_api_key(key: &str) -> bool {
    key.strip_prefix("grad_")
        .is_some_and(|suffix| !suffix.is_empty())
}

pub fn is_provider_key(key: &str) -> bool {
    Provider::from_key(key).is_some()
}

// Secrets deliberately have no Debug or serialization implementation.
pub struct ProviderCredential<'a> {
    pub provider: Provider,
    pub secret: &'a str,
}

pub struct RequestCredentials<'a> {
    pub api_key: &'a str,
    pub provider: Option<ProviderCredential<'a>>,
}

impl RequestCredentials<'_> {
    pub fn api_key_digest(&self) -> String {
        format!("{:x}", Sha256::digest(self.api_key.as_bytes()))
    }
}

fn single_secret<'a>(
    headers: &'a HeaderMap,
    name: &str,
) -> Result<Option<&'a str>, AuthenticationError> {
    let mut values = headers.get_all(name).iter();
    let Some(value) = values.next() else {
        return Ok(None);
    };

    if values.next().is_some() {
        return Err(AuthenticationError::InvalidApiKey);
    }

    let value = value
        .to_str()
        .map_err(|_| AuthenticationError::InvalidApiKey)?;
    let secret = if name == "authorization" {
        value
            .strip_prefix("Bearer ")
            .ok_or(AuthenticationError::InvalidApiKey)?
    } else {
        value
    };

    if secret.is_empty()
        || secret.len() > 4096
        || secret
            .bytes()
            .any(|b| !b.is_ascii_alphanumeric() && b != b'-' && b != b'_')
    {
        return Err(AuthenticationError::InvalidApiKey);
    }

    Ok(Some(secret))
}

/// Extracts identity from the supported headers. Valkey and the provider still
/// validate their own keys. A route must match the extracted provider before relay.
pub fn extract_credentials(
    headers: &HeaderMap,
) -> Result<RequestCredentials<'_>, AuthenticationError> {
    let workspace = single_secret(headers, "x-gradiated-api-key")?;
    let bearer = single_secret(headers, "authorization")?;
    let standard = single_secret(headers, "x-api-key")?;

    if workspace.is_some_and(|key| !is_api_key(key)) {
        return Err(AuthenticationError::InvalidApiKey);
    }

    let mut api_key = workspace;
    let mut provider = None;

    for key in [bearer, standard].into_iter().flatten() {
        if is_api_key(key) {
            if api_key.is_some_and(|existing| existing != key) {
                return Err(AuthenticationError::InvalidApiKey);
            }

            api_key = Some(key);
        } else if let Some(kind) = Provider::from_key(key) {
            if provider.is_some() {
                return Err(AuthenticationError::InvalidApiKey);
            }

            provider = Some(ProviderCredential {
                provider: kind,
                secret: key,
            });
        } else {
            return Err(AuthenticationError::InvalidApiKey);
        }
    }

    Ok(RequestCredentials {
        api_key: api_key.ok_or(AuthenticationError::InvalidApiKey)?,
        provider,
    })
}

pub fn credential_digest(headers: &HeaderMap) -> Result<String, AuthenticationError> {
    Ok(extract_credentials(headers)?.api_key_digest())
}

pub fn authenticate_credential(
    credential: GatewayCredential,
    now: DateTime<Utc>,
) -> Result<AuthenticatedIdentity, AuthenticationError> {
    if credential.revoked_at.is_some()
        || credential
            .expires_at
            .is_some_and(|expires_at| expires_at <= now)
    {
        return Err(AuthenticationError::InvalidApiKey);
    }

    Ok(AuthenticatedIdentity {
        api_key_id: credential.api_key_id,
        organization_id: credential.organization_id,
        workspace_id: credential.workspace_id,
    })
}

pub fn authorize_access(
    identity: AuthenticatedIdentity,
    workspace: &GatewayWorkspace,
    account: &GatewayAccount,
) -> Result<AuthenticatedIdentity, AccessError> {
    if workspace.workspace_id != identity.workspace_id
        || workspace.organization_id != identity.organization_id
        || account.organization_id != identity.organization_id
    {
        return Err(AccessError::InconsistentServingState);
    }
    if workspace.archived_at.is_some() {
        return Err(AccessError::WorkspaceArchived);
    }
    if account.organization_status != OrganizationStatus::Active {
        return Err(AccessError::OrganizationSuspended);
    }

    Ok(identity)
}

#[derive(Clone, Copy, Debug, Error, Eq, PartialEq)]
pub enum AuthenticationError {
    #[error("invalid API key")]
    InvalidApiKey,
}

impl From<AccessError> for crate::GatewayError {
    fn from(error: AccessError) -> Self {
        match error {
            // A permanent denial must not look like a dependency that may recover.
            AccessError::WorkspaceArchived => Self::WorkspaceArchived,
            AccessError::OrganizationSuspended => Self::OrganizationSuspended,
            AccessError::InconsistentServingState => Self::ServingStateUnavailable,
        }
    }
}

#[derive(Clone, Copy, Debug, Error, Eq, PartialEq)]
pub enum AccessError {
    #[error("serving state identities do not agree")]
    InconsistentServingState,
    #[error("workspace is archived")]
    WorkspaceArchived,
    #[error("organization is suspended")]
    OrganizationSuspended,
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;

    use super::*;
    use crate::domain::{BillingMode, OrganizationKind};

    const API_KEY_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000001);
    const ORGANIZATION_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000002);
    const WORKSPACE_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000003);

    fn credential() -> GatewayCredential {
        GatewayCredential {
            api_key_id: API_KEY_ID,
            organization_id: ORGANIZATION_ID,
            workspace_id: WORKSPACE_ID,
            expires_at: None,
            revoked_at: None,
        }
    }

    #[test]
    fn bearer_header_is_exact_and_digest_does_not_retain_the_secret() {
        let mut headers = HeaderMap::new();
        headers.insert(AUTHORIZATION, "Bearer grad_example".parse().unwrap());
        assert_eq!(
            credential_digest(&headers).unwrap(),
            "8c56ca6429a5b2f63cfc1fb8708a52a5b5d61b199680507e42a17de2c2deada3"
        );

        for value in [
            "grad_example",
            "bearer grad_example",
            "Bearer ",
            "Bearer a b",
        ] {
            let mut headers = HeaderMap::new();
            headers.insert(AUTHORIZATION, value.parse().unwrap());
            assert_eq!(
                credential_digest(&headers),
                Err(AuthenticationError::InvalidApiKey)
            );
        }
    }

    #[test]
    fn repeated_authorization_header_is_rejected() {
        let mut headers = HeaderMap::new();
        headers.append(AUTHORIZATION, "Bearer first".parse().unwrap());
        headers.append(AUTHORIZATION, "Bearer second".parse().unwrap());
        assert_eq!(
            credential_digest(&headers),
            Err(AuthenticationError::InvalidApiKey)
        );
    }

    #[test]
    fn x_api_key_authenticates_with_the_same_digest_as_bearer() {
        let mut headers = HeaderMap::new();
        headers.insert(X_API_KEY, "grad_example".parse().unwrap());
        assert_eq!(
            credential_digest(&headers).unwrap(),
            "8c56ca6429a5b2f63cfc1fb8708a52a5b5d61b199680507e42a17de2c2deada3"
        );

        for value in ["", "a b"] {
            let mut headers = HeaderMap::new();
            headers.insert(X_API_KEY, value.parse().unwrap());
            assert_eq!(
                credential_digest(&headers),
                Err(AuthenticationError::InvalidApiKey)
            );
        }

        let mut headers = HeaderMap::new();
        headers.append(X_API_KEY, "first".parse().unwrap());
        headers.append(X_API_KEY, "second".parse().unwrap());
        assert_eq!(
            credential_digest(&headers),
            Err(AuthenticationError::InvalidApiKey)
        );

        let mut both = HeaderMap::new();
        both.insert(AUTHORIZATION, "Bearer grad_example".parse().unwrap());
        both.insert(X_API_KEY, "grad_example".parse().unwrap());
        assert_eq!(
            credential_digest(&both).unwrap(),
            "8c56ca6429a5b2f63cfc1fb8708a52a5b5d61b199680507e42a17de2c2deada3"
        );
    }

    #[test]
    fn revoked_or_elapsed_credentials_are_rejected() {
        let now = Utc.with_ymd_and_hms(2026, 8, 18, 20, 0, 0).unwrap();
        let mut revoked = credential();
        revoked.revoked_at = Some(now);
        assert_eq!(
            authenticate_credential(revoked, now),
            Err(AuthenticationError::InvalidApiKey)
        );

        let mut expired = credential();
        expired.expires_at = Some(now);
        assert_eq!(
            authenticate_credential(expired, now),
            Err(AuthenticationError::InvalidApiKey)
        );
    }

    #[test]
    fn access_requires_consistent_active_unarchived_records() {
        let identity = authenticate_credential(credential(), Utc::now()).unwrap();
        let workspace = GatewayWorkspace {
            organization_id: ORGANIZATION_ID,
            workspace_id: WORKSPACE_ID,
            archived_at: None,
        };
        let account = GatewayAccount {
            organization_id: ORGANIZATION_ID,
            organization_kind: OrganizationKind::Customer,
            organization_status: OrganizationStatus::Active,
            billing_mode: BillingMode::Prepaid,
            balance: 1,
        };

        assert_eq!(
            authorize_access(identity.clone(), &workspace, &account),
            Ok(identity)
        );
    }
}

#[cfg(test)]
#[path = "auth_credentials_tests.rs"]
mod credential_tests;
