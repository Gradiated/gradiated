# Research log

## 2026-07-26T12:52:26Z — exact-model Gaudi3 runtime and placement screen

**Decision.** Emit typed `none` with type
`missing_scope_matched_target_gaudi3_performance_measurement`. The exact Gemma
4 31B producer and decision-bearing HPU consumer are now source-complete and
have a passing TP2 correctness job, but that job ran on `aicf-gaudi2-14`.
Neither it nor any public result measures the bound c32
4,214-prompt/358-output workload, its 12.7% prompt-cache read, or a
conservative service-time bound on Gaudi3. The project contract forbids
transferring Gaudi2 correctness or accelerator peaks into Gaudi3 throughput.

**Source-backed evidence.** vLLM-Gaudi merge
`ae952098bd0485a29d2b675065b89ad3c5b75674` adds the hybrid
full/sliding-attention and heterogeneous-KV consumers for
`google/gemma-4-31B-it`; its exact GSM8K job passed on Gaudi2 at TP2 against
vLLM `8def3cdde2a0acf0019447d8fcfc57e4df6bcfc2`. Small metadata from pinned
model revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4` confirms 60 layers
with a repeating five-local/one-global schedule, 1,024-token local horizon,
16x256 local and 4x512 global KV geometry, tied 262,144-row vocabulary, and
final logit softcap 30. No checkpoint shard was downloaded.

**Topology and current rate.** IBM's active public
`gx3d-160x1792x8gaudi3` profile purchases eight 128-GB Gaudi3 OAMs as one
node. The official July 2026 catalog exposes on-demand rates of `$60.60/h` in
`us-east` and `us-south` and `$70.30/h` in `eu-de`; spot is `$15.15/h` or
`$17.574/h` and is excluded from the sustainable case. The public reservation
metric exposes no usable nonzero 12–24-month price, so `$60.60/h` is the
conservative production ceiling. Published zones are bound, but live quota
and capacity were not tested.

**Derived discriminator.** Four TP2 replicas are the smallest
execution-evidenced packing on the eight-HPU node. Per replica, BF16 weights
are 58.2507 GiB and conservative c32 KV is 36.1621 GiB; evenly sharded raw
weights plus KV are 47.2064 GiB/HPU, leaving 72.0029 GiB/HPU when the
vendor's 128 GB is conservatively treated as decimal bytes, before compiler,
graph, bucket, fragmentation, and runtime buffers. At `$60.60/h`, 90%
utilization, and a further 10% failures/reloads/storage/orchestration/
reliability reserve, the target requires at least 187,505.8 total tok/s per
node. Equivalently, each TP2 replica must remain below 0.097533 service
seconds/request or 3.12106 seconds per c32 batch. Fresh-input, cache-read, and
output cost contributions are budgeted separately in the artifact; their
measured Gaudi3 phase times and costs remain null.

**Attempt amendment.** The first generator invocation stopped before writing
the screen because its public catalog schema assertion expected `service`
instead of the observed `plan`. This was an ordinary pre-result parser defect;
the assertion was corrected and only the invalidated local generator was
rerun. No scientific sample was consumed.

**Resources and reopen condition.** Spend was `$0`. No checkpoint was
downloaded, no hardware was claimed, no paid API was used, no provider was
contacted, and no resource was created. Reopen for one authorized,
lab-registered `gx3d-160x1792x8gaudi3` lifecycle that runs the exact revision
and source pair, measures fresh input/cache read/output plus failures at the
bound workload, validates compiled HBM fit, and clears the source-current
all-in hurdle. The full discriminator and source hashes are in
`GAUDI3_RUNTIME_PLACEMENT_SCREEN.json`.
