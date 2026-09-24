use axum::http::{
    header::{HeaderName, AUTHORIZATION},
    HeaderMap,
};
use sha2::{Digest, Sha256};

pub const X_API_KEY: HeaderName = HeaderName::from_static("x-api-key");
pub const X_GRADIATED_API_KEY: HeaderName = HeaderName::from_static("x-gradiated-api-key");
const MAX_SECRET_BYTES: usize = 4096;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Provider {
    Anthropic,
    OpenAi,
}

/// OpenAI shares `sk-` with other providers, so only its own formats count.
const KEY_FORMATS: &[(&str, Provider)] = &[
    ("sk-ant-", Provider::Anthropic),
    ("sk-proj-", Provider::OpenAi),
    ("sk-svcacct-", Provider::OpenAi),
    ("sk-admin-", Provider::OpenAi),
    ("sk-None-", Provider::OpenAi),
];

/// OpenAI's older user keys have no infix: `sk-` and 48 characters that contain
/// the marker `T3BlbkFJ`, the base64 of "OpenAI".
fn is_legacy_openai_key(key: &str) -> bool {
    key.strip_prefix("sk-").is_some_and(|rest| {
        rest.len() == 48
            && rest.bytes().all(|byte| byte.is_ascii_alphanumeric())
            && rest.contains("T3BlbkFJ")
    })
}

impl Provider {
    fn from_key(key: &str) -> Option<Self> {
        let known = KEY_FORMATS.iter().find_map(|(prefix, provider)| {
            key.strip_prefix(prefix)
                .filter(|rest| !rest.is_empty())
                .map(|_| *provider)
        });

        known.or_else(|| is_legacy_openai_key(key).then_some(Self::OpenAi))
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Anthropic => "anthropic",
            Self::OpenAi => "openai",
        }
    }
}

fn is_api_key(key: &str) -> bool {
    key.strip_prefix("grad_").is_some_and(|suffix| {
        !suffix.is_empty()
            && suffix
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    })
}

pub struct ApiKey<'a>(&'a str);

impl ApiKey<'_> {
    pub fn digest(&self) -> [u8; 32] {
        Sha256::digest(self.0.as_bytes()).into()
    }
}

pub struct ProviderKey {
    pub provider: Provider,
    pub header: HeaderName,
}

pub struct Credentials<'a> {
    pub api_key: Option<ApiKey<'a>>,
    pub provider: Option<ProviderKey>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
#[error("invalid API key")]
pub struct InvalidCredentials;

pub fn extract(headers: &HeaderMap) -> Result<Credentials<'_>, InvalidCredentials> {
    let workspace = single_value(headers, &X_GRADIATED_API_KEY)?
        .map(checked_secret)
        .transpose()?;
    let bearer = single_value(headers, &AUTHORIZATION)?
        .map(|value| {
            bearer_token(value)
                .ok_or_else(|| rejected("malformed_bearer"))
                .and_then(checked_secret)
        })
        .transpose()?;
    let standard = single_value(headers, &X_API_KEY)?
        .map(checked_secret)
        .transpose()?;

    if workspace.is_some_and(|key| !is_api_key(key)) {
        return Err(rejected("workspace_header_namespace"));
    }

    let mut api_key = workspace;
    let mut provider = None;

    for (header, key) in [(AUTHORIZATION, bearer), (X_API_KEY, standard)] {
        let Some(key) = key else {
            continue;
        };

        if is_api_key(key) {
            if api_key.is_some_and(|existing| existing != key) {
                return Err(rejected("conflicting_api_keys"));
            }

            api_key = Some(key);
        } else if let Some(kind) = Provider::from_key(key) {
            if provider.is_some() {
                return Err(rejected("multiple_provider_keys"));
            }

            provider = Some(ProviderKey {
                provider: kind,
                header,
            });
        } else {
            return Err(rejected("unknown_key_namespace"));
        }
    }

    Ok(Credentials {
        api_key: api_key.map(ApiKey),
        provider,
    })
}

fn single_value<'a>(
    headers: &'a HeaderMap,
    name: &HeaderName,
) -> Result<Option<&'a str>, InvalidCredentials> {
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

pub fn bearer_token(value: &str) -> Option<&str> {
    let (scheme, token) = value.split_once(' ')?;

    scheme
        .eq_ignore_ascii_case("bearer")
        .then(|| token.trim_matches(' '))
}

fn checked_secret(value: &str) -> Result<&str, InvalidCredentials> {
    let valid = !value.is_empty()
        && value.len() <= MAX_SECRET_BYTES
        && value.bytes().all(|byte| byte.is_ascii_graphic());

    if valid {
        Ok(value)
    } else {
        Err(rejected("malformed_secret"))
    }
}

fn rejected(reason: &'static str) -> InvalidCredentials {
    tracing::debug!(error_code = reason, "credential rejected");

    InvalidCredentials
}

#[cfg(test)]
mod tests {
    use super::*;

    fn headers(pairs: &[(&str, &str)]) -> HeaderMap {
        let mut headers = HeaderMap::new();
        for (name, value) in pairs {
            headers.append(
                HeaderName::from_bytes(name.as_bytes()).unwrap(),
                value.parse().unwrap(),
            );
        }

        headers
    }

    fn provider_of(pairs: &[(&str, &str)]) -> Option<Provider> {
        let headers = headers(pairs);

        extract(&headers).unwrap().provider.map(|key| key.provider)
    }

