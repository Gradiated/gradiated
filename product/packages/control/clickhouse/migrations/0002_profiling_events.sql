CREATE TABLE IF NOT EXISTS profiling_events
(
  id UUID,
  properties JSON(
    event_schema_version UInt16,
    deployment_id UUID,
    model_id String,
    runtime_revision String,
    event_type String,
    `timing.observed_at` DateTime64(6, 'UTC')
  ),
  ingested_at DateTime64(6, 'UTC') DEFAULT now64(6),
  event_schema_version UInt16 MATERIALIZED getSubcolumn(properties, 'event_schema_version'),
  deployment_id UUID MATERIALIZED getSubcolumn(properties, 'deployment_id'),
  model_id LowCardinality(String) MATERIALIZED getSubcolumn(properties, 'model_id'),
  runtime_revision String MATERIALIZED getSubcolumn(properties, 'runtime_revision'),
  event_type LowCardinality(String) MATERIALIZED getSubcolumn(properties, 'event_type'),
  observed_at DateTime64(6, 'UTC') MATERIALIZED getSubcolumn(properties, 'timing.observed_at')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (deployment_id, event_type, observed_at, id)
