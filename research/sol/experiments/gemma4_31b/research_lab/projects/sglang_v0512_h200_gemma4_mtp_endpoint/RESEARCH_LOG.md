# Research log

## 2026-07-18T09:19:34Z — director admission

The B200 full-stack bound closes even under an impossible free-queue/zero-linear envelope, while the simple weight-structure screen and W4 line are also terminal. Current official SGLang v0.5.12 is a materially different exact-model route: it explicitly adds Gemma 4 and Gemma 4 MTP plus full-stack fusion/overlap changes in the residual categories left unattributed by vLLM. H100 is excluded by the bound SGLang static-memory configuration; measured H200 BF16 linears/head and KV floors preserve c32. Activate one retained H200 stock-then-MTP endpoint under 140 wall/85 provider minutes, 1.4167 H200-hours, one 250-GiB disk, and `$3.75`. Provider create is gated only on the content-hashed assistant and immutable bindings; ordinary execution defects are repaired in place.

## 2026-07-18T09:27:54Z — retained execution launched

Action: verified every bound local artifact hash, materialized the public assistant at its pinned revision (five files, 971,215,445 bytes), and launched the admitted user-systemd development owner. The owner passed `PRECREATE_TERMINAL.json`, created H200 `computeinstance-e00v1y11h92cdp0y9b`, bound its 250-GiB disk and independent cleanup watchdog, transferred the assistant, and began the 62.58-GB target checkpoint transfer. Its scoped deadline is epoch `1784371871`; all stock/MTP execution remains in this one retained session. The pinned v0.5.12 cookbook resolves the native Gemma assistant to `NEXTN`; the owner uses its one-token contract (`--speculative-num-steps 1 --speculative-num-draft-tokens 1 --speculative-eagle-topk 1`) for the matched second arm.

## 2026-07-18T10:21:46Z — stock market pass; native MTP typed image boundary

The stock readiness predicate falsely timed out despite a healthy `/v1/models`; retained server logs established real readiness. The first trace invocation exposed a runner defect: its content-bound request bytes set streaming, so its JSON consumer observed empty HTTP-200 bodies. Repairing only the runner to submit identical requests with `stream: false` produced 32/32 nonempty exact 4,214-prompt/358-completion responses in 11.625702 batch seconds: `2.752522` completed requests/s and `0.363303 s/request`, a market pass against the `0.472012 s/request` ceiling. The retrieved raw bundle is `artifacts/sglang-v0512-h200-mtp-20260718t0925z-owner/stock-repaired.tar.gz` (SHA-256 `760dba65d275716a997887dc970b5c67dbefa0ac2802ffb78dcfeddd8eca9f73`).

The matched resident NEXTN restart was then attempted with the pinned assistant and one-token arguments. It failed before model load because the immutable image's installed Transformers does not recognize `model_type: gemma4_assistant`; the full typed traceback is retained in `mtp-failure.log`. Changing Transformers would change the bound image, so MTP is an invalid image-bound arm rather than a performance result. A teardown decision was supplied to the retained owner's authenticated cleanup path.
