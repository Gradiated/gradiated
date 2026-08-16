# Minimal-depth-42 clean materialization

## Question

Can the five-block, 42-layer proxy be rebuilt under a new content address with a non-self-referential runtime manifest and complete checksum closure, without changing any model tensor or mutating the frozen failed root?

## Why it matters

The first paid admission stopped correctly before create: all four weight shards and 12 of 13 manifest rows match, while only `minimal_depth_checkpoint_manifest.json` differs. Inspection binds the cause to build ordering: `write_runtime_manifest` checksums that metadata file and the builder then rewrites it, making the runtime contract stale by construction. This is a materialization defect, not model, loader, L40S, or throughput evidence. The candidate still has 2,401.98 MiB projected c32 headroom and a decision-narrow 597.529 tok/s bound.

## Fixed evidence and inputs

- Frozen failed root: `/root/.cache/glm47flash-awq-minimal-depth-4c84badbce22`; do not edit, re-manifest, or use it for a provider run.
- Exact mismatch: expected metadata SHA-256 `42940771cc9de0dd1d0a509f64008a3388c770c1776c517067ad94269c901262`, observed `cb075aad0a735a46e3a580c5a4552ac42b83e6b8e7a6d5f40952701bcfd9c8c8`; all four 16,658,558,680-byte weight shards match.
- Source checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Builder: `../minimal_change_c32_codesign/build_minimal_depth_proxy.py`; proven byte-preserving student39 materializer and the failed project's `IDENTITY_PREFLIGHT.json` are fixed references.

## Scope

At `$0`, correct only materialization and identity construction. Build a fresh v2 root from source, with a v2 artifact-policy/builder identity included in the semantic derivation contract so it cannot collide with the frozen root. Limit runtime checksums to an explicit 12-file served-payload allowlist; exclude `.campaign-*`, `model-files-*`, provenance, preflight, and root-manifest files from copied payload and never checksum either runtime control file. Write provenance outside that row set only after runtime manifests are final. Derive the new root from the semantic source/mapping contract, not timestamps or the runtime manifest's own digest. Preserve the exact retained source layers, contiguous `0..41` renumbering, MTP exclusion, config semantics, tokenizer, index mapping, and every tensor payload byte.

Build one new content-addressed root atomically through a temporary directory; never mutate or alias the failed root. Prove every new weight shard is byte-identical to its corresponding failed-root shard, then run full `sha256sum -c`, config/index/key/layer closure, exact byte totals, no-symlink checks, and two independent idempotent invocations. Existing roots are verify-only: never regenerate any manifest in place. The runtime root should contain only serving inputs needed by the loader; keep audit metadata in this project. Do not edit the shared launcher or remote script while the independent FP8 provider session owns them. Do not allocate CUDA/provider resources, train, evaluate quality, or prepare another controller.

## Decision and artifacts

A pass produces one independently admissible candidate root plus exact config/index/shard/runtime-manifest/checksum-list hashes and a focused explanation of why self-reference is impossible. It may be considered for a later L40S arm only after the current FP8 session releases provider ownership and a director explicitly binds the new identity into the shared validator. Failure closes this physical-42 materialization lineage.

Produce the corrected builder or narrow companion, `CLEAN_MATERIALIZATION_RESULT.json`, a project-local immutable manifest, focused tests, and a concise `RESEARCH_LOG.md` update.
