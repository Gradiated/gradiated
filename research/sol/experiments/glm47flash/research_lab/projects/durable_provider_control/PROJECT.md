# Actual-path Nebius cleanup canary

## Question

Can the proven external controller/watchdog create and delete one short-lived L40S instance with its managed boot disk through the same Nebius path used by scientific runs, leaving both direct and inventory views empty?

## Why it matters

The standalone-disk canary failed before creation and discarded command diagnostics, so it is an observability failure rather than evidence that Nebius cleanup is unsupported. The actual instance-attached path is already campaign-proven and is the relevant final gate before the quality capture. One bounded canary is faster and more decision-relevant than repairing an unused standalone-disk interface.

## Relevant evidence

- The passing zero-provider lifecycle proof at `artifacts/run-20260715T1035Z/`.
- The disk-canary failure at `artifacts/nebius-disk-canary-20260715T1045Z/` and the latest `SUPERVISOR_LOG.md` finding that its diagnostics were not retained.
- Existing instance-plus-managed-disk creation and cleanup controls under `campaign_100/nebius/`.
- Current authenticated inventory is zero instances and zero disks.

## Scope

Run exactly one preemptible L40S instance-plus-managed-boot-disk lifecycle canary through the proven systemd controller/watchdog boundary. Do not SSH, bootstrap a runtime, transfer a model, or run GPU work. Use content-bound names, a 300-second absolute deadline, and a $0.10 all-in cap. Observe instance and disk in direct and inventory views, delete through the durable cleanup path, and require GET-not-found, empty inventories, controller/watchdog terminal state, exposure, and cost evidence.

Every external command failure must retain a bounded credential-redacted diagnostic with stage, command identity, exit code, stdout, stderr, and hash before transient collection. If create fails, classify from that artifact and stop. If any resource ID is returned, cleanup remains mandatory. No retry or repair is authorized in this project.

## Available resources

Use the passing project-local lifecycle proof, factory ledger/systemd interface, and existing Nebius placement controls. This project is sole provider-mutation owner for this canary only; all scientific projects remain prohibited from provider mutation.

## Portfolio-changing result

A pass immediately releases provider ownership for the $4.27 quality capture. A typed failure keeps paid science closed and supplies the exact provider/control defect for the next director decision. Either outcome completes this project.
