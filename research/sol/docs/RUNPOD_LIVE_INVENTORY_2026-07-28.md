# RunPod live GPU inventory — 2026-07-28

## Question and decision

Question: which RunPod Pod GPU types were account-visible, at what one-, two-,
four-, and eight-GPU geometries, and at what quoted prices?

Decision: RunPod is immediately useful for H100 SXM, L40S, A100 SXM, RTX PRO 6000,
and commodity-GPU experiments. A single MI300X and up to two B200s were visible but
low-stock. RunPod did not expose multi-GPU MI300X, B300, H200 NVL, or eight-GPU
H200 in this snapshot.

## Scope and method

Evidence is a measured, read-only authenticated RunPod GraphQL response retrieved at
`2026-07-28T14:28:24.905634Z`. The query called `gpuTypes` and aliased
`lowestPrice` for secure-cloud GPU counts 1, 2, 4, and 8, plus one-GPU community
cloud. It retained `stockStatus`, `uninterruptablePrice`, `minimumBidPrice`,
`displayName`, and `memoryInGb`. No provider resource was created and no credential
was retained in this artifact.

The dollar figures for multi-GPU rows are total instance dollars per hour, not
per-GPU prices. Parenthesized values are RunPod's `minimumBidPrice`; they are a
minimum interruptible bid, not a guaranteed clearing price.

## Live result

| GPU | VRAM | Secure 1x | Secure 2x | Secure 4x | Secure 8x | Community 1x |
| --- | ---: | --- | --- | --- | --- | --- |
| MI300X | 192 GB | Low $2.39/h (bid $1.99) | — | — | — | — |
| B200 | 180 GB | Low $5.89/h (bid $5.49) | Low $11.78/h (bid $10.98) | — | — | — |
| H200 SXM | 141 GB | Medium $4.39/h (bid $3.99) | Low $8.78/h (bid $7.98) | Low $17.56/h (bid $15.96) | — | Low $3.59/h |
| RTX PRO 6000 Server | 96 GB | Medium $1.99/h (bid $1.89) | Medium $3.98/h (bid $3.78) | Medium $7.96/h (bid $7.56) | Low $15.92/h (bid $15.12) | — |
| RTX PRO 6000 Workstation | 96 GB | Low $1.89/h | — | — | — | Low $1.69/h |
| H100 NVL | 94 GB | Low $3.19/h (bid $3.07) | Low $6.38/h (bid $6.14) | Low $12.76/h (bid $12.28) | — | Low $2.59/h |
| A100 PCIe | 80 GB | Low $1.39/h | — | — | — | Low $1.19/h |
| A100 SXM | 80 GB | Medium $1.49/h | Medium $2.98/h | Low $5.96/h | Low $11.92/h | Low $1.39/h |
| H100 PCIe | 80 GB | Low $2.89/h (bid $2.39) | Low $5.78/h (bid $4.78) | — | — | — |
| H100 SXM | 80 GB | High $2.99/h | High $5.98/h | Medium $11.96/h | Low $23.92/h | — |
| A40 | 48 GB | Low $0.44/h | Low $0.88/h | Low $1.76/h | — | — |
| L40S | 48 GB | Medium $0.99/h (bid $0.86) | Medium $1.98/h (bid $1.72) | Medium $3.96/h (bid $3.44) | — | Low $0.79/h |
| RTX 6000 Ada | 48 GB | Low $0.84/h (bid $0.77) | Low $1.68/h (bid $1.54) | Low $3.36/h (bid $3.08) | — | — |
| RTX A6000 | 48 GB | Medium $0.53/h (bid $0.49) | Medium $1.06/h (bid $0.98) | Medium $2.12/h (bid $1.96) | Low $4.24/h (bid $3.92) | Low $0.33/h |
| RTX PRO 5000 | 48 GB | — | — | — | — | Low $0.82/h |
| A100 SXM 40GB | 40 GB | — | — | — | — | Low $1.00/h |
| RTX 5000 Ada | 32 GB | — | — | — | — | Low $0.49/h |
| RTX 5090 | 32 GB | Medium $0.99/h | Medium $1.98/h | Low $3.96/h | Low $7.92/h | Low $0.69/h |
| RTX PRO 4500 | 32 GB | High $0.74/h (bid $0.64) | High $1.48/h (bid $1.28) | High $2.96/h (bid $2.56) | — | — |
| RTX 3090 | 24 GB | Low $0.50/h (bid $0.46) | — | — | — | Low $0.22/h |
| RTX 4090 | 24 GB | Low $0.69/h | Low $1.38/h | — | — | Low $0.34/h |
| RTX PRO 4000 | 24 GB | Medium $0.57/h | Medium $1.14/h | Low $2.28/h | — | — |
| RTX 4000 Ada | 20 GB | Low $0.28/h (bid $0.26) | — | — | — | Low $0.20/h |
| RTX A4500 | 20 GB | Low $0.25/h | — | — | — | Low $0.19/h |
| RTX 2000 Ada | 16 GB | Low $0.24/h | Low $0.48/h | Low $0.96/h | — | — |
| RTX 5080 | 16 GB | — | — | — | — | Low $0.39/h |
| RTX A4000 | 16 GB | Low $0.25/h | — | — | — | — |
| V100 SXM2 | 16 GB | — | — | — | — | Low $0.23/h |
| RTX 3080 Ti | 12 GB | — | — | — | — | Low $0.18/h |
| RTX 4070 Ti | 12 GB | — | — | — | — | Low $0.19/h |
| RTX 3080 | 10 GB | — | — | — | — | Low $0.17/h |
| RTX 3070 | 8 GB | — | — | — | — | Low $0.13/h |
| RTX A2000 | 6 GB | — | — | — | — | Low $0.12/h |

Cataloged but not stock-positive in this snapshot: B300, H200 NVL, L4, L40,
RTX A5000, RTX PRO 6000 Max-Q, and RTX PRO 6000 MIG slices.

## Uncertainty and falsification

RunPod's `High`, `Medium`, and `Low` values are qualitative labels, not device counts
or allocation guarantees. `availableGpuCounts` was null. H200 changed between
`Medium` and `Low` during two queries less than two minutes apart, demonstrating that
the result is ephemeral. Successful creation is the falsification test for actual
allocatability, but no resource was created because the question authorized a
read-only availability check, not spend.

This is Pod inventory, not a claim about Serverless Flex/Active worker availability,
physical bare metal, exact datacenter topology, or profiler-counter access. Secure
Cloud means RunPod's secure provider class; it does not establish customer control of
the host.

### Subsequent AMD check

The new factory inventory adapter queried the same account again at
`2026-07-28T14:35:56Z`. The MI300X offer was absent while 34 other GPU types remained
stock-positive. The table above remains the exact 14:28 snapshot; this later result
confirms that RunPod should be the first AMD placement attempt, not treated as reserved
capacity. The live command is authoritative:

```bash
research/factory/tools/grad-profile providers --provider runpod
```

## Sources

| Source | Revision | Retrieved | Evidence type | Use |
| --- | --- | --- | --- | --- |
| Authenticated `https://api.runpod.io/graphql` `gpuTypes/lowestPrice` response | Live | 2026-07-28T14:28:24Z | Measured primary | Account-visible Pod stock labels, geometry, and quoted prices |
| https://docs.runpod.io/sdks/graphql/manage-pods | Current | 2026-07-28 | Official documentation | Query semantics |
| https://docs.runpod.io/references/gpu-types | Current | 2026-07-28 | Official documentation | GPU identities and memory |
| https://docs.runpod.io/pods/pricing | Current | 2026-07-28 | Official documentation | On-demand and interruptible pricing interpretation |
