CREATE TABLE IF NOT EXISTS usage_events
(
  event_id String,
  organization_id UUID,
  workspace_id UUID,
  product LowCardinality(String),
  sku LowCardinality(String),
  quantity UInt64,
  amount_nano_usd Int64,
  price_version LowCardinality(String),
  occurred_at DateTime64(6, 'UTC'),
  subject_id String,
  tags Map(LowCardinality(String), String),
  ingested_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (organization_id, workspace_id, event_id)
