use axum::http::{header::AUTHORIZATION, HeaderMap};
use chrono::{DateTime, Utc};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::domain::{GatewayAccount, GatewayCredential, GatewayWorkspace, OrganizationStatus};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuthenticatedIdentity {
    pub api_key_id: Uuid,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
}

pub fn credential_digest(headers: &HeaderMap) -> Result<String, AuthenticationError> {
    let mut values = headers.get_all(AUTHORIZATION).iter();
    let value = values.next().ok_or(AuthenticationError::InvalidApiKey)?;
    if values.next().is_some() {
        return Err(AuthenticationError::InvalidApiKey);
    }
    let value = value
        .to_str()
        .map_err(|_| AuthenticationError::InvalidApiKey)?;
    let secret = value
        .strip_prefix("Bearer ")
        .filter(|secret| {
            !secret.is_empty() && !secret.bytes().any(|byte| byte.is_ascii_whitespace())
        })
        .ok_or(AuthenticationError::InvalidApiKey)?;

    let digest = Sha256::digest(secret.as_bytes());
    Ok(format!("{digest:x}"))
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