    const LEGACY_OPENAI_KEY: &str = "sk-AAAAAAAAAAAAAAAAAAAAT3BlbkFJBBBBBBBBBBBBBBBBBBBB";

    #[test]
    fn every_known_key_format_names_its_provider_in_either_header() {
        for (key, provider) in [
            ("sk-ant-api03-customer", Provider::Anthropic),
            ("sk-ant-oat01-customer", Provider::Anthropic),
            ("sk-ant-admin01-customer", Provider::Anthropic),
            (
                "sk-ant-api99-a-format-that-does-not-exist-yet",
                Provider::Anthropic,
            ),
            ("sk-proj-customer", Provider::OpenAi),
            ("sk-svcacct-customer", Provider::OpenAi),
            ("sk-admin-customer", Provider::OpenAi),
            ("sk-None-customer", Provider::OpenAi),
            (LEGACY_OPENAI_KEY, Provider::OpenAi),
        ] {
            for (header, value) in [
                ("x-api-key", key.to_owned()),
                ("authorization", format!("Bearer {key}")),
            ] {
                assert_eq!(
                    provider_of(&[(header, &value), ("x-gradiated-api-key", "grad_a")]),
                    Some(provider),
                    "{header}: {key}"
                );
            }
        }

        assert_eq!(provider_of(&[("authorization", "Bearer grad_a")]), None);
    }

    #[test]
    fn a_key_in_no_known_format_is_refused() {
        for key in [
            "sk-or-v1-0123456789abcdef",
            "sk-0123456789abcdef0123456789abcdef",
            "sk-customer",
            "sk-proj-",
            "sk-ant-",
            &LEGACY_OPENAI_KEY.replace("T3BlbkFJ", "XXXXXXXX"),
            &format!("{LEGACY_OPENAI_KEY}A"),
        ] {
            let headers = headers(&[("x-api-key", key), ("x-gradiated-api-key", "grad_a")]);

            assert!(extract(&headers).is_err(), "{key}");
        }
    }

    #[test]
    fn a_gradiated_key_can_arrive_in_any_standard_header() {
        for pairs in [
            &[("authorization", "Bearer grad_a")][..],
            &[("x-api-key", "grad_a")][..],
            &[("x-gradiated-api-key", "grad_a")][..],
            &[
                ("x-gradiated-api-key", "grad_a"),
                ("authorization", "Bearer grad_a"),
            ][..],
        ] {
            let headers = headers(pairs);
            let credentials = extract(&headers).unwrap();
            assert_eq!(
                credentials.api_key.map(|key| key.digest()),
                Some(Sha256::digest(b"grad_a").into())
            );
        }
    }

    #[test]
    fn ambiguous_or_malformed_credentials_are_rejected() {
        let oversized = format!("sk-ant-{}", "a".repeat(MAX_SECRET_BYTES));

        for pairs in [
            &[("authorization", "grad_a")][..],
            &[("authorization", "Basic grad_a")][..],
            &[("authorization", "Bearer ")][..],
            &[("authorization", "Bearer a b")][..],
            &[("x-api-key", "")][..],
            &[("x-api-key", "unknown-namespace")][..],
            &[("x-api-key", "sk-ant-")][..],
            &[("x-gradiated-api-key", "sk-ant-api03-customer")][..],
            &[("x-api-key", "grad_a"), ("x-api-key", "grad_b")][..],
            &[("x-api-key", "grad_a!")][..],
            &[("x-api-key", "sk-ant-api03 customer")][..],
            &[("x-api-key", oversized.as_str())][..],
            &[("x-gradiated-api-key", "grad_a"), ("x-api-key", "grad_b")][..],
            &[
                ("authorization", "Bearer sk-proj-a"),
                ("x-api-key", "sk-ant-api03-b"),
            ][..],
        ] {
            assert!(extract(&headers(pairs)).is_err(), "{pairs:?}");
        }
    }

    #[test]
    fn credential_syntax_is_read_leniently() {
        for (pairs, provider) in [
            (&[("authorization", "bearer grad_a")][..], None),
            (&[("authorization", "BEARER  grad_a ")][..], None),
            (
                &[("x-api-key", "grad_a"), ("x-api-key", "grad_a")][..],
                None,
            ),
            (
                &[
                    ("authorization", "bearer sk-ant-oat01-a"),
                    ("x-api-key", "grad_a"),
                ][..],
                Some(Provider::Anthropic),
            ),
            (
                &[
                    ("x-api-key", "sk-ant-api03-a.b+c/d="),
                    ("authorization", "Bearer grad_a"),
                ][..],
                Some(Provider::Anthropic),
            ),
            (
                &[
                    ("authorization", "Bearer sk-proj-a"),
                    ("authorization", "Bearer sk-proj-a"),
                    ("x-gradiated-api-key", "grad_a"),
                ][..],
                Some(Provider::OpenAi),
            ),
        ] {
            let headers = headers(pairs);
            let credentials = extract(&headers).unwrap_or_else(|_| panic!("{pairs:?}"));

            assert_eq!(
                credentials.api_key.map(|key| key.digest()),
                Some(Sha256::digest(b"grad_a").into()),
                "{pairs:?}"
            );
            assert_eq!(
                credentials.provider.map(|key| key.provider),
                provider,
                "{pairs:?}"
            );
        }
    }

    #[test]
    fn no_credentials_is_not_an_extraction_error() {
        let headers = HeaderMap::new();
        let credentials = extract(&headers).unwrap();

        assert!(credentials.api_key.is_none());
        assert!(credentials.provider.is_none());
    }
}
