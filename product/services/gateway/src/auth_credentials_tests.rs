use super::*;

fn headers(pairs: &[(&str, &str)]) -> HeaderMap {
    let mut headers = HeaderMap::new();
    for (name, value) in pairs {
        headers.append(
            axum::http::HeaderName::from_bytes(name.as_bytes()).unwrap(),
            value.parse().unwrap(),
        );
    }
    headers
}

#[test]
fn extracts_supported_identity_combinations() {
    let cases = vec![
        (vec![("authorization", "Bearer grad_example")], None),
        (vec![("x-api-key", "grad_example")], None),
        (vec![("x-gradiated-api-key", "grad_example")], None),
        (
            vec![
                ("x-gradiated-api-key", "grad_example"),
                ("authorization", "Bearer sk-proj-example"),
            ],
            Some((Provider::OpenAi, "sk-proj-example")),
        ),
        (
            vec![
                ("x-gradiated-api-key", "grad_example"),
                ("x-api-key", "sk-ant-example"),
            ],
            Some((Provider::Anthropic, "sk-ant-example")),
        ),
        (
            vec![
                ("authorization", "Bearer grad_example"),
                ("x-api-key", "sk-ant-example"),
            ],
            Some((Provider::Anthropic, "sk-ant-example")),
        ),
        (
            vec![
                ("authorization", "Bearer sk-example"),
                ("x-api-key", "grad_example"),
            ],
            Some((Provider::OpenAi, "sk-example")),
        ),
        (
            vec![
                ("x-gradiated-api-key", "grad_example"),
                ("authorization", "Bearer sk-ant-example"),
            ],
            Some((Provider::Anthropic, "sk-ant-example")),
        ),
        (
            vec![
                ("x-gradiated-api-key", "grad_example"),
                ("authorization", "Bearer grad_example"),
            ],
            None,
        ),
        (
            vec![
                ("authorization", "Bearer grad_example"),
                ("x-api-key", "grad_example"),
            ],
            None,
        ),
    ];
    for (pairs, expected) in cases {
        let headers = headers(&pairs);
        let credentials = extract_credentials(&headers).unwrap();
        assert_eq!(credentials.api_key, "grad_example");
        assert_eq!(
            credentials.provider.map(|key| (key.provider, key.secret)),
            expected
        );
        assert_eq!(
            credential_digest(&headers).unwrap(),
            "8c56ca6429a5b2f63cfc1fb8708a52a5b5d61b199680507e42a17de2c2deada3"
        );
    }
}

#[test]
fn rejects_missing_conflicting_or_unknown_identity() {
    let cases = vec![
        vec![],
        vec![("authorization", "Bearer sk-example")],
        vec![("x-gradiated-api-key", "sk-example")],
        vec![("authorization", "Bearer unknown")],
        vec![("authorization", "Bearer grad_")],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer grad_other"),
        ],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer eyJ.token.signature"),
        ],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer sk-"),
        ],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer sk-ant-"),
        ],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer sk-openai"),
            ("x-api-key", "sk-ant-example"),
        ],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer sk-openai"),
            ("x-api-key", "sk-openai"),
        ],
    ];
    for pairs in cases {
        assert!(matches!(
            extract_credentials(&headers(&pairs)),
            Err(AuthenticationError::InvalidApiKey)
        ));
    }
}

#[test]
fn rejects_duplicates_and_malformed_headers() {
    for name in ["authorization", "x-api-key", "x-gradiated-api-key"] {
        let value = if name == "authorization" {
            "Bearer grad_example"
        } else {
            "grad_example"
        };
        assert!(extract_credentials(&headers(&[(name, value), (name, value)])).is_err());
        for malformed in [
            "",
            "grad_example,grad_other",
            "grad_ex ample",
            "grad_example\t",
        ] {
            assert!(extract_credentials(&headers(&[(name, malformed)])).is_err());
        }
    }
    let oversized = format!("grad_{}", "a".repeat(4096));
    assert!(extract_credentials(&headers(&[("x-gradiated-api-key", &oversized)])).is_err());
}

#[test]
fn distinguishes_provider_namespaces() {
    assert!(is_api_key("grad_example"));
    assert!(!is_api_key("sk-example"));
    assert!(is_provider_key("sk-example"));
    assert!(is_provider_key("sk-proj-example"));
    assert!(is_provider_key("sk-ant-example"));
    assert!(!is_provider_key("grad_example"));
    assert!(!is_provider_key("eyJ.token.signature"));
    assert!(!is_provider_key("sk-ant-"));
}
