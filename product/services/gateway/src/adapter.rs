use serde::Deserialize;
use sha2::{Digest, Sha256};
use uuid::Uuid;

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum AdapterFormat {
    #[default]
    PeftLora,
    Cartridge,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct PrivateAdapter {
    pub workspace_id: Uuid,
    pub organization_slug: String,
    pub task_name: String,
    pub version_id: Uuid,
    pub name: String,
    pub status: String,
    pub size_bytes: u64,
    pub base_model_id: String,
    pub base_model_revision: String,
    pub sha256: String,
    #[serde(default)]
    pub format: AdapterFormat,
    /// A cartridge's K: the prompt positions it occupies.
    #[serde(default)]
    pub num_tokens: Option<u64>,
    /// `grad` for a version published from a grad artifact.
    #[serde(default)]
    pub source_kind: Option<String>,
    /// grad's eval-only versions answer eval-lane keys only.
    #[serde(default)]
    pub eval_only: bool,
}

impl PrivateAdapter {
    pub fn is_valid(&self) -> bool {
        self.status == "available"
            && self.size_bytes > 0
            && !self.name.is_empty()
            && !self.organization_slug.is_empty()
            && !self.task_name.is_empty()
            && !self.base_model_id.is_empty()
            && !self.base_model_revision.is_empty()
            && self.sha256.len() == 64
            && self
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            && match self.format {
                AdapterFormat::PeftLora => self.num_tokens.is_none(),
                AdapterFormat::Cartridge => self.num_tokens.is_some_and(|tokens| tokens > 0),
            }
    }

    pub fn is_cartridge(&self) -> bool {
        self.format == AdapterFormat::Cartridge
    }

    /// Answers without the adapter would not be the version's, so neither the base
    /// model nor external capacity may stand in for it.
    pub fn fails_closed(&self) -> bool {
        self.is_cartridge() || self.source_kind.as_deref() == Some("grad")
    }

    /// Prompt positions the runtime adds for this adapter, which are not billed.
    pub fn cartridge_tokens(&self) -> u64 {
        if self.is_cartridge() {
            self.num_tokens.unwrap_or(0)
        } else {
            0
        }
    }

    pub fn model_id(&self) -> String {
        format!(
            "{}/{}/{}",
            self.organization_slug, self.task_name, self.name
        )
    }

    pub fn runtime_name(&self) -> String {
        format!("{}/{}", self.workspace_id, self.version_id)
    }

    pub fn served_digest(&self, base_digest: &str) -> String {
        let mut identity = serde_json::json!({"base_release_digest": base_digest, "version_id": self.version_id, "sha256": self.sha256});
        // LoRA keeps its earlier identity, so its served digests do not change.
        if self.is_cartridge() {
            identity["format"] = "cartridge".into();
        }
        format!(
            "sha256:{:x}",
            Sha256::digest(serde_json::to_vec(&identity).expect("adapter identity serializes"))
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn adapter(format: AdapterFormat, num_tokens: Option<u64>) -> PrivateAdapter {
        PrivateAdapter {
            workspace_id: Uuid::nil(),
            organization_slug: "acme".to_owned(),
            task_name: "task".to_owned(),
            version_id: Uuid::from_u128(7),
            name: "v1".to_owned(),
            status: "available".to_owned(),
            size_bytes: 1,
            base_model_id: "base".to_owned(),
            base_model_revision: "revision".to_owned(),
            sha256: "a".repeat(64),
            format,
            num_tokens,
            source_kind: None,
            eval_only: false,
        }
    }

    #[test]
    fn a_cartridge_needs_its_length_and_a_lora_has_none() {
        assert!(adapter(AdapterFormat::PeftLora, None).is_valid());
        assert!(!adapter(AdapterFormat::PeftLora, Some(4)).is_valid());
        assert!(adapter(AdapterFormat::Cartridge, Some(4)).is_valid());
        assert!(!adapter(AdapterFormat::Cartridge, None).is_valid());
        assert!(!adapter(AdapterFormat::Cartridge, Some(0)).is_valid());
        assert_eq!(
            adapter(AdapterFormat::Cartridge, Some(4)).cartridge_tokens(),
            4
        );
        assert_eq!(adapter(AdapterFormat::PeftLora, None).cartridge_tokens(), 0);
    }

    #[test]
    fn the_served_digest_includes_a_cartridge_format_and_keeps_lora_digests() {
        let lora = adapter(AdapterFormat::PeftLora, None);
        let legacy = serde_json::json!({"base_release_digest": "sha256:base", "version_id": lora.version_id, "sha256": lora.sha256});
        assert_eq!(
            lora.served_digest("sha256:base"),
            format!(
                "sha256:{:x}",
                Sha256::digest(serde_json::to_vec(&legacy).unwrap())
            )
        );
        assert_ne!(
            adapter(AdapterFormat::Cartridge, Some(4)).served_digest("sha256:base"),
            lora.served_digest("sha256:base")
        );
    }

    #[test]
    fn the_adapter_query_shape_parses_both_formats() {
        let record = |format: &str, num_tokens: serde_json::Value| {
            serde_json::from_value::<PrivateAdapter>(serde_json::json!({
                "workspace_id": Uuid::nil(), "organization_slug": "acme", "task_name": "t",
                "version_id": Uuid::nil(), "name": "v1", "status": "available", "size_bytes": 1,
                "base_model_id": "b", "base_model_revision": "r", "sha256": "a".repeat(64),
                "format": format, "num_tokens": num_tokens,
            }))
            .unwrap()
        };
        let lora = record("peft_lora", serde_json::Value::Null);
        assert_eq!(
            (lora.format, lora.num_tokens),
            (AdapterFormat::PeftLora, None)
        );
        let cartridge = record("cartridge", 512.into());
        assert_eq!(
            (cartridge.format, cartridge.num_tokens),
            (AdapterFormat::Cartridge, Some(512))
        );
    }
}
