use super::*;
use aws_sdk_secretsmanager::config::{retry::RetryConfig, Credentials, Region};
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[test]
fn rejects_invalid_values_without_exposing_keys() {
    for value in [
        "private-malformed-value",
        "null",
        r#"{"primaryApiKey":"private-key"}"#,
        r#"{"activeSlot":"private-invalid-slot","primaryApiKey":"private-key"}"#,
        r#"{"activeSlot":"primary","secondaryApiKey":"private-key"}"#,
        r#"{"activeSlot":"primary","primaryApiKey":""}"#,
        r#"{"activeSlot":"secondary","secondaryApiKey":" "}"#,
        r#"{"activeSlot":"primary","primaryApiKey":123}"#,
    ] {
        let error = active_key(value).unwrap_err();

        assert_eq!(error.to_string(), "Cannot load provider credential.");
        assert_eq!(format!("{error:?}"), "CredentialError");
    }
}

#[test]
fn does_not_require_a_revoked_inactive_key() {
    assert_eq!(
        active_key(r#"{"activeSlot":"secondary","secondaryApiKey":"next-key"}"#).unwrap(),
        "next-key"
    );
}

#[tokio::test]
async fn reads_current_version_and_observes_manual_rotation() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    let server = tokio::spawn(async move {
        let mut requests = Vec::new();

        for slot in ["primary", "secondary", "error"]
            .into_iter()
            .cycle()
            .take(6)
        {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = Vec::new();
            let mut buffer = [0; 4096];

            loop {
                let n = stream.read(&mut buffer).await.unwrap();
                assert!(n > 0);
                request.extend_from_slice(&buffer[..n]);

                if let Some(end) = request.windows(4).position(|w| w == b"\r\n\r\n") {
                    let headers = String::from_utf8_lossy(&request[..end]).to_lowercase();
                    let length: usize = headers
                        .lines()
                        .find_map(|line| {
                            line.strip_prefix("content-length:")
                                .map(|n| n.trim().parse().unwrap())
                        })
                        .unwrap();

                    if request.len() >= end + 4 + length {
                        requests.push(
                            serde_json::from_slice::<serde_json::Value>(&request[end + 4..])
                                .unwrap(),
                        );
                        break;
                    }
                }
            }

            let stored = serde_json::json!({
                "activeSlot": slot,
                "primaryApiKey": "first-key",
                "secondaryApiKey": "next-key"
            });
            let (status, body) = if slot == "error" {
                (
                    "400 Bad Request",
                    serde_json::json!({
                        "__type": "AccessDeniedException",
                        "Message": "private-provider-value"
                    })
                    .to_string(),
                )
            } else {
                (
                    "200 OK",
                    serde_json::json!({"SecretString": stored.to_string()}).to_string(),
                )
            };
            let response = format!(
                "HTTP/1.1 {status}\r\nContent-Type: application/x-amz-json-1.1\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(), body
            );
            stream.write_all(response.as_bytes()).await.unwrap();
        }

        requests
    });
    let config = aws_sdk_secretsmanager::Config::builder()
        .behavior_version_latest()
        .region(Region::new("us-east-1"))
        .credentials_provider(Credentials::new("test", "test", None, None, "test"))
        .retry_config(RetryConfig::standard().with_max_attempts(1))
        .endpoint_url(endpoint)
        .build();
    let loader = CredentialLoader::new(Client::from_conf(config));

    for provider in [Provider::OpenAi, Provider::Anthropic] {
        let (first, concurrent) = tokio::join!(loader.load(provider), loader.load(provider));
        assert_eq!(first.unwrap(), "first-key");
        assert_eq!(concurrent.unwrap(), "first-key");
        assert_eq!(loader.load(provider).await.unwrap(), "first-key");

        let cache = match provider {
            Provider::OpenAi => &loader.openai,
            Provider::Anthropic => &loader.anthropic,
        };
        cache.lock().await.as_mut().unwrap().expires_at = Instant::now();
        assert_eq!(loader.load(provider).await.unwrap(), "next-key");
        cache.lock().await.as_mut().unwrap().expires_at = Instant::now();
        assert_eq!(
            loader.load(provider).await.unwrap_err().to_string(),
            "Cannot load provider credential."
        );
    }

    for (i, request) in server.await.unwrap().into_iter().enumerate() {
        let provider = if i < 3 {
            Provider::OpenAi
        } else {
            Provider::Anthropic
        };

        assert_eq!(request["SecretId"], provider.secret_id());
        assert_eq!(request["VersionStage"], "AWSCURRENT");
    }

    assert_eq!(
        Provider::Anthropic.secret_id(),
        "gradiated/prod/providers/anthropic"
    );
}
