# Kimi K3.1 Pro throughput probe

This closed-loop probe tests aggregate throughput while requiring every request
to complete and the **median request** to decode at least `--floor-tps` output
tokens/s (default 80; tokens after the first, over time after the first token). Each round also
records the slowest and p05 stream rates. It generates deterministic
synthetic 2K, 8K and 32K text-token fixtures using the pinned checkpoint's custom
Hugging Face tokenizer and `tiktoken.model`. Actual chat prompt counts come from response usage; chat control
tokens can make them larger than the prepared text-token counts.

Run the probe on an isolated or explicitly targeted Kimi replica, never against
the ordinary production pool while exploring saturation. The probe does not start
servers, modify admission settings, or manage provider capacity.

```sh
python \
  product/inference/benchmarks/kimi-k31/probe.py \
  --base-url http://127.0.0.1:30000 \
  --label tp8-baseline-A1 --native-metrics \
  --tokenizer-path /var/lib/kimi-k31/checkpoint \
  --concurrency 1,2,4,8,16,24,32 --trials 3 \
  --temperature 1.0 --top-p .95 --reasoning-effort max \
  --output-tokens 512 --min-output-tokens 512 \
  --deadline-utc 2026-11-06T06:00:00Z \
  --config-json .agents/runtime/kimi-k31/launch-config.json \
  --output .agents/runtime/kimi-k31/tp8-baseline-A1.json
```

Run with the qualified SGLang runtime's Python so that the matching `transformers`
and `tiktoken` dependencies are available. The tokenizer is loaded with
`trust_remote_code=True, local_files_only=True`: only use a local snapshot pinned
to the declared model revision, including its tokenizer Python files.
Alternatively, `--fixtures fixtures.json` accepts an array of
`{id,target_tokens,messages,prepared_text_tokens?}` records. These should be
prepared with the pinned tokenizer; their final chat token counts are still
reported by the server. The default model and runtime revisions are pinned in
the script. `--model` accepts the public model ID when targeting the gateway.
Credentials are read only from the environment variable named by
`--api-key-env` (default `GRADIATED_RUNTIME_API_KEY`) and excluded from output.

The default sampling parameters match production: temperature `1.0`, top-p
`0.95`, and reasoning effort `max`. Speculative decoding acceptance depends on
sampling, so report production-default performance separately from a greedy
control (`--temperature 0 --top-p 1`). `--reasoning-effort low` is available for
a separately scoped arm. Every setting is recorded in result metadata; the seed
controls synthetic fixture generation and ordering only, not request sampling.

`--native-metrics` requests SGLang's `continuous_usage_stats` and
`include_internal_content` stream extensions. The pinned Kimi implementation
deliberately permits top-level usage only in the final summary, so Chat mode
normally has no first-burst counter and uses the conservative end-to-end gate.
When authoritative cumulative usage is available, the probe counts the first
emitted token burst, then computes
`(completion_tokens - first_burst_tokens) / (last_progress - first_progress)`.
This avoids overstating speculative decode performance when one SSE event
contains multiple tokens. It also reports the conventional
`(completion_tokens - 1) / duration` figure as `nominal_decode_tps`, but never uses
that figure to qualify an uncounted first burst. SSE event gaps describe network
delivery gaps, not per-token latency. Kimi's `internal_content` describes token
provenance for parser fragments: a token spanning two fragments can appear in
both, and replayed reasoning can reference earlier tokens. Its summed
`internal_token_occurrences` can therefore exceed completion usage legitimately.
These occurrences are diagnostic only and never substitute for cumulative token
counts or prove the size of the first generation burst.

Without counted first-burst metadata, qualification uses the stricter
`completion_tokens / full_request_elapsed` lower bound, including prefill,
queueing, and delivery. This is conservative for decode performance and can
reject a valid decode configuration. Missing token usage, stream errors,
truncated streams, or fewer than 512 output tokens fail qualification. The probe
never substitutes `max_tokens` for missing usage. `--ignore-eos` is available for
native synthetic fixed-length throughput tests; record its use and do not use
those tests as a quality result.

