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

## 2026-07-23 — independent H200 execution started

Claimed `h200-dflash-e00q45wf04571cb67n`; H200 identity, driver 580.159.04,
Docker 29.5.3, and 225 GiB free disk were measured. The first remote owner
failed before source build because `/work` is not writable; the second reached
the pinned source checkout but lacked Docker-socket access. Both are
pre-invocation wiring defects with no model server, CUDA candidate, or workload
request. The claim remains active. Repair 2 uses a writable remote work root
and `sudo docker`; it is building the immutable SGLang image and retains source
and downloaded layers. Artifacts: `artifacts/dflash-h200-20260723t2343z`.
