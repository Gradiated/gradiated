# Current AWQ frontier through a validated SSH/cloud-init adapter

## Question

Can the already admitted current GLM-4.7-Flash AWQ/vLLM c8/c16/c32 experiment finally run on one L40S when launched through a locally parsed, previously successful SSH/cloud-init serialization path?

## Why it matters

The V2 scientific adapter is ready: current checkpoint/tokenizer hashes, exact 8,192-input/1,024-output rendering, prompt-logprob route, c8/c16/c32 ladder, and focused tests pass. Its final provider request was rejected before allocation because `make_cloud_init` received `/root/.config/nebius/glm-campaign/public.pem`, a 14-line PEM certificate, where cloud-init expected one SSH authorized-key scalar. Nebius reported invalid YAML at line 10. The same campaign previously created V31 successfully using the one-line `ssh_ed25519.pub`, and the durable lifecycle canary proved current Nebius create/delete semantics. This is a separately identifiable adapter path, not another model or batching repair.

No current control or intervention arm exists. Reusing the admitted payload with a locally schema-validated SSH cloud-init document is the highest-information remaining paid action.

## Relevant evidence

- `current_awq_frontier_v2/artifacts/glm47_current_awq_l40s_frontier_v2_final/provider-create-diagnostic.json`: typed `InvalidArgument`, invalid UserData YAML line 10, zero resources.
- Local metadata: `public.pem` is 800 bytes/14 lines with a PEM header; `ssh_ed25519.pub` is 101 bytes/one line with an `ssh-ed25519` type. Do not retain either key's contents.
- The retained V31 invocation used `ssh_ed25519` plus `ssh_ed25519.pub` and successfully created an L40S, reached SSH/runtime preflight, and transferred model bytes.
- `current_awq_frontier_v2` supplies the content-addressed V2 staging adapter, exact workload hash `9025685d...8924b`, experiment spec, and five passing diagnostic tests.
- The new adjacent c8 control remains the only admissible denominator; V21 is non-transferable history.

## Scope

Implement and execute in one researcher turn. Reuse the frozen project-local V2 scientific staging sources and `EXPERIMENT_SPEC_V2.json`; do not redesign the runner, workload, quality protocol, or provider controller. Create a new project-local launcher whose only provider-envelope change is the validated SSH/cloud-init path and bounded diagnostic retention.

Before create, perform executable local checks: the private key derives exactly the selected public key without emitting either value; the public file is exactly one nonempty `ssh-ed25519` line and contains no PEM markers; `make_cloud_init` produces a document accepted by a real YAML/cloud-init parser with exactly one authorized-key scalar; a negative multiline-PEM fixture is rejected; the exact serialized cloud-init bytes and launcher/source identities are hashed; the create diagnostic fixture passes; and authenticated instance/disk inventories are empty. Retain only key type, byte/line counts, comparison result, and hashes—never key contents. Missing parser tooling is an implementation task within this turn, not a reason for another readiness handoff.

If all checks pass, launch exactly one preemptible Nebius L40S through the proven independent systemd controller/watchdog using `/root/.config/nebius/glm-campaign/ssh_ed25519` and its matching `.pub`. Retain typed create diagnostics. On success, immediately load the verified current AWQ checkpoint once and execute the unchanged cache-off c8/c16/c32 ladder, current development-quality/logprob capture, telemetry, full lifecycle accounting, artifact retrieval, and two-view cleanup from the V2 contract. Each admitted background arm has a 300-second terminal envelope; interactive TTFT/TPOT are reported, not rejection gates.

This is the final Nebius provider-envelope attempt for the current AWQ payload. A typed create, SSH, bootstrap, transfer, load, workload, quality-evidence, artifact, timeout, or cleanup failure is the project result; do not repair or retry. Use at most $0.65 incremental exposure and 2,700 seconds. Arm cleanup before create, and do not overlap any other provider mutation.

## Available resources

Use shared factory tools, `campaign_100`, the complete `current_awq_frontier_v2` sources/artifacts, current AWQ cache, successful V31 invocation evidence, durable Nebius lifecycle machinery, and configured matching SSH key files. Authenticated final inventories were empty after the rejected V2 request.

## Portfolio-changing result

Promote c16 or c32 only if it is reliable, development-quality-equivalent, and lowers matched steady-state cost by at least 5% versus the new adjacent c8 control; report <=$0.60/M separately. A valid c8 without a winning arm closes batching and establishes the current control. All economics remain quality-conditional if absolute calibration is unresolved, and Cloudflare's $0.88/M listing remains unmatched. Any terminal failure closes this Nebius payload path and redirects future measurement to another provider adapter or venue; no direct delta to V21 is permitted.
