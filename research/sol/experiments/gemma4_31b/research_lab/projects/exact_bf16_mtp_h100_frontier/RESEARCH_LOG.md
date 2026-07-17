# Research log

No researcher turn has completed. The first action is the bounded exact BF16 control and matched MTP experiment in `PROJECT.md`.

## 2026-07-16 — durable stock owner launched

Question: establish the exact pinned BF16 H100 stock control before considering MTP.

Action: grouped preflight resolved `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, its two accessible 62,546,177,752-byte BF16 shards, assistant revision `627c5ec1458b9086b841a91e0512fd31fd2fbbf1`, and `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`; Nebius inventory was empty. Started the bounded systemd owner `gemma-bf16-h100-owner.service` and a separate existing-controller cleanup watchdog.

Evidence: `artifacts/preflight-20260717T000000Z/`; owner artifact root `artifacts/gemma-bf16-h100-20260716t2210z/`. The grouped ownership snapshot recorded durable PID/cgroup, watchdog, deadline, and `computeinstance-e00pmr66j0jjafxy1r` in `STARTING` state.

Interpretation/next move: this is an executed provider experiment, not readiness. Do not launch another allocation or wait/poll it; reconcile its typed terminal and verified cleanup on the next scheduled turn.

## 2026-07-16 — one allowed remote-workspace correction launched

Question: recover the exact BF16 stock run after the pre-GPU workspace failure without changing model, runtime, provider lifecycle, or experimental scope.

Action: the first owner’s `remote.stderr.log` gives the typed cause (`mkdir: cannot create directory '/workspace': Permission denied`), while `cleanup.json` verifies zero matching resources. Reused the same owner/controller and changed only the remote workspace to `/home/glmrunner/gemma-workspace`, including the container bind mount and retrieval paths. The corrected owner is `gemma-bf16-h100-corrected-owner.service`; first-attempt provider exposure was 125.189 seconds, so its deadline was reduced to keep combined exposure within the three-H100-hour budget.

Evidence: corrected artifact root `artifacts/gemma-bf16-h100-20260716t2215z-corrected/`; grouped snapshot records durable PID/cgroup, `gemma-bf16-h100-corrected-external-watchdog.service`, deadline `1784250936`, and named resource `computeinstance-e00ghtyvrzrnxe00tn` (provider-visible, reconciling).

Interpretation/next move: corrected paid execution is active. Do not create another allocation; reconcile only the owner’s typed terminal, retrieved scientific artifacts, exposure, and cleanup on the next turn.
