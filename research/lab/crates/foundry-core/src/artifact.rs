use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::fs;
use std::io;
use std::path::PathBuf;
use thiserror::Error;

#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(transparent)]
pub struct ArtifactId(String);

impl ArtifactId {
    pub fn from_bytes(bytes: &[u8]) -> Self {
        Self(blake3::hash(bytes).to_hex().to_string())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    ExperimentSpec,
    ModelTransform,
    QualityEvaluation,
    KernelMeasurement,
    HardwareSimulation,
    ServingSimulation,
    EconomicReport,
    ExperimentReport,
    SearchReport,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Provenance {
    pub producer: String,
    pub producer_version: String,
    pub source_artifacts: Vec<ArtifactId>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Artifact<T> {
    pub schema_version: u32,
    pub kind: ArtifactKind,
    pub provenance: Provenance,
    pub payload: T,
}

#[derive(Clone, Debug)]
pub struct ArtifactStore {
    root: PathBuf,
}

impl ArtifactStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn put<T: Serialize>(&self, artifact: &Artifact<T>) -> Result<ArtifactId, ArtifactError> {
        let bytes = serde_json::to_vec(artifact)?;
        let id = ArtifactId::from_bytes(&bytes);
        let path = self.path_for(&id)?;
        if path.exists() {
            self.verify_bytes(&id, &fs::read(path)?)?;
            return Ok(id);
        }

        let parent = path.parent().ok_or(ArtifactError::InvalidId)?;
        fs::create_dir_all(parent)?;
        let temporary = parent.join(format!(".{}.tmp", id.as_str()));
        fs::write(&temporary, bytes)?;
        match fs::rename(&temporary, &path) {
            Ok(()) => Ok(id),
            Err(_) if path.exists() => {
                let _ = fs::remove_file(temporary);
                self.verify_bytes(&id, &fs::read(path)?)?;
                Ok(id)
            }
            Err(error) => Err(error.into()),
        }
    }

    pub fn get<T: DeserializeOwned>(&self, id: &ArtifactId) -> Result<Artifact<T>, ArtifactError> {
        let bytes = fs::read(self.path_for(id)?)?;
        self.verify_bytes(id, &bytes)?;
        Ok(serde_json::from_slice(&bytes)?)
    }

    fn path_for(&self, id: &ArtifactId) -> Result<PathBuf, ArtifactError> {
        let value = id.as_str();
        if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(ArtifactError::InvalidId);
        }
        Ok(self
            .root
            .join(&value[..2])
            .join(format!("{}.json", &value[2..])))
    }

    fn verify_bytes(&self, id: &ArtifactId, bytes: &[u8]) -> Result<(), ArtifactError> {
        let actual = ArtifactId::from_bytes(bytes);
        if actual == *id {
            Ok(())
        } else {
            Err(ArtifactError::Integrity {
                expected: id.clone(),
                actual,
            })
        }
    }
}

#[derive(Debug, Error)]
pub enum ArtifactError {
    #[error("artifact identity is invalid")]
    InvalidId,
    #[error("artifact integrity failed: expected {expected:?}, got {actual:?}")]
    Integrity {
        expected: ArtifactId,
        actual: ArtifactId,
    },
    #[error("artifact I/O failed: {0}")]
    Io(#[from] io::Error),
    #[error("artifact serialization failed: {0}")]
    Serialization(#[from] serde_json::Error),
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
    struct Payload {
        candidate: String,
        output_cost: f64,
    }

    fn temporary_store() -> (PathBuf, ArtifactStore) {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock must be after epoch")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("foundry-artifacts-{nonce}"));
        (root.clone(), ArtifactStore::new(root))
    }

    fn artifact() -> Artifact<Payload> {
        Artifact {
            schema_version: 1,
            kind: ArtifactKind::EconomicReport,
            provenance: Provenance {
                producer: "foundry-core".into(),
                producer_version: "0.1.0".into(),
                source_artifacts: Vec::new(),
            },
            payload: Payload {
                candidate: "qwen3-8b-w4".into(),
                output_cost: 0.25,
            },
        }
    }

    #[test]
    fn identical_artifacts_share_identity_and_round_trip() {
        let (root, store) = temporary_store();
        let artifact = artifact();

        let first = store.put(&artifact).expect("first write must succeed");
        let second = store.put(&artifact).expect("second write must succeed");
        let loaded: Artifact<Payload> = store.get(&first).expect("read must succeed");

        assert_eq!(first, second);
        assert_eq!(loaded, artifact);
        fs::remove_dir_all(root).expect("temporary store must be removable");
    }

    #[test]
    fn tampering_is_detected_before_deserialization() {
        let (root, store) = temporary_store();
        let id = store.put(&artifact()).expect("write must succeed");
        let path = store.path_for(&id).expect("identity must produce a path");
        fs::write(path, br#"{"changed":true}"#).expect("tamper write must succeed");

        let error = store
            .get::<Payload>(&id)
            .expect_err("tampered artifact must fail");

        assert!(matches!(error, ArtifactError::Integrity { .. }));
        fs::remove_dir_all(root).expect("temporary store must be removable");
    }
}
