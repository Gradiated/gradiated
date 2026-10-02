use serde::Deserialize;
use sha2::{Digest, Sha256};
use uuid::Uuid;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct PrivateAdapter {
    pub workspace_id: Uuid,
    pub version_id: Uuid,
    pub name: String,
    pub status: String,
    pub size_bytes: u64,
    pub base_model_id: String,
    pub base_model_revision: String,
    pub sha256: String,
}

impl PrivateAdapter {
    pub fn is_valid(&self) -> bool {
        self.status == "available"
            && self.size_bytes > 0
            && !self.name.is_empty()
            && !self.base_model_id.is_empty()
            && !self.base_model_revision.is_empty()
            && self.sha256.len() == 64
            && self
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    }

    pub fn model_id(&self) -> String {
        self.name.clone()
    }

    pub fn runtime_name(&self) -> String {
        format!("{}/{}", self.workspace_id, self.name)
    }

    pub fn served_digest(&self, base_digest: &str) -> String {
        let identity = serde_json::json!({"base_release_digest": base_digest, "version_id": self.version_id, "sha256": self.sha256});
        format!(
            "sha256:{:x}",
            Sha256::digest(serde_json::to_vec(&identity).expect("adapter identity serializes"))
        )
    }
}
