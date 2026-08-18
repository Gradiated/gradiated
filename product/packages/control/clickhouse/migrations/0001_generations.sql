CREATE TABLE IF NOT EXISTS generations
(
  id UUID,
  properties JSON(
    event_schema_version UInt16,
    organization_id UUID,
    workspace_id UUID,
    api_key_id UUID,
    model_id String,
    `settlement.slot_id` String,
    status String,
    `usage.charge` Int64,
    `timing.completed_at` DateTime64(6, 'UTC')
  ),
  ingested_at DateTime64(6, 'UTC') DEFAULT now64(6),
  event_schema_version UInt16 MATERIALIZED getSubcolumn(properties, 'event_schema_version'),
  organization_id UUID MATERIALIZED getSubcolumn(properties, 'organization_id'),
  workspace_id UUID MATERIALIZED getSubcolumn(properties, 'workspace_id'),
  api_key_id UUID MATERIALIZED getSubcolumn(properties, 'api_key_id'),
  model_id LowCardinality(String) MATERIALIZED getSubcolumn(properties, 'model_id'),
  settlement_slot_id String MATERIALIZED getSubcolumn(properties, 'settlement.slot_id'),
  status LowCardinality(String) MATERIALIZED getSubcolumn(properties, 'status'),
  charge Int64 MATERIALIZED getSubcolumn(properties, 'usage.charge'),
  completed_at DateTime64(6, 'UTC') MATERIALIZED getSubcolumn(properties, 'timing.completed_at')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(completed_at)
ORDER BY (organization_id, workspace_id, completed_at, id)
