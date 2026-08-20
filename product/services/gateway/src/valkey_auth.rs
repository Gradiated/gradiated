use std::{pin::Pin, time::Duration};

use aws_config::BehaviorVersion;
use aws_credential_types::{provider::ProvideCredentials, Credentials};
use aws_sigv4::{
    http_request::{sign, SignableBody, SignableRequest, SignatureLocation, SigningSettings},
    sign::v4,
};
use futures_util::{stream, Stream};
use redis::{BasicAuth, RedisResult, StreamingCredentialsProvider};
use thiserror::Error;
use tokio::sync::watch;
use tracing::warn;

use crate::ValkeyIamConfig;

const TOKEN_LIFETIME: Duration = Duration::from_secs(15 * 60);
const TOKEN_REFRESH_INTERVAL: Duration = Duration::from_secs(10 * 60);
const TOKEN_REFRESH_RETRY: Duration = Duration::from_secs(30);

#[derive(Clone)]
pub(crate) struct ValkeyIamCredentials {
    credentials: watch::Receiver<BasicAuth>,
}

impl ValkeyIamCredentials {
    pub(crate) async fn start(config: ValkeyIamConfig) -> Result<Self, ValkeyIamError> {
        let sdk_config = aws_config::defaults(BehaviorVersion::latest())
            .region(aws_config::Region::new(config.region.clone()))
            .load()
            .await;
        let provider = sdk_config
            .credentials_provider()
            .ok_or(ValkeyIamError::MissingAwsCredentialsProvider)?;
        let initial = credentials(&config, &provider.provide_credentials().await?)?;
        let (sender, receiver) = watch::channel(initial);

        tokio::spawn(async move {
            let mut next_refresh = TOKEN_REFRESH_INTERVAL;
            loop {
                tokio::time::sleep(next_refresh).await;
                match provider.provide_credentials().await {
                    Ok(aws_credentials) => match credentials(&config, &aws_credentials) {
                        Ok(credentials) => {
                            sender.send_replace(credentials);
                            next_refresh = TOKEN_REFRESH_INTERVAL;
                        }
                        Err(error) => {
                            warn!(%error, "failed to refresh Valkey IAM token");
                            next_refresh = TOKEN_REFRESH_RETRY;
                        }
                    },
                    Err(error) => {
                        warn!(%error, "failed to refresh AWS credentials for Valkey");
                        next_refresh = TOKEN_REFRESH_RETRY;
                    }
                }
            }
        });

        Ok(Self {
            credentials: receiver,
        })
    }
}

impl StreamingCredentialsProvider for ValkeyIamCredentials {
    fn subscribe(&self) -> Pin<Box<dyn Stream<Item = RedisResult<BasicAuth>> + Send + 'static>> {
        let receiver = self.credentials.clone();
        Box::pin(stream::unfold(
            (receiver, true),
            |(mut receiver, initial)| async move {
                if !initial && receiver.changed().await.is_err() {
                    return None;
                }
                let credentials = receiver.borrow().clone();
                Some((Ok(credentials), (receiver, false)))
            },
        ))
    }
}

fn credentials(
    config: &ValkeyIamConfig,
    credentials: &Credentials,
) -> Result<BasicAuth, ValkeyIamError> {
    let unsigned_uri = format!(
        "http://{}/?Action=connect&ResourceType=ServerlessCache&User={}",
        config.cache_name, config.user
    );
    let identity = credentials.clone().into();
    let mut settings = SigningSettings::default();
    settings.signature_location = SignatureLocation::QueryParams;
    settings.expires_in = Some(TOKEN_LIFETIME);
    let signing_params = v4::SigningParams::builder()
        .identity(&identity)
        .region(&config.region)
        .name("elasticache")
        .time(std::time::SystemTime::now())
        .settings(settings)
        .build()
        .map_err(|error| ValkeyIamError::Signing(error.to_string()))?
        .into();
    let signable_request = SignableRequest::new(
        "GET",
        &unsigned_uri,
        std::iter::empty(),
        SignableBody::Bytes(&[]),
    )?;
    let (instructions, _) = sign(signable_request, &signing_params)?.into_parts();
    let mut request = axum::http::Request::builder()
        .uri(&unsigned_uri)
        .body(())
        .map_err(|error| ValkeyIamError::Signing(error.to_string()))?;
    instructions.apply_to_request_http1x(&mut request);
    let token = request
        .uri()
        .to_string()
        .strip_prefix("http://")
        .ok_or_else(|| ValkeyIamError::Signing("signed token has an invalid URI".to_owned()))?
        .to_owned();

    Ok(BasicAuth::new(config.user.clone(), token))
}

#[derive(Debug, Error)]
pub(crate) enum ValkeyIamError {
    #[error("the AWS credentials provider is unavailable")]
    MissingAwsCredentialsProvider,
    #[error("AWS credentials are unavailable: {0}")]
    AwsCredentials(#[from] aws_credential_types::provider::error::CredentialsError),
    #[error("Valkey IAM token signing failed: {0}")]
    Signing(String),
    #[error("Valkey IAM token signing failed: {0}")]
    SigV4(#[from] aws_sigv4::http_request::SigningError),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signs_the_serverless_cache_connection_request() {
        let config = ValkeyIamConfig {
            cache_name: "gradiated-prod".to_owned(),
            region: "us-east-1".to_owned(),
            user: "gradiated-prod-gateway".to_owned(),
        };
        let aws_credentials = Credentials::new(
            "access-key",
            "secret-key",
            Some("session-token".to_owned()),
            None,
            "test",
        );

        let credentials = credentials(&config, &aws_credentials).unwrap();

        assert_eq!(credentials.username(), "gradiated-prod-gateway");
        assert!(credentials.password().starts_with("gradiated-prod/?"));
        assert!(credentials.password().contains("Action=connect"));
        assert!(credentials
            .password()
            .contains("ResourceType=ServerlessCache"));
        assert!(credentials
            .password()
            .contains("User=gradiated-prod-gateway"));
        assert!(credentials.password().contains("X-Amz-Signature="));
        assert!(!credentials.password().contains("secret-key"));
    }
}
