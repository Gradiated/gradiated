use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ServiceTier {
    Flex,
    #[default]
    Default,
    Fast,
}

impl ServiceTier {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Flex => "flex",
            Self::Default => "default",
            Self::Fast => "fast",
        }
    }

    pub const fn runtime_priority(self) -> i64 {
        match self {
            Self::Fast => -10,
            Self::Default => 0,
            Self::Flex => 10,
        }
    }

    pub const fn price_ratio(self) -> (u64, u64) {
        match self {
            Self::Flex => (7, 10),
            Self::Default => (1, 1),
            Self::Fast => (3, 2),
        }
    }
}