Each concurrency runs three trials by default, with three requests per worker
and mixed prompt lengths. A concurrency qualifies only if every trial passes; the sweep stops at its first failure unless
`--continue-after-failure` is set. Results are atomically checkpointed after each
trial. Request timeouts, post-first-output idle timeouts, and an absolute campaign
deadline bound all network reads.

`--diagnostic-events` records up to 2,048 event timestamps, cumulative usage,
internal-token occurrence counts, and output-presence flags per request. It
records no generated text or token IDs and preserves partial diagnostics on a
failed request. The script is self-contained and can be copied directly to the
isolated runtime host.

For engine decode measurements, `--protocol generate` uses native SGLang
`/generate` SSE. It sends input IDs rendered by the pinned Kimi custom tokenizer
with `thinking_effort` matching the selected OpenAI `reasoning_effort`, then
reads authoritative cumulative `meta_info.completion_tokens` from each engine
event. The native prompt count must equal the exact input-ID length. Kimi Chat
reports three fewer prompt tokens because its billing excludes the assistant
generation stub; all three stub tokens remain in the actual model input.
Native mode is limited to the synthetic single-user text fixtures and records a
hash of each complete rendered input. It does not change the production wire
contract or qualify gateway behavior, parser latency, tools, or model quality.
Use a separate public OpenAI holdout to verify those serving effects.

```sh
python product/inference/benchmarks/kimi-k31/probe.py \
  --base-url http://127.0.0.1:30000 --label tp8-native-A1 \
  --protocol generate --tokenizer-path /var/lib/kimi-k31/checkpoint \
  --fixtures-per-class 1 --warmups 3 --trials 3 \
  --temperature 1 --top-p .95 --reasoning-effort max --floor-tps 80 \
  --output .agents/runtime/kimi-k31/tp8-native-A1.json
```

`--sampling-seed`, `--frequency-penalty` and `--presence-penalty` add request
sampling parameters; `--seed` only generates and orders fixtures. Qualify an
admission limit with two separate passing runs at that concurrency, one with
default sampling and one with seeded penalties, using the floor that the
runtime README sets for that limit. Penalties lower DFLASH acceptance, so the
penalty run is usually the limiting one. For the current five-request runtime
with its 65 TPS floor, every one of these six runs must pass:

```sh
# Fresh --seed per run keeps every trial cold; repeated trials reuse fixtures.
failed=0
for arm in default penalty; do for seed in 1 2 3; do
  extra="" base=100
  [ "$arm" = penalty ] && extra="--sampling-seed 42 --frequency-penalty .2 --presence-penalty .2" base=200
  python product/inference/benchmarks/kimi-k31/probe.py \
    --base-url http://127.0.0.1:30000 --label qualify-c5-$arm-$seed \
    --protocol generate --tokenizer-path /var/lib/kimi-k31/checkpoint \
    --concurrency 5 --fixtures-per-class 5 --warmups 0 --trials 1 \
    --seed $((base + seed)) \
    --temperature 1 --top-p .95 --reasoning-effort max --floor-tps 65 $extra \
    --output .agents/runtime/kimi-k31/qualify-c5-$arm-$seed.json || failed=1
done; done
test "$failed" = 0  # nonzero if any of the six runs failed
```

Use labels and separate output files for repeated same-workload A/B/A/B/A arms;
`--config-json` records the exact non-secret launch flags and hardware/runtime
identity. Compare repeated trials rather than treating a single saturation burst
as sustainable production capacity. These synthetic performance tests do not
qualify model quality, tools, multimodal behavior, or production routing.

```sh
python3 -m unittest discover -s product/inference/benchmarks/kimi-k31 -p 'test_*.py'
```
