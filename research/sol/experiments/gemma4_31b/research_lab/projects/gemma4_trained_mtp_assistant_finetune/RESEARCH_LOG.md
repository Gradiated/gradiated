## 2026-07-29T08:17Z — offline two-H200 owner bound

Question: Can the existing official Gemma assistant be fine-tuned directly through current Speculators MTP training, and can the admitted two-H200 run be launched without another preparation turn?

Action: Bound Speculators commit `aee3cc9b…`, vLLM v0.26.0 commit `568afb3a…`, the exact target/assistant revisions, and the project-local hard-linked assistant bytes. Inspected the assistant safetensors header and current MTP model/loader registry, implemented deterministic four-source train/holdout splitting, two small upstream adapters for immutable dataset selection and cross-host hidden-state transfer, and one PID-managed two-claim owner with retained repair and spend fencing.

Evidence: The assistant contains 48 tensors, zero `mtp.*` tensors, four hidden-size-1024 layers, and pre/post projections. Current Speculators MTP supports native Qwen-family MTP layers and requires a verifier `mtp.*` subtree. Direct Gemma-assistant support therefore crosses at least three adapter surfaces, so `SPECULATORS_GEMMA4_ASSISTANT_COMPATIBILITY.json` binds the contract-authorized EAGLE-3 fallback. Both patches apply to the exact upstream commit; deterministic split tests and the shared two-exact-claim lifecycle tests pass. No GPU, provider call, large download, or spend occurred.

Interpretation: The offline owner is executable after director binding. It preserves the unchanged official assistant as the stock vLLM MTP control and trains the confirmed Gemma 4 EAGLE-3 warm start through upstream `scripts/train.py`, rather than extending preparation into a custom trainer.

Next move: Director immediately registers two exact H200 benches and launches the single detached command in `TRAINED_MTP_OWNER_OFFLINE_RESULT.json`. The owner must use the shorter spend-derived deadline when two registered rates plus cleanup reserve cannot fit the nominal 4.5-hour timeout.

## 2026-07-29T08:5xZ — production pipeline owner repair

Question: Can the pre-bound two-H200 lifecycle owner execute one concrete, repairable production pipeline without treating a future director binding as its program?

Action: Added `run_trained_mtp_pipeline.py`. It validates the later execution binding, reads both claimed connection records from the pool, verifies and stages the immutable local stock assistant only after claim, stages packet files atomically, and persists content-addressed completion markers for checkout, target staging, response generation, split, relay, preparation, training, holdout, and conditional endpoint work. Its repair argv accepts only the hash-bound repair patch supplied through the owner's repair handshake and invalidates only the named stage.

Evidence: `py_compile`, the runner's zero-GPU `--validate-only` execution, and all three existing lifecycle/split tests pass. No pool, SSH, provider, download, detached owner, or GPU operation occurred. The final offline handoff binds runner SHA-256 `d5a039bd8740c79c9318ea0c14bd7418e1f5cbee751dda9be698e954d9cc83b2` and preserves owner SHA-256 `8d76dd5a94f9bf6d837324eeb999126a7bc6a634cc9ee889e1b138ecafd3deb0`.

Interpretation: The remaining boundary is the director's execution binding and spend/lifecycle fit, not missing project-local production code. No scientific sample is consumed.

## 2026-07-29T09:08Z — pre-science owner attempt

Question: Does the bound owner reach packet staging on the two exact H200 claims?

Action: Launched at 09:07:47Z; target and trainer were claimed at 09:07:47.942Z and 09:07:47.951Z. The first packet-stage remote command failed before staging or CUDA because SSH split the unquoted `bash -lc` program. A packet-stage-only repair was requested through the retained handshake.

Evidence: `pipeline.stderr.log` records `mkdir: missing operand`, with no stage marker, remote artifact, server, CUDA marker, request, or terminal. `repair-command.json` records the second pre-science defect: `TRAINED_MTP_ABSOLUTE_DEADLINE_UTC is required`. That exception escaped the repair loop, so the owner released both benches to maintenance at 09:08:49Z. Conservative cumulative exposure is $2.541734; no sample was consumed.

Interpretation: This is invalid controller evidence, not a model/runtime result. The runner now transports remote programs as one quoted argument; the owner now supplies the deadline to repair commands and retains claims on repair-command failure. Their changed hashes require director inspection, bench re-ready, and a new binding; this project must not reclaim either maintenance bench.

## 2026-07-29T10:36Z — g11 regeneration import repair submitted

Action: Revalidated owner PID 4050908/start ticks 143316077 and both original claims, then submitted g11 repair request `023d47b7…` with patch `709e4fe7…`.

Evidence: The response-generation stage had no generated files and never issued a target request. `datasets==5.0.0` is present and the target health endpoint succeeds; the local Speculators checkout contains `hs_connectors`, but its distribution was not installed, leaving only a namespace package and causing the `FileTransfer` import failure. The patch archives that empty root, installs only the declared local connector package, and smokes the actual `speculators.data_generation` import boundary before the unchanged regeneration commands.

Interpretation: This remains a pre-science integration repair. The owner retains the working target engine and retries only `regenerate_shards`; no target checkpoint, assistant, dataset selection, training geometry, or scientific stage is replayed.

## 2026-07-30 — zero-GPU speculative-decoder pilot

Question: Can existing exact Gemma 4 token traces train a useful speculative decoder on CPU, without another target or trainer GPU?

Action: Reconstructed all 32 response sequences from the raw per-request `token_ids` artifacts and held out requests 18, 28, 29, and 30, matching the prior request-disjoint split. Trained a 46,450-parameter copy-distance/vocabulary MLP for 40 epochs on 9,996 next-token examples. The decoder uses token-identity-invariant equality features so it can copy token IDs absent from the training vocabulary. Compared depth-4 exact prefixes against latest-token copy, a training-corpus n-gram, and the existing in-request n-gram.

Evidence: Training used `torch==2.13.0+cpu`, with CUDA unavailable, and completed in 3.90 seconds. Loss fell from 0.49005 to 0.01077. On 1,356 holdout positions, the learned decoder accepted 3.005 draft tokens per verification; deterministic in-request n-gram accepted 3.934, achieved full depth on 98.23% of positions, and had about 100x lower controller-CPU draft time. Only one of 22 holdout token IDs occurred in training. The earlier causal-offset dataset was also found invalid for this use: 3,461/4,096 training rows and 497/512 holdout rows repeat one current token across all 16 alleged future labels, explaining its near-zero training loss and one-token measured acceptance.

Interpretation: CPU training is feasible, but this learned decoder should not be integrated into an endpoint. The synthetic c32 completions are highly repetitive and deterministic in-request n-gram is already near the depth-4 ceiling. This is a measured mechanism negative, not evidence against a trained hidden-state-conditioned Gemma assistant on realistic traffic.

Next move: During a normal target experiment, capture realistic request-disjoint output sequences and the exact target hidden-state tensor consumed by the stock Gemma assistant. Preserve those artifacts once; then fine-tune the small assistant or a narrow adapter on CPU and request GPU time only for matched endpoint verification if its held-out accepted-prefix efficiency beats stock and n-gram controls.
