# Research log

## 2026-07-15 — execution-equivalent service gate and terminal mutation-route failure

Question: can the current AWQ c8/c16/c32 payload reach a scientific result when the final absolute controller first passes through the same user-systemd envelope without provider mutation?

Action: added `service_boundary.py`, bound its controller, paths, current model identity, V2 staging, SSH/cloud-init validation, inventory reconciliation, and 2,700-second contract to canonical absolute paths. The exact no-mutation `systemd-run --user` entrypoint passed: it recorded `/root/workspace` as the observed controller directory, the current 20,170,199,928-byte AWQ identity, valid one-line key/cloud-init, and empty instance/disk inventories. The same entrypoint then reached an L40S create, but the mutation controller did not leave a completed scientific terminal or summary. Its retained create diagnostic records an aborted create after the cleanup operation superseded it; direct post-run inventories were empty for both instances and disks.

Evidence: `artifacts/no_mutation_service_precreate_final/precreate-terminal.json` (`4bcc78bf...`); `artifacts/glm47_current_awq_l40s_frontier_service_boundary/provider-create-diagnostic.json` (`fa16f9b1...`); `events.jsonl` (`23dec17b...`); `systemd-service-report.json` (`3b7a86ac...`).

Interpretation: the relative-path defect is falsified and the service precreate is credible, but this route has no throughput, quality, or cost result. The aborted mutation is an artifact/controller-boundary failure, not evidence about AWQ, vLLM, L40S capacity, or batching. The project terminal rule closes Nebius for this payload; do not retry here.
