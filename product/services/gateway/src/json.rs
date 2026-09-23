use serde::{de, Deserialize, Deserializer};
use serde_json::{Map, Value};

/// Unlike deserializing into Value directly, this visitor rejects duplicate
/// decoded object keys, including inside arrays and structured instructions.
struct UniqueValue(Value);

impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Visitor;

        impl<'de> de::Visitor<'de> for Visitor {
            type Value = UniqueValue;

            fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                formatter.write_str("JSON with unique object keys")
            }

            fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }

            fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self::Value, E> {
                Ok(UniqueValue(value.into()))
            }

            fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self::Value, E> {
                Ok(UniqueValue(value.into()))
            }

            fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self::Value, E> {
                Ok(UniqueValue(value.into()))
            }

            fn visit_f64<E: de::Error>(self, value: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(value)
                    .map(|n| UniqueValue(Value::Number(n)))
                    .ok_or_else(|| E::custom("nonfinite number"))
            }

            fn visit_str<E: de::Error>(self, value: &str) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::String(value.to_owned())))
            }

            fn visit_seq<A: de::SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(UniqueValue(value)) = seq.next_element()? {
                    values.push(value);
                }

                Ok(UniqueValue(Value::Array(values)))
            }

            fn visit_map<A: de::MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
                let mut values = Map::new();
                while let Some(key) = map.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(de::Error::custom("duplicate object key"));
                    }
                    let UniqueValue(value) = map.next_value()?;
                    values.insert(key, value);
                }

                Ok(UniqueValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(Visitor)
    }
}

pub(crate) fn strict_json(body: &[u8]) -> Result<Value, serde_json::Error> {
    serde_json::from_slice::<UniqueValue>(body).map(|value| value.0)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::strict_json;

    #[test]
    fn a_top_level_duplicate_is_rejected() {
        assert!(strict_json(br#"{"model":"a","model":"b"}"#).is_err());
    }

    #[test]
    fn a_nested_duplicate_is_rejected() {
        assert!(strict_json(br#"{"state":{"step":1,"step":2}}"#).is_err());
    }

    #[test]
    fn a_duplicate_inside_an_array_element_is_rejected() {
        assert!(strict_json(br#"{"messages":[{"role":"user","role":"system"}]}"#).is_err());
    }

    #[test]
    fn the_same_key_at_different_levels_is_accepted() {
        let value = strict_json(br#"{"model":"a","metadata":{"model":"b"}}"#).unwrap();

        assert_eq!(value, json!({"model": "a", "metadata": {"model": "b"}}));
    }

    #[test]
    fn trailing_bytes_are_rejected() {
        assert!(strict_json(b"{}{}").is_err());
        assert!(strict_json(b"{} x").is_err());
    }

    #[test]
    fn numbers_round_trip_exactly() {
        let value = strict_json(br#"[18446744073709551615,-9223372036854775808,0.125]"#).unwrap();

        assert_eq!(value[0].as_u64(), Some(u64::MAX));
        assert_eq!(value[1].as_i64(), Some(i64::MIN));
        assert_eq!(value[2].as_f64(), Some(0.125));
    }

    #[test]
    fn a_scalar_top_level_value_decodes() {
        assert_eq!(strict_json(b"42").unwrap(), json!(42));
        assert_eq!(strict_json(br#""text""#).unwrap(), json!("text"));
        assert_eq!(strict_json(b"null").unwrap(), json!(null));
    }

    #[test]
    fn key_order_is_preserved() {
        let value = strict_json(br#"{"z":1,"a":2,"m":{"y":3,"b":4}}"#).unwrap();

        assert_eq!(
            serde_json::to_string(&value).unwrap(),
            r#"{"z":1,"a":2,"m":{"y":3,"b":4}}"#
        );
    }
}
