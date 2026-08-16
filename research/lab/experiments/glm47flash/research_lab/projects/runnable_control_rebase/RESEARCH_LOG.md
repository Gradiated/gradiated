# Research log

## 2026-07-15 — fresh-identity precreate gate

**Question.** Can the project safely create its one L40S allocation and obtain a fresh c8/c16/c32 result rather than repeating the frozen-V21 failure?

**Action.** Ran `precreate_gate.py`, a zero-provider gate that re-hashes every local current-AWQ manifest file, attempts deterministic construction of the required 32-record 8,192/1,024 corpus, proves a fake terminal artifact through an external user-systemd unit, checks the available controller key without reading it, and observes authenticated Nebius inventory. The test and artifact are `precreate_gate.py` and `artifacts/PRECREATE_GATE_V1.json`.

**Evidence.** All 12 current public-AWQ files, including 20,170,199,928 weight bytes, match revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; the fresh tokenizer hashes are `353a3ff…` / `b6b807…` / `d63ad5…`. The fake external terminal passed and authenticated instance/disk inventories were each zero. The profile SSH key exists. Corpus construction failed before create because the local executable environment has no `transformers` module. More importantly, the only current L40S execution path (`vllm_smoke_control.py` plus `remote_vllm_awq_smoke.sh`) hard-requires the invalid frozen V21 tokenizer hashes and frozen quality artifacts, and no actual-endpoint adapter can capture the required 36-case raw prompt/input-logprob evidence for this new identity.

**Interpretation and next move.** This is a precreate operational/scientific falsifier, not a result about c16 or c32: no provider resource was created and $0.00 of the $1.00 cap was spent. The new current checkpoint is integrity-valid, but the campaign has no runnable fresh-identity measurement adapter. Do not repair V21 or create an L40S from this project. A later project may implement and locally prove one fresh tokenizer/workload builder plus endpoint-quality adapter, then re-run this gate before requesting a new allocation.
