use axum::http::{
    header::{HeaderName, AUTHORIZATION},
    HeaderMap,
};
use chrono::{DateTime, Utc};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::{
    diagnostics::limited_warn,
    domain::{GatewayAccount, GatewayCredential, GatewayWorkspace, OrganizationStatus},
};

pub(crate) const X_API_KEY: HeaderName = HeaderName::from_static("x-api-key");
const X_GRADIATED_API_KEY: HeaderName = HeaderName::from_static("x-gradiated-api-key");
const MAX_SECRET_BYTES: usize = 4096;

/// `Eval` is grad's eval workers, authenticated by the eval service token: lowest
/// runtime priority, a per-workspace rate limit of their own, and the only
/// callers of eval-only versions.
#[derive(Clone, Copy, Debug, Default, serde::Deserialize, serde::Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Lane {
    #[default]
    Standard,
    Eval,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuthenticatedIdentity {
    pub api_key_id: Uuid,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub lane: Lane,
    /// The grad eval an eval-lane request belongs to, from `X-Gradiated-Eval-Id`.
    pub eval_id: Option<String>,
}

pub(crate) const X_GRADIATED_SOURCE: HeaderName = HeaderName::from_static("x-gradiated-source");
pub(crate) const X_GRADIATED_WORKSPACE: HeaderName =
    HeaderName::from_static("x-gradiated-workspace");
pub(crate) const X_GRADIATED_EVAL_ID: HeaderName = HeaderName::from_static("x-gradiated-eval-id");

/// The bearer tokens grad's eval workers present: the current one and, during a
/// rotation, the previous one. Compared as SHA-256 digests, in constant time.
#[derive(Clone, Default)]
pub struct EvalServiceTokens(Vec<[u8; 32]>);

impl EvalServiceTokens {
    pub fn new<'a>(tokens: impl IntoIterator<Item = &'a str>) -> Self {
        Self(
            tokens
                .into_iter()
                .map(|token| Sha256::digest(token.as_bytes()).into())
                .collect(),
        )
    }

    /// The bearer, when it is an eval service token.
    pub(crate) fn matches(&self, headers: &HeaderMap) -> Result<bool, AuthenticationError> {
        if self.0.is_empty() {
            return Ok(false);
        }

        let Some(value) = single_value(headers, &AUTHORIZATION)? else {
            return Ok(false);
        };
        let Ok(token) = bearer_token(value) else {
            return Ok(false);
        };
        let presented: [u8; 32] = Sha256::digest(token.as_bytes()).into();

        Ok(self.0.iter().fold(false, |matched, expected| {
            let difference = expected
                .iter()
                .zip(presented)
                .fold(0_u8, |bits, (left, right)| bits | (left ^ right));
            matched | (difference == 0)
        }))
    }
}

/// The workspace and eval an eval-service request names; `None` when it is not
/// tagged `X-Gradiated-Source: eval`, which the token is refused without.
pub(crate) fn eval_target(
    headers: &HeaderMap,
) -> Result<Option<(Uuid, Option<String>)>, crate::GatewayError> {
    if single_value(headers, &X_GRADIATED_SOURCE)? != Some("eval") {
        return Ok(None);
    }

    let workspace_id = single_value(headers, &X_GRADIATED_WORKSPACE)?
        .and_then(|value| Uuid::parse_str(value).ok())
        .ok_or_else(|| crate::GatewayError::invalid_request(Some("x-gradiated-workspace")))?;
    let eval_id = single_value(headers, &X_GRADIATED_EVAL_ID)?
        .map(|value| {
            let valid = value.split_once('_').is_some_and(|(prefix, rest)| {
                !prefix.is_empty()
                    && prefix.bytes().all(|byte| byte.is_ascii_lowercase())
                    && (1..=64).contains(&rest.len())
                    && rest.bytes().all(|byte| byte.is_ascii_alphanumeric())
            });
            valid
                .then(|| value.to_owned())
                .ok_or_else(|| crate::GatewayError::invalid_request(Some("x-gradiated-eval-id")))
        })
        .transpose()?;

    Ok(Some((workspace_id, eval_id)))
}

