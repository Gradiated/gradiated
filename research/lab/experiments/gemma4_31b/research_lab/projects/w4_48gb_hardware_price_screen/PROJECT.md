# W4 48-GiB hardware and price screen

## Decision question

If the live L40S W4 Marlin mechanism passes, is A40 or RTX 6000 Ada a materially cheaper production target for the exact campaign workload, or does L40S remain the only justified 48-GiB candidate?

## Why now

The corrected W4 c16 bound fits within 48 GiB and the live owner is measuring the SM89 L40S mechanism. Production venue is not fixed to the experiment provider. The shared inventory also contains A40 (SM86, 48 GB, 696 GB/s) and RTX 6000 Ada (SM89, 48 GB, 960 GB/s), but the fresh shared price file has no planning rate for either. A price-normalized threshold can decide whether either deserves a later matched measurement without waiting for the live terminal.

## Authoritative inputs

- `../gemma_l40s_w4_c16_economic_bound/W4_C16_BOUND_V2.json`, SHA-256 `b697e8c43bcdecac9b0261ab79e363b39e11e9c37a0be282d357a21c9e24fe9d`.
- `../gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json`, SHA-256 `3ac9ff0868ed63bd06bb263c78576ba8d00c67244a1ca636e82f00be65ed8aad`.
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`, SHA-256 `690e0e457c6e8e9121b54fb7f88abc92c3dcc358e1d71accffddb083878d00d6`.
- `/root/workspace/research/factory/data/gpu_prices.json`, SHA-256 `3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01`, measured fresh at 1.688 days this director turn.
- `/root/workspace/research/factory/data/accelerator_inventory.json`, SHA-256 `bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8`.

Do not refresh or duplicate the shared L40S/H100/H200/B200/MI355X price search. Public evidence may be checked only for the missing A40 or RTX 6000 Ada candidate/rate/topology, and must be labeled as marketplace, on-demand, or vendor evidence rather than a committed planning quote.

## Required evidence

Reconcile capacity, pinned-vLLM Marlin device/runtime support, tensor format, SM/tile/occupancy differences, memory bandwidth, L2, power, and likely decode weight-stream behavior for L40S, A40, and RTX 6000 Ada. Use the exact W4 active stream, c16/c32 logical totals, six Gemma shapes, and campaign request mix. Do not transfer L40S throughput to another GPU as a claim.

Derive for each candidate:

- the maximum 12–24 month production price that would beat L40S at equal all-in cost under bandwidth-proportional, conservative efficiency-discount, and measured-live-terminal-parameterized cases;
- the minimum matched throughput ratio required at any observed public rate;
- capacity/allocator and consumer-support failure modes;
- whether its likely grid, register/shared-memory, cache, or instruction behavior makes bandwidth scaling an unsafe prior.

Return at most one conditional matched-GPU nominee. Nominate only if current evidence or a clearly stated price ceiling makes at least a 10% all-in cost improvement plausible and the actual Marlin consumer is supported. Otherwise emit typed `none`. A nominee is conditional on a passing live W4 mechanism and must require fresh matched CUDA/whole-workload evidence plus a current written committed quote before any production claim.

## Limits and artifacts

- Wall clock: 45 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 1 GiB project-local, including at most 64 MiB bounded public/source probes; no shared `/tmp`.
- Spend: `$0`; no provider mutation, reservation, compilation, or full-weight download.

Write `HARDWARE_SCREEN.json`, concise `DECISION.md` and `RESEARCH_LOG.md`, and terminal `STATUS.json`. Evidence must be labeled measured, inventory, first-party source, vendor/marketplace, derived, or inferred.
