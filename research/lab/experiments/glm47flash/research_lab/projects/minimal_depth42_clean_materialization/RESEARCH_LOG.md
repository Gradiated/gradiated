# Research log

Opened after the first student42 admission found a single stale metadata checksum with all weight shards intact. This project owns one clean, non-self-referential rematerialization at `$0`; it does not own the provider or shared launcher.

## 2026-07-16 — v2 clean materialization PASS

Question: can the physical-42 proxy be rebuilt under a fresh content address with complete closure and no runtime-manifest self-reference?

Action: added `build_clean_materialization.py` with a semantic v2 contract containing the source revision/config/index, exact 0..41 layer mapping, skipped layers `(6,15,24,33,42)`, explicit 12-file served-payload allowlist, excluded runtime controls, and builder identity. It builds atomically through `/root/.cache/minimal-depth42-v2-*`; existing roots are verify-only. Added focused policy tests.

Measured evidence: `/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1` passed full `sha256sum -c` for all 12 payload rows; all four 4,998,492,120 / 4,997,404,256 / 4,626,447,304 / 2,036,215,000-byte shards match the frozen failed root byte-for-byte; config/index/key/layer closure, exact index tensor payload (`16,654,390,736` bytes), no-symlink, and runtime-row closure checks all pass. Two independent invocations produced identical result artifacts (`cddf427700dc0f9b60c9ac757a5101974fce102634bb7622ea3f4c5d171aa46c`). No CUDA/provider activity occurred.

Future admission identity: contract `5dbf26dc16a1cabbdb36eb256a996a11cf44c71c702b72686806a68a3bb1a290`; root basename `glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1`; runtime manifest `cfee71f350b69a931bc6700712db9850780c30f2e8aa51a406ce9ac7a668cdda`; checksum list `87d080fa3b10a184abf39e050f6dd67264b32394b43d45caecd93d32e3512950`. The runtime root contains no provenance, preflight, campaign, or root-manifest file; self-reference is structurally impossible because controls hash only the explicit payload allowlist.

Interpretation/next move: this closes the materialization defect and is independently admissible for a later L40S arm only after the current provider owner releases the session and the director binds this exact identity into the shared validator. Quality and loader instantiation remain deferred by scope.
