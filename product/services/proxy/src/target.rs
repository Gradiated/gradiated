use std::{borrow::Cow, fmt};

use serde::{
    de::{self, IgnoredAny, MapAccess, Visitor},
    Deserializer,
};

pub fn model(body: &[u8]) -> Option<String> {
    let mut deserializer = serde_json::Deserializer::from_slice(body);
    let model = deserializer.deserialize_map(ModelVisitor).ok()?;
    deserializer.end().ok()?;

    model.filter(|model| !model.is_empty())
}

struct ModelVisitor;

impl<'de> Visitor<'de> for ModelVisitor {
    type Value = Option<String>;

    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("a JSON object")
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
        let mut model = None;

        while let Some(key) = map.next_key::<Cow<'de, str>>()? {
            if key != "model" {
                map.next_value::<IgnoredAny>()?;
                continue;
            }

            if model.is_some() {
                return Err(de::Error::duplicate_field("model"));
            }

            model = Some(map.next_value::<Cow<'de, str>>()?.into_owned());
        }

        Ok(model)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_only_the_top_level_model() {
        assert_eq!(
            model(br#"{"messages":[{"model":"inner"}],"model":"claude-sonnet-5"}"#),
            Some("claude-sonnet-5".to_owned())
        );
        assert_eq!(
            model(br#"{"mod\u0065l":"escaped"}"#),
            Some("escaped".to_owned())
        );
    }

    #[test]
    fn leaves_every_doubtful_body_to_the_gateway() {
        for body in [
            &br#"{"max_tokens":16}"#[..],
            &br#"{"model":""}"#[..],
            &br#"{"model":null}"#[..],
            &br#"{"model":["claude-sonnet-5"]}"#[..],
            &br#"{"model":"a","model":"b"}"#[..],
            &br#"{"model":"a","mod\u0065l":"b"}"#[..],
            &br#"{"model":"a"} trailing"#[..],
            &br#"["claude-sonnet-5"]"#[..],
            &b"not json"[..],
            &b""[..],
        ] {
            assert_eq!(model(body), None, "{}", String::from_utf8_lossy(body));
        }
    }
}
