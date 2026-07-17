# Depth42/depth43 quality-signal adjudication

## Question

Does the frozen six-case V1 development screen contain an unambiguous quality improvement from depth42 to depth43, or is the apparent `1/6` to `0/6` ordering caused by transport formatting or an underspecified exact-match contract?

## Why this matters

Depth42 and depth43 both pass the campaign's architecture-cost gate, but serially restoring another layer is justified only if the existing cheap screen carries a real recovery-direction signal. The raw rows show the same substantive continuation failure in both candidates, while depth43's only additional lost point is `K-4702: amber-orbit-17` versus the value-only `amber-orbit-17`; the calibration audit already marks that retrieval contract underspecified. Depth43 also has lower teacher-forced NLL (`7.507868` versus depth42 `7.582577` and the carried control `7.645514`). A bounded artifact adjudication can prevent either discarding a useful cost proxy or buying depth44 for a spurious quality trend. It is directional candidate selection, not broad evaluation or a quality claim.

## Fixed evidence

- Depth42 archive SHA-256 `ee0f3f3b3d3abfa2f9610320a5be44934be8493a61f52a0d339e83ca4b3d8541`; archived raw-response SHA-256 `780d4c7a3bc4b600d8437d60cf3a3e729c3348c6a9b5be5c58fec0f9740bdf94`; paired-quality SHA-256 `43a74cb23689710f4b080b2a7e8ac0eb8fc05a9091a0e1bf33b1e75d0707e6a6`.
- Depth43 archive SHA-256 `8db63070ed174a9710f181e17d3cb747f9ca70b54775ee6eaf0bfa3beaad8120`; archived raw-response SHA-256 `d3c4f443d096c1765da64c5c8e12f2a6828c5d63dc20f04dcf8b733c0856a8ec`; paired-quality SHA-256 `6e54fe59ac7c2cf13365eae9a8dc1ec126686339d1ed50a0d4cf83792f36aeb5`.
- Frozen V1 suite: `../../../campaign_100/quality/development.jsonl`, SHA-256 `350d35be3267bb08a47fea8046fa2eab78e7be1cdfc08f64c0c239f9bbf66681`.
- Existing boundary policy: `../quality_gate_calibration/ARCHIVED_RESPONSE_BOUNDARY_AUDIT.json` SHA-256 `bb2d78e82a707c06e3d58709f1fb9dabecfd17b12379d050c7c32c60fd8104f8` and `audit_archived_quality.py` SHA-256 `5f1b866a38c7dd194e7f8fb8f084799f267f56772c6b0c4613bc7fbcf9607efd`.
- V2 control context only: `../bf16_v2_capture_adjudication/BF16_V2_CONTROL_ADJUDICATION.json` SHA-256 `393cb6e89cb8c4b8b2b6de4c2f8da98507129805fa898d85c511dbee7d56f49c` and `BF16_V2_NLL_CEILINGS.json` SHA-256 `849e057d0dcb6b4d76c6d11093d3e7ce9a6a7e4915b8a6ca3735957889477eff`. Do not transfer V2 scores to these V1 candidates.

## Execution contract

Work offline at `$0` for at most 600 seconds, 2 GiB peak RSS, and 16 MiB of new artifacts. Verify both archive and internal identities, extract only the bound V1 quality rows, and reproduce the frozen V1 scores unchanged. Then apply only the already-approved fail-closed fence normalization and category-boundary reasoning from the calibration artifacts. Classify every depth42/depth43 delta as transport formatting, underspecified contract, or unambiguous semantic behavior. Preserve the original scores and prompts; do not repair a response, edit a scorer or expectation, generate a new case, inspect a holdout, call a model, use CUDA, or access a provider.

Return exactly one terminal result:

- `SERIAL_DEPTH_CLOSE`: no unambiguous semantic improvement from depth42 to depth43; do not fund depth44 on quality-restoration grounds and preserve depth42 as the eventual V2-canary finalist;
- `DEPTH43_SIGNAL`: at least one unambiguous semantic improvement survives the frozen boundary audit, making depth43 the later V2-canary finalist; or
- `EVIDENCE_CLOSE`: an identity or exact-reproduction mismatch prevents adjudication.

Produce one compact decision artifact and a concise research-log update. No provider preparation, broad quality work, training, or successor project.

## Available resources

Use only the fixed projects above, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
