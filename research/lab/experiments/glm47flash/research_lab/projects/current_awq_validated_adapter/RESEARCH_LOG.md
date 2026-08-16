# Research log

## 2026-07-15 — validated cloud-init preflight and terminal controller launch failure

Question: can the admitted current-AWQ c8/c16/c32 payload reach one L40S through the proven SSH/cloud-init serialization path?

Action: added a project-local wrapper around the frozen V2 scientific launcher. It derived the configured private key in memory, compared it to the configured one-line `ssh-ed25519` public key, parsed the generated cloud-init with `PyYAML.safe_load`, asserted exactly one authorized-key scalar, rejected a synthetic multiline-PEM fixture, and retained hashes/metadata only. The wrapper and all five frozen V2 focused tests passed; authenticated precreate inventories were empty. The typed create-diagnostic fixture passed. Started the one bounded external user-systemd controller service.

Evidence: [validated precreate report](artifacts/glm47_current_awq_l40s_frontier_validated_adapter/validated-adapter-precreate.json) records key-pair equality, a 101-byte/one-line `ssh-ed25519` public file, one parsed authorized-key scalar, and content identities without key material. [Systemd launch diagnostic](artifacts/glm47_current_awq_l40s_frontier_validated_adapter/systemd-launch-diagnostic.json) records exit 2 before Python started: systemd resolved the relative wrapper path under `/root/research/...`, which does not exist. It records `provider_create_reached: false`; direct post-failure instance and disk inventories were both zero.

Interpretation: the malformed PEM/cloud-init cause is locally falsified for this matching key path, but no provider request, allocation, runtime, quality capture, or c8/c16/c32 workload occurred. This is a typed external-controller launch failure, not AWQ/vLLM/batching evidence. Per the one-attempt terminal rule, do not change the relative-to-absolute controller binding and retry here.

Next move: if the campaign needs this payload, admit a separate project whose precreate contract executes and verifies the external controller's absolute source binding before any provider mutation.
