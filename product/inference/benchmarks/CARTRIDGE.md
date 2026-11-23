# Cartridge serving GPU test plan

This plan qualifies the SGLang cartridge patches (`cartridge_*.patch` in
`bundles/glm-5-3-flash-sglang`) on DeepSeek V4.1 Flash 1017. The design is in
[CARTRIDGE_SERVING_PLAN.md](../../../docs/CARTRIDGE_SERVING_PLAN.md).
`cartridge_bench.py` drives every step. It uses only the standard library.

## Hypothesis and acceptance

When requests for 64 different cartridges share one batch, decode should cost
the same as the same batch without cartridges. Prefill should cost no more than
the extra K positions. Logits should match the research reference.

| Check                                                                                                                 | Pass                                                                                    |
| --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Decode: 64 requests across 64 cartridges vs 64 base requests                                                          | throughput ratio ≥ 0.98 and mean ITL ratio ≤ 1.02 (ABBA, 4 repeats)                     |
| Fixed cost: pool on, base traffic only, vs `--cartridge-pool-bytes 0`                                                 | the same 2% bounds                                                                      |
| Cold prefill: cartridge rows resident, after `flush_cache`, vs a base prompt padded to the same `usage.prompt_tokens` | TTFT ratio ≤ 1.05, plus the first-use cost (resolve and table load) measured separately |
| Warm prefill: cached cartridge prefix vs base request with a cached system prompt                                     | TTFT ratio ≤ 1.05; `cached_tokens` ≥ first cartridge position + K                       |
| Correctness: one held-out row, 16 assistant cut points                                                                | same argmax, top-5 \|Δ logprob\| ≤ 0.02, and the no-cartridge control differs by > 0.1  |
| Mixed-batch isolation: the correctness run with 63 background requests (cartridges and base)                          | the same bounds                                                                         |
| Radix isolation: two cartridges with the same slot IDs                                                                | the second cartridge's first request caches at most the tokens before the slots         |

## Configuration

The task asks for the 8-GPU production configuration. `runtimes/deepseek-sglang/config.py`
launches TP4/EP4 on B300 with 32 active requests. Run TP8/EP8 first, then repeat
the decode and correctness checks on TP4. Keep every flag from `config.py`:
DSPARK, breakable prefill CUDA graphs, decode CUDA graphs, overlap scheduling,
the radix cache and chunked prefill at 16384. Then add:

```sh
export SGLANG_LORA_RESOLVER_URL=http://127.0.0.1:31999/resolve
... --cartridge-pool-bytes 4294967296 \
    --max-running-requests 64 --cuda-graph-max-bs-decode 64
```

The 64-request decode check needs 64 running requests and a captured bs-64
decode graph. Production's 32 is not enough. Repeat it at 32 with
`--batch 32` to match production.

## Steps

Use an existing leased dev host (`$gpu-host-lease` or `$dev-training`). Do not
create compute for this plan without approval. Budget about two GPU-hours and
time out each server start after 50 minutes. Keep cases, references and the
customer cartridge under `/data` on the host or under `.agents/runtime/`; never
commit them.

1. Build the bundle and run `verify-build.py`. Then run the CPU tests in
   `bundles/glm-5-3-flash-sglang/tests` and `lora/test_cartridge.py`.
2. Write synthetic cartridges. The command reads only the slot IDs of the
   reference cartridge; its embeddings are never copied:
   `cartridge_bench.py synth --slots-from /tmp/cartconv/cartridge.safetensors --output /data/cartbench --count 96`.
3. Start the resolver with
   `cartridge_bench.py resolver --root /data/cartbench`. Copy the reference
   cartridge to `/data/cartbench/reference/` on the host only.
4. Start the patched server with the flags above. Check the startup log for:
   decode and prefill graph capture, overlap scheduling, and no
   `--cartridge-pool-bytes does not support` error.
5. Decode: `cartridge_bench.py decode --batch 64 --output-tokens 512 --repeats 4`.
   Repeat the base arm against a server started with
   `--cartridge-pool-bytes 0` to measure the breakable-graph break that the
   pool adds to every prefill.
6. Prefill: `cartridge_bench.py prefill --cartridge-tokens 256 --repeats 8`.
   Record the cartridge table load time separately from the server log or
   `py-spy`.