fn is_api_key(key: &str) -> bool {
    key.strip_prefix("grad_").is_some_and(|suffix| {
        !suffix.is_empty()
            && suffix
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    })
}

// Secrets deliberately have no Debug or serialization implementation.
pub struct ApiKey<'a>(&'a str);

impl ApiKey<'_> {
    pub fn digest(&self) -> String {
        format!("{:x}", Sha256::digest(self.0.as_bytes()))
    }
}

fn single_value<'a>(
    headers: &'a HeaderMap,
    name: &HeaderName,
) -> Result<Option<&'a str>, AuthenticationError> {
    let mut values = headers.get_all(name).iter();
    let Some(value) = values.next() else {
        return Ok(None);
    };

    if values.any(|other| other != value) {
        return Err(rejected("conflicting_duplicate_header"));
    }

    value
        .to_str()
        .map(Some)
        .map_err(|_| rejected("unreadable_header"))
}

fn bearer_token(value: &str) -> Result<&str, AuthenticationError> {
    value
        .split_once(' ')
        .filter(|(scheme, _)| scheme.eq_ignore_ascii_case("bearer"))
        .map(|(_, token)| token.trim_matches(' '))
        .ok_or_else(|| rejected("malformed_bearer"))
}

fn checked_secret(value: &str) -> Result<&str, AuthenticationError> {
    let valid = !value.is_empty()
        && value.len() <= MAX_SECRET_BYTES
        && value.bytes().all(|byte| byte.is_ascii_graphic());

    if valid {
        Ok(value)
    } else {
        Err(rejected("malformed_secret"))
    }
}

pub fn extract_api_key(headers: &HeaderMap) -> Result<ApiKey<'_>, AuthenticationError> {
    let workspace = single_value(headers, &X_GRADIATED_API_KEY)?
        .map(checked_secret)
        .transpose()?;
    let bearer = single_value(headers, &AUTHORIZATION)?
        .map(|value| bearer_token(value).and_then(checked_secret))
        .transpose()?;
    let standard = single_value(headers, &X_API_KEY)?
        .map(checked_secret)
        .transpose()?;

    let mut api_key = None;

    for key in [workspace, bearer, standard].into_iter().flatten() {
        if !is_api_key(key) {
            return Err(rejected("unknown_key_namespace"));
        }

        if api_key.is_some_and(|existing| existing != key) {
            return Err(rejected("conflicting_api_keys"));
        }

        api_key = Some(key);
    }

    api_key
        .map(ApiKey)
        .ok_or_else(|| rejected("missing_api_key"))
}

#[cfg(test)]
pub(crate) fn credential_digest(headers: &HeaderMap) -> Result<String, AuthenticationError> {
    Ok(extract_api_key(headers)?.digest())
}

