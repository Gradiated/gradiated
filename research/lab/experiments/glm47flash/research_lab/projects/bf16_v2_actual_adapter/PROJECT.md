# Actual BF16 V2 capture adapter

## Question

Can the already implemented historical H100/V13 control path be converted, in one bounded zero-provider turn, into the actual execution-equivalent adapter required by the frozen 36-case BF16 development calibration contract?

## Why it matters

Campaign economics remain quality-conditional. The authoritative complete BF16 revision `33facc...`, its 48 shards, the sealed 36-case development suite, V2 artifact validator, fake controller proof, and systemd timeout/cleanup proof all exist. The quality project correctly stopped because no actual adapter connects real H100 bootstrap, checkpoint transfer and verification, runtime launch, capture, artifact retrieval, and cleanup to that V2 contract. This is the one finite implementation gap blocking calibration; it must not become another provider-readiness lineage.

## Scope

Implement and independently test one actual adapter by reusing the historical `campaign_100/nebius/stock_control.py` H100/V13 primitives and the existing `quality_gate_calibration` V2 capture/artifact contract. Bind the complete revision, tokenizer/runtime hashes, 36-case development fixture, all three cold-start phases, raw responses, normalized/scored outputs, prompt token IDs/logprobs, phase telemetry, cost, and two-view cleanup evidence. The holdout stays sealed.

Use test-driven fixtures for successful capture, missing artifact, identity mismatch, remote failure with redacted stdout/stderr, deadline, and cleanup failure. Exercise the final absolute-path controller through the same service manager, user, working directory, environment, arguments, and artifact destination in explicit no-mutation mode. The result must be an actual code path capable of provider use, not another fake-only wrapper, schema design, preregistration, or proof that the historical controller is unsuitable.

Do not create an instance, call a provider mutation API, generate model outputs, unseal holdout, change prompts/scorers/threshold policy, or authorize the later H100 spend. Budget is $0 and provider ownership is prohibited. Stop after one implementation/review turn: either the execution-equivalent no-mutation contract passes with a content-bound adapter, or record a typed terminal implementation blocker and close.

## Evidence and artifacts

- `quality_gate_calibration/BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json` and executable 36-case suite.
- `quality_gate_calibration/V2_CAPTURE_CONTROLLER_PROOF.json`, `V2_SYSTEMD_CAPTURE_PROOF.json`, validators, and `ACTUAL_ADAPTER_PREFLIGHT.json`.
- Historical complete V13 H100 controller and archived allocation contract under `campaign_100`.

Produce focused tests, a no-mutation terminal artifact with source and contract hashes, an adversarial review checklist, and a concise research-log handoff. Do not modify or reopen `quality_gate_calibration`; the director will decide that only after this project completes.

## Portfolio-changing result

A passing actual adapter makes the existing quality calibration eligible for one later director-authorized H100 session under its frozen $4.27/3,600-second cap. Failure closes this implementation attempt and must identify a scientific or authority requirement, not invite another generic controller successor.

## Director correction — Cycle 23

The first completion is rejected as fake-backend readiness, not an actual provider-capable adapter. The implementation has four launch-blocking gaps visible from source inspection:

- `NebiusBackend.__init__` references `metadata_name` and `run_ssh` without importing them, so actual backend construction fails.
- Cleanup deletes and verifies only the instance; it neither deletes the boot disk nor proves disk absence in direct and inventory views.
- `main()` supports only `--no-mutation` and explicitly errors for provider execution, so there is no final controller entrypoint whose mutation switch was exercised by the systemd precreate.
- The required remote V2 36-case capture script and its real archive producer are absent; fake fixture directories do not demonstrate model serving, raw/logprob capture, or artifact construction.

Run one corrective turn in this same project. Supply the real remote capture/archive implementation; make the final CLI parse and validate the frozen model, suite, key, output, deadline, and mutation arguments; instantiate the actual backend in a provider-free test; and make no-mutation traverse the same local contract/backend/command construction as the final path while stopping immediately before the explicit create call. Add failure tests for actual-backend construction, cloud-init/create command serialization, instance plus disk deletion, two-view absence, remote archive validation, and a mutation spy proving zero provider calls. Reuse the existing historical primitives rather than creating another wrapper project.

Provider mutation, H100 launch, model generation, and holdout access remain prohibited with a $0 cap. The correction passes only if the exact final controller and remote script are present, content-bound, and independently executable through the systemd no-mutation boundary; otherwise close the adapter lineage and leave quality calibration paused.

## Director correction — Cycle 24

The second completion is still not provider-executable. `build_host_bootstrap()` installs Docker and pulls the pinned `lmsysorg/sglang:v0.5.15-cu130` image, but does not install SGLang on the host. The new `remote_v2_capture.sh` nevertheless calls `python3 -m sglang.launch_server` directly on the host, so a real session would fail before the first model capture. This also bypasses the preregistered container digest.

Run one final $0 correction in this project. Execute the complete capture process inside the pinned container using the historical stock-control GPU, IPC/shared-memory, `/workspace`, and read-only input mounts; bind the exact image digest in the runtime evidence and artifact identity. Add a behavioral fixture that models a host with Docker but no host SGLang and proves the generated remote command launches the pinned container, exposes `/workspace/model-bf16` and the staged development suite, writes the expected host-visible archive, and preserves the phase deadline and cleanup trap. The frozen 36 cases, endpoints, scorer inputs, three cold starts, and all identities remain unchanged.

No provider mutation or H100 spend is authorized. This is the last adapter-preparation turn: pass the container-execution contract or close the adapter lineage and leave quality calibration paused.
