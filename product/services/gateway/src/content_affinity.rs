use std::{collections::BTreeMap, io};

use serde::{
    ser::{SerializeMap, SerializeSeq},
    Serialize, Serializer,
};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::{protocol::Protocol, session_affinity::CacheKey};

const FALLBACK_CHARACTERS: usize = 8_192;

pub(crate) fn content_key(request: &Value, raw_body: &[u8], protocol: Protocol) -> CacheKey {
    if let Some((system, first)) = opening_messages(request, protocol) {
        let mut writer = HashWriter(Sha256::new());
        writer.0.update(b"opening-messages-v1");
        if serde_json::to_writer(&mut writer, &(system.map(Canonical), Canonical(first))).is_ok() {
            return CacheKey {
                source: "content_messages",
                value: format!("{:x}", writer.0.finalize()),
            };
        }
    }
    let prefix = match std::str::from_utf8(raw_body) {
        Ok(text) => {
            let end = text
                .char_indices()
                .nth(FALLBACK_CHARACTERS)
                .map_or(text.len(), |(index, _)| index);
            &raw_body[..end]
        }
        Err(_) => &raw_body[..raw_body.len().min(FALLBACK_CHARACTERS)],
    };
    let mut hash = Sha256::new();
    hash.update(b"request-prefix-v1");
    hash.update(prefix);
    CacheKey {
        source: "content_prefix_8192",
        value: format!("{:x}", hash.finalize()),
    }
}

fn opening_messages(request: &Value, protocol: Protocol) -> Option<(Option<&Value>, &Value)> {
    let (messages, system) = match protocol {
        Protocol::OpenAiChat => (request.get("messages")?.as_array()?, None),
        Protocol::AnthropicMessages => {
            (request.get("messages")?.as_array()?, request.get("system"))
        }
        Protocol::OpenAiResponses => {
            let input = request.get("input")?;
            let system = request.get("instructions");
            if input.is_string() {
                return Some((system, input));
            }
            (input.as_array()?, system)
        }
    };
    let system = system.filter(|value| !value.is_null()).or_else(|| {
        messages.iter().find(|message| {
            matches!(
                message.get("role").and_then(Value::as_str),
                Some("system" | "developer")
            )
        })
    });
    for message in messages {
        match message.get("role")?.as_str()? {
            "system" | "developer" => continue,
            "user" | "assistant" | "tool" | "function" => return Some((system, message)),
            _ => return None,
        }
    }
    None
}

struct HashWriter(Sha256);
impl io::Write for HashWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0.update(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

struct Canonical<'a>(&'a Value);
impl Serialize for Canonical<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        match self.0 {
            Value::Object(object) => {
                let sorted: BTreeMap<_, _> = object.iter().collect();
                let mut map = serializer.serialize_map(Some(sorted.len()))?;
                for (key, value) in sorted {
                    map.serialize_entry(key, &Canonical(value))?;
                }
                map.end()
            }
            Value::Array(array) => {
                let mut sequence = serializer.serialize_seq(Some(array.len()))?;
                for value in array {
                    sequence.serialize_element(&Canonical(value))?;
                }
                sequence.end()
            }
            value => value.serialize(serializer),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn key(body: &Value) -> CacheKey {
        content_key(
            body,
            &serde_json::to_vec(body).unwrap(),
            Protocol::OpenAiChat,
        )
    }

    #[test]
    fn hashes_opening_system_and_non_system_messages_without_later_turns() {
        let initial = json!({"messages":[{"role":"developer","content":"Rules"},{"role":"user","content":"Question A"}]});
        let growing = json!({"messages":[{"role":"developer","content":"Rules"},{"role":"user","content":"Question A"},{"role":"assistant","content":"Answer"},{"role":"user","content":"Follow-up"}],"temperature":0.3,"metadata":{"dynamic":"ignored"}});
        assert_eq!(key(&initial), key(&growing));
        assert_eq!(key(&initial).source, "content_messages");
        for pointer in ["/messages/0/content", "/messages/1/content"] {
            let mut changed = initial.clone();
            *changed.pointer_mut(pointer).unwrap() = json!("Different");
            assert_ne!(key(&initial), key(&changed));
        }
        let no_system = json!({"messages":[{"role":"user","content":"Question A"}]});
        assert_eq!(key(&no_system).source, "content_messages");
        assert_ne!(key(&initial), key(&no_system));
        let later_unknown = json!({"messages":[{"role":"user","content":"Question A"},{"type":"function_call_output","output":"not part of the opening"}]});
        assert_eq!(key(&no_system), key(&later_unknown));
    }

