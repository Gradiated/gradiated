# Task: 2026-07-15-whatsapp-research-results

## Outcome

Completed researcher results can be delivered to the user's WhatsApp without coupling messaging failures to the research loop; credentials and recipient data remain outside the repository.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/18
- GitHub project:
- owner: codex-whatsapp-notifier
- Codex thread:
- created: 2026-07-15T09:31:46+00:00
- started: 2026-07-15T09:31:46+00:00
- last updated: 2026-07-15T09:31:46+00:00
- scope: research/factory/src/grad_research/result_notifier.py,research/factory/tests/test_result_notifier.py,research/factory/tools/whatsapp_cloud.py,research/factory/systemd/gradiated-research-notifier@.service,research/factory/README.md,research/factory/pyproject.toml,tasks/active/2026-07-15-whatsapp-research-results.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: Immediate concise WhatsApp updates let the user monitor a 24/7 research factory without opening Codex while preserving research throughput.
- acceptance checks: Formatting, deduplication, template payload, and retry isolation tests pass; notifier service is installable independently.
- quality gate: Never commit credentials or phone numbers; never block experiments on notification delivery.
- SLO or budget: Poll within 10 seconds; HTTP timeout 20 seconds; no messaging spend until the user configures and enables Meta Cloud API.
- timeout: 45 minutes.
- artifact locations: `result_notifier.py`, its tests, systemd unit, runtime notifier state and notification JSONL.
- resume command: `PYTHONPATH=research/factory/src python3 -m unittest research/factory/tests/test_result_notifier.py -v`
- rollback or cleanup: Disable the notifier unit; it does not alter the research-lab service.

## Plan

1. Add an independent event-tail notifier and compact result formatter.
2. Add WhatsApp Cloud API text/template delivery with retry isolation.
3. Verify and install the service, leaving credential activation to the user.

## Result

- status: waiting_user_configuration
- verification: Seven focused notifier/harness tests passed; Python compilation, skill validation, DevEx, and systemd unit linking passed. The notifier instance remains disabled and inactive.
- changed paths: `result_notifier.py`, `test_result_notifier.py`, `gradiated-research-notifier@.service`, `research/factory/README.md`, and `research/factory/pyproject.toml`.
- limitations or blocked paths: No WhatsApp Cloud API access token, business phone-number ID, approved utility template, or recipient number is configured. These values must remain outside version control.
- commit:
- next action: User creates `/root/.config/gradiated/research-lab/whatsapp.env`; then enable and send one test notification before leaving the service active.
- released: 2026-07-15T09:34:30+00:00
