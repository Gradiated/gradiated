# Running the research lab

The service runs the simple lab harness through the saved Codex subscription login. Its config is outside the repository at `/root/.config/gradiated/research-lab/<name>.json`.

Install and start:

```bash
systemctl --user link /root/workspace/research/factory/systemd/gradiated-research-lab@.service
systemctl --user daemon-reload
systemctl --user enable --now gradiated-research-lab@glm47.service
```

Inspect progress:

```bash
systemctl --user status gradiated-research-lab@glm47.service
PYTHONPATH=research/factory/src python3 -m grad_research.lab_harness \
  --config /root/.config/gradiated/research-lab/glm47.json --status
```

Before replacing another service, allow any provider controller it owns to finish and clean up. Then stop and disable the old service before starting this one. Stopping the lab service preserves campaign files, research logs, project threads, and traces.