pub fn authenticate_credential(
    credential: GatewayCredential,
    now: DateTime<Utc>,
) -> Result<AuthenticatedIdentity, AuthenticationError> {
    if credential.revoked_at.is_some() {
        return Err(rejected("revoked"));
    }

    if credential
        .expires_at
        .is_some_and(|expires_at| expires_at <= now)
    {
        return Err(rejected("expired"));
    }

    Ok(AuthenticatedIdentity {
        api_key_id: credential.api_key_id,
        organization_id: credential.organization_id,
        workspace_id: credential.workspace_id,
        lane: Lane::Standard,
        eval_id: None,
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

/// The public error never says why a credential failed, so the bounded reason is logged here.
fn rejected(reason: &'static str) -> AuthenticationError {
    limited_warn!(error_code = reason, "credential rejected");

    AuthenticationError::InvalidApiKey
}

impl From<AuthenticationError> for crate::GatewayError {
    fn from(error: AuthenticationError) -> Self {
        match error {
            AuthenticationError::InvalidApiKey => Self::InvalidApiKey,
        }
    }
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
    use chrono::{Duration, TimeZone};

    use super::*;
    use crate::{test_support::TestServingState, GatewayError};

    fn records() -> (GatewayCredential, GatewayWorkspace, GatewayAccount) {
        let state = TestServingState::ready();

        (
            state.credential.unwrap(),
            state.workspace.unwrap(),
            state.account.unwrap(),
        )
    }

    #[test]
    fn the_bearer_scheme_is_case_insensitive() {
        let expected = format!("{:x}", Sha256::digest(b"grad_example"));

        for value in [
            "Bearer grad_example",
            "bearer grad_example",
            "BEARER grad_example",
            "Bearer  grad_example",
        ] {
            let mut headers = HeaderMap::new();
            headers.insert(AUTHORIZATION, value.parse().unwrap());

            assert_eq!(credential_digest(&headers), Ok(expected.clone()), "{value}");
        }
    }

    #[test]
    fn malformed_bearer_values_are_rejected() {
        for value in [
            "grad_example",
            "Basic grad_example",
            "Bearer ",
            "Bearer a b",
            "Bearer grad_a!b",
        ] {
            let mut headers = HeaderMap::new();
            headers.insert(AUTHORIZATION, value.parse().unwrap());

            assert_eq!(
                credential_digest(&headers),
                Err(AuthenticationError::InvalidApiKey),
                "{value}"
            );
        }
    }

    #[test]
    fn revoked_or_elapsed_credentials_are_rejected() {
        let now = Utc.with_ymd_and_hms(2026, 8, 18, 20, 0, 0).unwrap();
        let (credential, _, _) = records();

        let mut revoked = credential.clone();
        revoked.revoked_at = Some(now);
        assert_eq!(
            authenticate_credential(revoked, now),
            Err(AuthenticationError::InvalidApiKey)
        );

        let mut expired = credential.clone();
        expired.expires_at = Some(now);
        assert_eq!(
            authenticate_credential(expired, now),
            Err(AuthenticationError::InvalidApiKey)
        );

        let mut expiring = credential;
        expiring.expires_at = Some(now + Duration::seconds(1));
        assert!(authenticate_credential(expiring, now).is_ok());
    }

    #[test]
    fn every_authentication_failure_is_the_public_invalid_api_key() {
        let mut revoked = records().0;
        revoked.revoked_at = Some(Utc::now());

        for failure in [
            extract_api_key(&HeaderMap::new()).err(),
            authenticate_credential(revoked, Utc::now()).err(),
        ] {
            assert_eq!(
                failure.map(GatewayError::from),
                Some(GatewayError::InvalidApiKey)
            );
        }
    }

    #[test]
    fn access_requires_consistent_active_unarchived_records() {
        let (credential, workspace, account) = records();
        let identity = authenticate_credential(credential, Utc::now()).unwrap();
        let other = Uuid::from_u128(0xdead);

        assert_eq!(
            authorize_access(identity.clone(), &workspace, &account),
            Ok(identity.clone())
        );

        let mut other_workspace = workspace.clone();
        other_workspace.workspace_id = other;
        let mut other_workspace_organization = workspace.clone();
        other_workspace_organization.organization_id = other;
        let mut other_account_organization = account.clone();
        other_account_organization.organization_id = other;
        let mut archived = workspace.clone();
        archived.archived_at = Some(Utc::now());
        let mut suspended = account.clone();
        suspended.organization_status = OrganizationStatus::Suspended;

        for (workspace, account, denial, public) in [
            (
                &other_workspace,
                &account,
                AccessError::InconsistentServingState,
                GatewayError::ServingStateUnavailable,
            ),
            (
                &other_workspace_organization,
                &account,
                AccessError::InconsistentServingState,
                GatewayError::ServingStateUnavailable,
            ),
            (
                &workspace,
                &other_account_organization,
                AccessError::InconsistentServingState,
                GatewayError::ServingStateUnavailable,
            ),
            (
                &archived,
                &account,
                AccessError::WorkspaceArchived,
                GatewayError::WorkspaceArchived,
            ),
            (
                &workspace,
                &suspended,
                AccessError::OrganizationSuspended,
                GatewayError::OrganizationSuspended,
            ),
        ] {
            assert_eq!(
                authorize_access(identity.clone(), workspace, account),
                Err(denial)
            );
            assert_eq!(GatewayError::from(denial), public);
        }
    }
}

#[cfg(test)]
#[path = "auth_credentials_tests.rs"]
mod credential_tests;
