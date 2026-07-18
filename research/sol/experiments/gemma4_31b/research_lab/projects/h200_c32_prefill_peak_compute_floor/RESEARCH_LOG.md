# Research log

## 2026-07-17 — director admission

Activated as an independent `$0` lane while the actual H200 decode-attention owner runs. The measured c32 decode linears/head omit the prompt-heavy prefill phase; this project derives the most optimistic exact-geometry prefill arithmetic floor and the decode-attention threshold that remains under the campaign service ceilings.

## 2026-07-17 — terminal reconciliation

- **Question:** Does compulsory fresh-prompt arithmetic close c32, or what exact room remains for actual decode attention and all other omitted service work?
- **Action:** Bound the exact model/runtime/workload and executed shapes by hash; recomputed dense transformer GEMM FLOPs for 3,678.822 fresh tokens; derived separately labeled causal-global/sliding QK+AV sensitivity; and ran an independent implementation that does not import the calculator. Both reproducible runs were byte-stable.
- **Evidence:** The 29,396,828,160 MAC/fresh-token geometry gives a 0.21858655515963117 s/request impossible-ideal prefill-linear floor at the inventory's dense 989.5 BF16 TFLOP/s. Adding the disjoint measured decode linears/head gives 0.4433561450894726 s/request. Strict/lenient residual thresholds for actual decode attention are 0.02865567786266872 / 0.03415749866911373 s/request. The 0.01182710612323994 s/request QK+AV sensitivity narrows those to 0.01682857173942878 / 0.02233039254587379. No concurrency `/32`, analytical decode-KV floor, sparse peak, or duplicate measured component was added.
- **Interpretation:** Typed decision `c32_preserved_with_attention_threshold`; c32 is not closed by the primary disjoint floor, but only survives if every omitted component collectively fits the small residual. QK+AV remains a sensitivity because the campaign gives an aggregate cache fraction rather than a request-level cache-length distribution.
- **Artifacts:** `PREFILL_COMPUTE_FLOOR.json` sha256 `342b650c2bf61615928a5525daa773023d643af6741202f98c3384503905b68a`; independent `RECONCILIATION.json` sha256 `91e317e534294d7974b2692beeeebb49f35b0c571d63b1c7215302ce7f2fb6ff`. `$0`, zero provider/GPU use, retained storage under 1 MiB.
- **Next:** Director may compare a typed actual decode-attention result directly to the primary thresholds; this project is terminal and must not poll that owner.
