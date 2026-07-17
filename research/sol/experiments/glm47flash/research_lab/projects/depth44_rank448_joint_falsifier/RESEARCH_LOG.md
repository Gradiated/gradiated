# Research log

## 2026-07-16 — Director opening handoff

- Test only the joint 44-layer/rank448 interaction at `$0`; do not materialize weights or prepare provider work.
- Rank448 saves an exact `1,408 MiB` of c32 KV and clears memory analytically, but the measured adjacent-depth slope plus prior MLA transfer appears below the `606.355` robustness gate.
- Close on any representation, loader, memory, endpoint-bound, or identifiability failure; nominate at most one future c32 proxy.

## 2026-07-16 — JOINT_PROXY_CLOSE

- Reconstructed the group-32 rank448 representation from the local depth42 headers: sparse `kv_a` is `[512,256]` packed plus `[512,64]` scales, and sparse `kv_b` is `[8960,56]` packed plus `[8960,14]` scales; the 44-layer projection saves `17.595 MiB` of projection payload. The pinned loader's `config.kv_lora_rank` path makes this a coherent deterministic rewrite, but no payload was written.
- The 44-layer c32 KV calculation saves `32 MiB/layer` (`1,408 MiB` total), projecting `43,746.871 MiB`, or `785.129 MiB` under the robust limit.
- Raw complete c32 profiles give depth42 `686.910494` and depth43 `636.469100` tok/s. Their adjacent-depth retention projects depth44 to `589.731731`; granting the entire scope-matched retained MLA endpoint transfer for the rank448 work reduction reaches only `594.526298` tok/s, `11.828702` below `606.355`. This is an optimistic upper bound, so no uncertainty credit is admissible.
- Terminal `JOINT_PROXY_CLOSE`; no checkpoint, CUDA, provider, or quality action occurred. Artifact: `artifacts/JOINT_PROXY_CLOSE_2026-07-16.json`.
