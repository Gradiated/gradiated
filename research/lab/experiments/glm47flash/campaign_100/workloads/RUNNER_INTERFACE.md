# Frozen workload replay interface

Validate the content-addressed bundle before materializing or sending any request:

```sh
python3 workloads/validate_bundle.py
```

`REPLAY_SCHEDULE.json` is authoritative for request count, maximum concurrency, arrival offsets, warmup count, cache mode, and repetitions. The cheapest Phase-B falsification sequence is `development_smoke`, `fixed_8k_1k_c1`, then `fixed_8k_1k_c8`: at most 25 measured requests before the 256-request concurrency-32 headline profile is admissible. The AA-AgentPerf-derived screen imports length geometry only and is not part of this minimum sequence.

For each selected profile, materialize a JSON plan with this contract:

```json
{
  "schema_version": 1,
  "bundle_sha256": "value printed by validate_bundle.py",
  "profile_id": "fixed_8k_1k_c1",
  "cache_mode": "disabled",
  "warmup_requests": [],
  "requests": []
}
```

Every request array must have the exact frozen count. Each request has `schema_version`, `request_id`, `fixture_id`, `max_output_tokens`, `expected_input_tokens`, and `scheduled_offset_ms`. Agent fixtures also carry the exact runner-derived `messages` and `tools`; prefix fixtures carry `request_index`. A fixed length-only fixture carries a tokenizer-materialized `prompt` and no messages. Input counts must equal `TOKENIZER_BINDINGS.json`, and agent message/tool objects must equal the frozen fixture byte-for-byte after canonical JSON encoding. Closed-loop offsets are zero; fixed-interval and session-relative offsets must match the selected profile exactly.

Run one profile against the SGLang OpenAI-compatible API:

```sh
python3 workloads/replay_api.py \
  --bundle workloads \
  --base-url http://127.0.0.1:30000 \
  --plan /evidence/replay-plan.json \
  --output /evidence/request-outcomes.jsonl
```

The server must return cumulative `completion_tokens` on each non-empty stream event, final prompt/completion usage, one finish reason, and `[DONE]`. The runner measures monotonic TTFT, token-level ITL, and E2E itself; records input/output/total tokens, typed errors, finish reason, and truncation; checks final prompt tokens against the frozen tokenizer binding; resets `/flush_cache` after warmup and before every measured repetition; and exits nonzero on any failure or truncation. It never accepts caller-supplied latency or token metrics.

Each outcome is schema version 1 with `request_id`, `fixture_id`, `repetition`, `status`, `latency_ms.{ttft,itl,end_to_end}`, `tokens.{input,output,total}`, `truncation.{detected,finish_reason}`, `stream_sha256`, and a typed `error` object or null.
