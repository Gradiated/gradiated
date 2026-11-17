WITH
  deduplicated AS (
    SELECT id, argMax(toJSONString(properties), ingested_at) AS p
    FROM generations
    WHERE completed_at >= now() - INTERVAL 7 DAY
    GROUP BY id
  ),
  requests AS (
    SELECT
      JSONExtractString(p, 'model_id') AS model,
      JSONExtractString(p, 'served_release_digest') AS served_release,
      JSONExtractRaw(p, 'request_telemetry') AS metadata,
      JSONExtractUInt(p, 'usage', 'input_tokens') AS input_tokens,
      JSONExtractUInt(p, 'usage', 'output_tokens') AS output_tokens,
      JSONExtractUInt(p, 'usage', 'cached_input_tokens') AS cached_input_tokens
    FROM deduplicated
    WHERE JSONExtractString(p, 'status') = 'succeeded'
      AND JSONExtractUInt(p, 'request_telemetry', 'schema_version') = 1
      AND JSONExtractString(p, 'request_telemetry', 'traffic') = 'routed'
  )
SELECT
  model,
  served_release,
  JSONExtractString(metadata, 'kind') AS kind,
  JSONExtractString(metadata, 'task_type') AS task_type,
  JSONExtractString(metadata, 'task_source') AS task_source,
  JSONExtractString(metadata, 'token_buckets', 'input') AS input_bucket,
  JSONExtractString(metadata, 'token_buckets', 'output') AS output_bucket,
  JSONExtractString(metadata, 'token_buckets', 'cache_fraction') AS cache_bucket,
  count() AS requests,
  sum(input_tokens) AS total_input_tokens,
  sum(output_tokens) AS total_output_tokens,
  sum(cached_input_tokens) AS total_cached_input_tokens,
  quantilesExact(0.5, 0.9, 0.99)(JSONExtractUInt(metadata, 'messages')) AS message_counts,
  quantilesExact(0.5, 0.9, 0.99)(JSONExtractUInt(metadata, 'tool_definitions')) AS tool_counts,
  quantilesExact(0.5, 0.9, 0.99)(JSONExtractUInt(metadata, 'tool_schema', 'nodes')) AS schema_nodes
FROM requests
GROUP BY model, served_release, kind, task_type, task_source, input_bucket, output_bucket, cache_bucket
HAVING requests >= 100
ORDER BY total_output_tokens DESC;
