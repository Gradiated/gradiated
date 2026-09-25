use chrono::{DateTime, TimeZone, Timelike, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use uuid::Uuid;

pub const SCHEMA: &str = "gradiated.generation-content/1";
const MAX_TASK_BYTES: usize = 256;
const RETENTION_DAYS: [u16; 3] = [30, 90, 180];

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum RecordError {
    #[error("the body is not a generation content record: {0}")]
    Malformed(String),
    #[error("unsupported schema {0}")]
    Schema(String),
    #[error("generation_id must be a UUIDv7")]
    GenerationId,
    #[error("task must be at most 256 bytes")]
    Task,
    #[error("retention_days must be 30, 90 or 180")]
    Retention,
    #[error("source must be hosted, relay or import")]
    Source,
    #[error("hosted generations are trainable and relayed generations are not")]
    Trainable,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct GenerationContent {
    pub schema: String,
    pub generation_id: Uuid,
    pub workspace_id: Uuid,
    pub task: Option<String>,
    pub trace_id: Option<String>,
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub external_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub protocol: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<u16>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub outcome: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub streamed: Option<bool>,
    pub model: String,
    pub provider: String,
    pub source: String,
    pub trainable: bool,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub usage: Option<Value>,
    pub retention_days: u16,
}

#[derive(Clone, Debug, Hash, PartialEq, Eq)]
pub struct StreamKey {
    pub workspace_id: Uuid,
    pub task_key: String,
    pub hour: DateTime<Utc>,
    pub retention_days: u16,
    pub trainable: bool,
}

impl GenerationContent {
    pub fn read(body: &[u8]) -> Result<Self, RecordError> {
        serde_json::from_slice(body).map_err(|error| RecordError::Malformed(error.to_string()))
    }

    pub fn parse(body: &[u8]) -> Result<Self, RecordError> {
        let header = Self::read(body)?;

        if header.schema != SCHEMA {
            return Err(RecordError::Schema(header.schema));
        }

        if header.generation_id.get_version_num() != 7 {
            return Err(RecordError::GenerationId);
        }

        if header
            .task
            .as_ref()
            .is_some_and(|task| task.len() > MAX_TASK_BYTES)
        {
            return Err(RecordError::Task);
        }

        if !RETENTION_DAYS.contains(&header.retention_days) {
            return Err(RecordError::Retention);
        }

        match (header.source.as_str(), header.trainable) {
            ("hosted", true) | ("relay", false) | ("import", _) => Ok(header),
            ("hosted" | "relay", _) => Err(RecordError::Trainable),
            _ => Err(RecordError::Source),
        }
    }

    pub fn stream_key(&self) -> Option<StreamKey> {
        let task = self.task.as_deref().filter(|task| !task.is_empty())?;

        Some(StreamKey {
            workspace_id: self.workspace_id,
            task_key: task_key(task),
            hour: generation_hour(self.generation_id),
            retention_days: self.retention_days,
            trainable: self.trainable,
        })
    }
}

pub fn task_key(task: &str) -> String {
    let plain = task.len() <= 64
        && task.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-' || byte == b'_'
        });

    if plain {
        return task.to_owned();
    }

    let digest = Sha256::digest(task.as_bytes());
    let hex: String = digest
        .iter()
        .take(16)
        .map(|byte| format!("{byte:02x}"))
        .collect();

    format!("h-{hex}")
}

pub fn generation_hour(generation_id: Uuid) -> DateTime<Utc> {
    let (seconds, _) = generation_id
        .get_timestamp()
        .expect("a UUIDv7 carries a timestamp")
        .to_unix();
    let time = Utc
        .timestamp_opt(seconds as i64, 0)
        .single()
        .expect("a UUIDv7 timestamp is a valid time");

    time.with_minute(0)
        .and_then(|time| time.with_second(0))
        .expect("every hour has minute and second zero")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::{record, with_fields};
    use serde_json::json;

    #[test]
    fn a_valid_record_parses_and_keys_by_its_generation_hour() {
        let id = Uuid::parse_str("0199835f-5a00-7000-8000-000000000000").unwrap();
        let header = GenerationContent::parse(&record(id, "support-triage")).unwrap();
        let key = header.stream_key().unwrap();

        assert_eq!(key.task_key, "support-triage");
        assert_eq!(key.hour.minute(), 0);
        assert_eq!(key.retention_days, 30);
        assert!(key.trainable);
        assert!(
            key.hour
                <= Utc
                    .timestamp_opt(id.get_timestamp().unwrap().to_unix().0 as i64, 0)
                    .unwrap()
        );
    }

    #[test]
    fn invalid_records_are_refused() {
        let v7 = Uuid::now_v7();
        let v4 = Uuid::parse_str("123e4567-e89b-42d3-a456-426614174000").unwrap();
        let mut wrong_schema: Value = serde_json::from_slice(&record(v7, "t")).unwrap();
        wrong_schema["schema"] = "gradiated.generation-content/9".into();
        let valid = record(v7, "t");

        for (body, expected) in [
            (b"not json".to_vec(), "Malformed"),
            (serde_json::to_vec(&wrong_schema).unwrap(), "Schema"),
            (record(v4, "t"), "GenerationId"),
            (record(v7, &"t".repeat(257)), "Task"),
            (
                with_fields(&valid, json!({ "retention_days": 60 })),
                "Retention",
            ),
            (with_fields(&valid, json!({ "source": "upload" })), "Source"),
            (
                with_fields(&valid, json!({ "trainable": false })),
                "Trainable",
            ),
            (
                with_fields(&valid, json!({ "source": "relay", "trainable": true })),
                "Trainable",
            ),
        ] {
            let error = GenerationContent::parse(&body).unwrap_err();

            assert!(format!("{error:?}").starts_with(expected), "{error:?}");
        }
    }

    #[test]
    fn relayed_and_imported_generations_key_by_their_trainability() {
        let valid = record(Uuid::now_v7(), "t");

        for (fields, trainable) in [
            (json!({ "source": "relay", "trainable": false }), false),
            (json!({ "source": "import", "trainable": false }), false),
            (json!({ "source": "import", "trainable": true }), true),
        ] {
            let key = GenerationContent::parse(&with_fields(&valid, fields.clone()))
                .unwrap()
                .stream_key()
                .unwrap();

            assert_eq!(key.trainable, trainable, "{fields}");
        }
    }

    #[test]
    fn a_generation_without_a_task_has_no_stream() {
        let valid = record(Uuid::now_v7(), "t");

        for task in [json!(null), json!("")] {
            let content =
                GenerationContent::parse(&with_fields(&valid, json!({ "task": task }))).unwrap();

            assert_eq!(content.stream_key(), None, "{task}");
        }
    }

    #[test]
    fn task_keys_are_safe_in_object_keys() {
        assert_eq!(task_key("support-triage_2"), "support-triage_2");

        for unsafe_task in ["Support", "a/b", "..", &"a".repeat(65)] {
            let key = task_key(unsafe_task);

            assert!(
                key.starts_with("h-") && key.len() == 34,
                "{unsafe_task}: {key}"
            );
        }
    }
}
