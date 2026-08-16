# Research log

## 2026-07-15 — current exact-model scan and portfolio decision

- Question: Does current exact-model evidence identify a non-duplicate mechanism with a credible path to the campaign's 5% cost gate?
- Action: Audited the official Z.ai/Hugging Face model card and pinned model revision, official vLLM recipes, current exact-model derivative metadata/cards, and retained A40/comparator artifacts. No credentials, provider requests, allocation, or paid action was used.
- Evidence: `zai-org/GLM-4.7-Flash@7dd208...` is a 30B-A3B MoE. Official vLLM guidance documents GLM-4.7-Flash, FP8/BF16 serving, MTP, and an 8k/1k benchmark recipe, but its numeric example is GLM-4.5-Air and is not transferable. `cyankiwi/GLM-4.7-Flash-AWQ-4bit@87c9a07...` is 20.2 GB, documents AWQ v1/group-32, a vendor-reported 0.417% perplexity delta, vLLM/SGLang paths, and no MTP. `unsloth/GLM-4.7-Flash-NVFP4@98b036...` was modified today, contains a separate MTP file, but has zero downloads and no quality/throughput evidence. A40 remains a catalog-only $0.44/hour lead with 192.022 tok/s required at the 5% gate; capacity is closed by the separate typed RunPod control-plane failure.
- Interpretation: Promote only a conditional fresh AWQ replay against the active runnable-control project, keeping measurement venue (Nebius L40S if its gates pass) separate from production hypothesis (A40 or another verified 48 GiB venue). Park NVFP4 until an offline loader/format gate and Blackwell venue exist. Do not reopen MTP, already closed by its dedicated project, and do not treat the Cloudflare $0.88/M anchor as matched.
- Cheapest falsifier/admission: Offline bind the AWQ revision, tokenizer, config, shard manifest, and quality-contract compatibility. Admit a future arm only after exact load and memory residence pass, then quality/SLO and sustained >=192.022 tok/s; stop on any identity, load, quality, SLO, or artifact failure. No benchmark or provider mutation is authorized by this scan.
- Next move: Director may allocate one bounded AWQ replay only after the runnable-control project supplies a current content-addressed control; otherwise retain the result as a useful conditional scan.

See [SCAN_2026-07-15.json](./SCAN_2026-07-15.json) for revisions, source identities, candidate ranking, break-even calculations, and claim boundaries.
