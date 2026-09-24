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
fn accepts_the_gradiated_key_in_any_standard_header() {
    for pairs in [
        vec![("authorization", "Bearer grad_example")],
        vec![("x-api-key", "grad_example")],
        vec![("x-gradiated-api-key", "grad_example")],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer grad_example"),
        ],
        vec![
            ("authorization", "Bearer grad_example"),
            ("x-api-key", "grad_example"),
        ],
    ] {
        assert_eq!(
            credential_digest(&headers(&pairs)).unwrap(),
            "8c56ca6429a5b2f63cfc1fb8708a52a5b5d61b199680507e42a17de2c2deada3",
            "{pairs:?}"
        );
    }
}

#[test]
fn rejects_missing_conflicting_or_unknown_identity() {
    let cases = vec![
        vec![],
        vec![("authorization", "Bearer sk-example")],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("authorization", "Bearer sk-proj-example"),
        ],
        vec![
            ("x-gradiated-api-key", "grad_example"),
            ("x-api-key", "sk-ant-example"),
        ],
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
            extract_api_key(&headers(&pairs)),
            Err(AuthenticationError::InvalidApiKey)
        ));
    }
}

#[test]
fn rejects_conflicting_duplicates_and_malformed_headers() {
    for name in ["authorization", "x-api-key", "x-gradiated-api-key"] {
        let (value, other) = if name == "authorization" {
            ("Bearer grad_example", "Bearer grad_other")
        } else {
            ("grad_example", "grad_other")
        };
        assert!(extract_api_key(&headers(&[(name, value), (name, value)])).is_ok());
        assert!(extract_api_key(&headers(&[(name, value), (name, other)])).is_err());
        for malformed in [
            "",
            "grad_example,grad_other",
            "grad_ex ample",
            "grad_example\t",
        ] {
            assert!(extract_api_key(&headers(&[(name, malformed)])).is_err());
        }
    }
    let oversized = format!("grad_{}", "a".repeat(4096));
    assert!(extract_api_key(&headers(&[("x-gradiated-api-key", &oversized)])).is_err());
}

#[test]
fn only_the_gradiated_namespace_is_an_api_key() {
    assert!(is_api_key("grad_example"));
    assert!(!is_api_key("grad_"));
    assert!(!is_api_key("sk-example"));
    assert!(!is_api_key("grad_a!b"));
}
