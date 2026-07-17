# Research log

## 2026-07-16 — Director opening handoff

- Decision: Replace the terminal SGLang audit with one `$0` external-draft fail-fast gate while the no-weight n-gram candidate remains under its sole durable provider owner.
- Fixed target: exact AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, L40S c16 cache-off 8K/1K, ordinary `594.466` and robust `606.355` output tok/s.
- Strong prior: the smaller `1.543-GiB` native MTP addition loaded but left only `167.38 MiB` free and then failed a `562-MiB` allocation during c16; external-draft residence must be reconciled to this measured boundary.
- First action: inspect the smallest credible public GLM-family draft and fail immediately on token-ID mismatch before runtime, memory, or acceptance analysis.
- Guardrail: At most two candidates; no full-weight download, CUDA, provider action, patch, conversion, training, or controller preparation.

## 2026-07-16 — terminal identity closure

- Question: Does a compact public GLM-family draft survive the first exact token-ID gate?
- Action: Inspected the smallest credible public candidate, `thoughtworks/GLM-4.7-Flash-Eagle3`, at Hugging Face revision `c43b5f18f59b8fba69e8c0d585fb0e614cf42af1`. Retrieved only official repository metadata and `config.json`; no weights, CUDA, runtime, or provider action.
- Evidence: The candidate declares `vocab_size=154880` but `draft_vocab_size=32000`, BOS `151329`, and EOS `151336`. The exact target config declares vocab `154880`, BOS `0`, and EOS `[154820,154827,154829]`. The candidate repository exposes only `config.json` and `model.safetensors`, with no tokenizer mapping assets. These are measured metadata/config facts; the public model card's 54.9% acceptance and 1.66x H200 result are not transferred because identity already fails and workload/runtime/chip differ.
- Decision: `IDENTITY_CLOSE`. Since special-token IDs and draft token space do not bind exactly and no translation-free mapping is available, stop before pinned-runtime, c16 residence, or acceptance economics. Do not inspect a second candidate under the terminal stop rule.
- Artifact: [external_draft_identity_gate_2026-07-16.json](external_draft_identity_gate_2026-07-16.json)
