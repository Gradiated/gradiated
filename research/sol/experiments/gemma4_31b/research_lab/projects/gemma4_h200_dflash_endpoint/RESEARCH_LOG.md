# Research log

## 2026-07-24 — bind one executable DFlash route

Action: selected SGLang because PR #23000 is merged. Bound merge commit
`588d1f7bc9424201f89957e145f9d5af633a3eb8`, draft revision
`eabd648301ce28583cc14757912e5e0f84e152e1`, Dockerfile/dependency hashes, and
the DFlash worker/Triton source hashes in `DRAFT_RUNTIME_BINDING.json`. Added a
project-local AR/DFlash workload consumer, reconciler, and remote build/run
script. `bash -n`, `py_compile`, and binding-schema validation passed.

Evidence: the source registers `DFLASH`, supports a 16-token draft block and
the immutable draft revision, and contains target-hidden/KV state guards. vLLM
PR #41703 remains open. This is source-backed/offline integration evidence, not
a GPU performance or quality result.

Next: director registration of one independent H200 within the $28 authority;
the exact request is `DIRECTOR_REQUEST.json`. The shared NGRAM bench was not
claimed.