    #[test]
    fn nested_object_order_does_not_change_the_key() {
        let a: Value = serde_json::from_str(
            r#"{"messages":[{"role":"user","content":[{"type":"text","text":"hello"}]}]}"#,
        )
        .unwrap();
        let b: Value = serde_json::from_str(
            r#"{"messages":[{"content":[{"text":"hello","type":"text"}],"role":"user"}]}"#,
        )
        .unwrap();
        assert_eq!(key(&a), key(&b));
    }

    #[test]
    fn handles_anthropic_and_responses_openings() {
        for (protocol, mut body) in [
            (
                Protocol::AnthropicMessages,
                json!({"system":[{"type":"text","text":"Rules"}],"messages":[{"role":"user","content":"Question"}]}),
            ),
            (
                Protocol::OpenAiResponses,
                json!({"instructions":"Rules","input":[{"role":"user","content":[{"type":"input_text","text":"Question"}]}]}),
            ),
        ] {
            let original = content_key(&body, b"", protocol);
            assert_eq!(original.source, "content_messages");
            let field = if protocol == Protocol::AnthropicMessages {
                "messages"
            } else {
                "input"
            };
            body[field]
                .as_array_mut()
                .unwrap()
                .push(json!({"role":"user","content":"Follow-up"}));
            assert_eq!(original, content_key(&body, b"", protocol));
        }
        assert_eq!(
            content_key(
                &json!({"input":"Question","instructions":"Rules"}),
                b"",
                Protocol::OpenAiResponses
            )
            .source,
            "content_messages"
        );
    }

    #[test]
    fn unknown_shapes_fall_back_to_exactly_8192_unicode_characters() {
        let prefix = "é".repeat(FALLBACK_CHARACTERS);
        let a = format!("{prefix}one");
        let b = format!("{prefix}two");
        for body in [
            json!({}),
            json!({"messages":[{}]}),
            json!({"messages":[{"role":"unknown"}]}),
            json!({"messages":[]}),
        ] {
            let first = content_key(&body, a.as_bytes(), Protocol::OpenAiChat);
            assert_eq!(first.source, "content_prefix_8192");
            assert_eq!(
                first,
                content_key(&body, b.as_bytes(), Protocol::OpenAiChat)
            );
            assert_ne!(
                first,
                content_key(
                    &body,
                    "é".repeat(FALLBACK_CHARACTERS - 1).as_bytes(),
                    Protocol::OpenAiChat
                )
            );
        }
        assert_eq!(
            content_key(&json!({}), &[0xff], Protocol::OpenAiChat).source,
            "content_prefix_8192"
        );
    }
    #[test]
    fn arbitrary_shapes_and_raw_parse_failures_always_produce_a_key() {
        let bodies = [
            Value::Null,
            json!(true),
            json!(42),
            json!("text"),
            json!([]),
            json!({}),
            json!({"messages":null}),
            json!({"messages":42}),
            json!({"messages":"text"}),
            json!({"messages":[null]}),
            json!({"messages":[{}]}),
            json!({"messages":[{"role":7}]}),
            json!({"messages":[{"role":"system"}]}),
            json!({"input":null}),
            json!({"input":{}}),
            json!({"input":[{"type":"function_call_output","output":"text"}]}),
            json!({"input":"", "instructions":null}),
        ];
        for protocol in [
            Protocol::OpenAiChat,
            Protocol::AnthropicMessages,
            Protocol::OpenAiResponses,
        ] {
            for body in &bodies {
                for raw in [b"".as_slice(), b"not JSON", b"{", &[0xff, 0xfe]] {
                    let result = content_key(body, raw, protocol);
                    assert_eq!(result.value.len(), 64);
                    assert!(result.value.bytes().all(|byte| byte.is_ascii_hexdigit()));
                }
            }
        }
        let mut nested = json!("leaf");
        for _ in 0..100 {
            nested = json!({"nested":nested});
        }
        assert_eq!(
            key(&json!({"messages":[{"role":"user","content":nested}]})).source,
            "content_messages"
        );
    }

    #[test]
    fn fallback_includes_the_8192nd_character_and_excludes_the_8193rd() {
        for character in ["a", "é", "😀"] {
            let prefix = character.repeat(FALLBACK_CHARACTERS - 1);
            let inside_a = format!("{prefix}a");
            let inside_b = format!("{prefix}b");
            let get = |text: &str| content_key(&Value::Null, text.as_bytes(), Protocol::OpenAiChat);
            assert_ne!(get(&inside_a), get(&inside_b));
            assert_eq!(get(&inside_a), get(&format!("{inside_a}ignored suffix")));
        }
    }
}