7. Correctness reference: render 16 cut points of one held-out row as chat
   messages, with the final assistant message as a prefix, into
   `/data/cases.json` (`{"cases": [{"messages": [...]}]}`). Start the research
   build: the same pinned bundle without the cartridge patches, with
   `carthook` loaded and `serve_cart.sh score`. Record the reference:
   `cartridge_bench.py correctness --cases /data/cases.json --record /data/reference.json --cartridge-model deepseek-ai/DeepSeek-V4.1-Flash-1017`.
   The hook serves the cartridge on the base model name.
8. Correctness: on the patched server, run
   `cartridge_bench.py correctness --cases /data/cases.json --reference /data/reference.json --cartridge-model <workspace>/reference`,
   then again with `--background 63`.
9. Chunking and isolation:
   - restart with `--chunked-prefill-size 128` so a chunk boundary falls
     inside the 256 cartridge positions, and repeat step 8;
   - send two synthetic cartridges with the same slot IDs and check
     `usage.prompt_tokens_details.cached_tokens`;
   - with `--enable-hierarchical-cache`, evict the device cache and confirm
     that host hits stay per cartridge.
10. Compare DSPARK's accepted length between the decode arms in the
    `/metrics` output. Cartridges should not change it beyond noise.

Report each result as measured, with the command line, bundle digest, GPU and
TP size. A failure is a branch result: record it and continue with the
remaining checks.

## Production replica

`cartridge_replica.py` runs the checks that gate a rollout against a
production replica held at the first new replica, or the gateway. It takes
`--base-url`, the base model name and real task-version model names, and
reads the API key from `CARTRIDGE_BENCH_API_KEY`. It needs no flush or
resolver.

Upload 34 cartridge task versions to one internal workspace. Each holds K = 256
positions × 5120 bf16 values: 2,621,440 bytes of embeddings plus 2,048 bytes of
slot IDs, about 2.62 MB. All 34 total about 89 MB.

- 32 synthetic cartridges, for 32 different cartridges in a batch-32 decode:
  `cartridge_bench.py synth --slots-from <cartridge> --output <dir> --count 32`.
  Only the slot IDs are read from `--slots-from`, never its embeddings.
- `identity-a` and `identity-b`, from
  `cartridge_replica.py identity-files --model <checkpoint> --slots-from <cartridge> --output <dir>`.
  Their rows are the checkpoint's own embedding rows of the slot IDs, so a
  correct server gives the same logits as the base model with the slot text.
  The two files differ only in metadata, so they have different digests and
  cache namespaces. `identity-b` is the noise floor.

List the 32 synthetic model names in a file, one per line. Run the checks in
this order against one replica. The base model and every cartridge must reach
the same replica; through the gateway that holds only when the replica is the
deployment's only one. Production's router admits 32 requests and queues 2, so
background load stops at 31. The wrapper retries 429 and 503 answers.

```sh
export CARTRIDGE_BENCH_API_KEY=...   # from the secret store, never on the command line
C="--base-url <url> --base-model deepseek-ai/DeepSeek-V4.1-Flash-1017 --cartridges names.txt --slot-text slots.json"
cartridge_replica.py probe     $C --identity <identity-a>
cartridge_replica.py decode    $C --batch 32 --repeats 4 [--metrics-url <replica>/metrics]
cartridge_replica.py identity  $C --identity <identity-a> --identity-floor <identity-b>
cartridge_replica.py identity  $C --identity <identity-a> --identity-floor <identity-b> --background 31
cartridge_replica.py isolation $C
```

`probe` checks that `ignore_eos`, streamed usage and logprobs pass through.
Without per-chunk usage, `decode` spreads the token count over the chunks and
reports `approximate_token_counts`. Gates:

| Check       | Pass                                                                                                                                                         |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `decode`    | cartridge vs slot-text control: throughput ratio ≥ 0.98 and ITL ratio ≤ 1.02; DSPARK accept ratio reported with `--metrics-url`                              |
| `identity`  | median top-5 \|Δ logprob\| vs the slot-text render ≤ max(0.02, 1.5 × the identity-a vs identity-b median), and argmax agreement within one case of the floor |
| `isolation` | the second cartridge and the slot-text base request cache at most the 64 tokens before the slots; each cartridge reuses its own prefix                       |
