# Research log

## 2026-07-16 — Director urgent handoff

The live W4 owner passed provider create and SSH and is in runtime bootstrap, with no GPU science yet. A read-only source audit found a deterministic later failure: the controller stages `official_head_shared_w4_bind.py`, while the remote script invokes `head_shared_w4_bind.py`. Correct only that basename contract and its focused test at `$0`; do not touch the owner, provider, checkpoint, oracle, deadline, or retention behavior.

## 2026-07-16 — Director timing close

`runtime_bootstrap` completed after `404.304` seconds and the controller advanced through local-input staging to checkpoint transfer before this offline project could be scheduled. The mismatched remote script is therefore already on the instance. Close `MISSED_LIVE_STAGING_WINDOW` without editing code or interacting with the owner; prepare the correction for a fresh successor instead.
