# Research log

## 2026-07-15 — V2 adapter and bounded provider attempt

Question: can a current-identity cache-off c8/c16/c32 L40S frontier be executed after V32's stale tokenizer gate and archive-envelope failure?

Action: implemented `frontier_v2.py`, a project-local staging adapter that replaces only the two stale V21 tokenizer hashes, preserves the verified current third hash, and extends the fixed adjacent ladder to c32 with two full batches. Four focused tests passed. A cached Transformers tokenizer rendered the deterministic one-token atom prompt to exactly 8,192 input tokens (`9025685d...8924b`) with a 1,024-token maximum. The durable V2 controller attempted one 2,700-second/$0.64359165 maximum Nebius session after empty direct inventories.

Evidence: [V2 precreate and provider outcome](artifacts/V2_PRECREATE_AND_PROVIDER_OUTCOME.json). The controller's create returned exit 3 immediately; it retained no provider stdout/stderr. Direct inventories after cleanup were `{}` for instances and disks. The earlier V32 archive also contains no `allocation-result.json`, consistent with its remote script stopping before the runner under frozen tokenizer hashes.

Interpretation: no quality, throughput, or economic result exists; neither a provider rejection nor a model/runtime failure may be inferred. The local adapter and workload gate are now passed. The paid create route is an observability failure, not a scientific falsifier.

Next move: before any retry, amend the project-local controller to persist credential-redacted create stdout/stderr and run its no-create fixture. Then retry only if the diagnostic identifies a safe, in-scope provider remediation and the remaining all-in project cap still covers it.

## 2026-07-15 — Final diagnostic-bearing create attempt

Question: is the final current-AWQ L40S creation request admissible after correcting both controller observation layers?

Action: added a redacted `provider-create-diagnostic.json` envelope to the project-local controller and a no-create fixture; all five focused tests passed. With empty direct inventories, launched the one authorized final 2,700-second diagnostic-bearing attempt under the durable systemd controller.

Evidence: [typed provider-create diagnostic](artifacts/glm47_current_awq_l40s_frontier_v2_final/provider-create-diagnostic.json) records return code 3 and Nebius `InvalidArgument`: cloud-init `UserData` YAML is invalid at line 10. The final [events](artifacts/glm47_current_awq_l40s_frontier_v2_final/events.jsonl) and [summary](artifacts/glm47_current_awq_l40s_frontier_v2_final/summary.json) record zero created resources and verified cleanup.

Interpretation: this is a typed request-envelope failure before allocation, model transfer, loading, quality capture, or any c8/c16/c32 arm. It does not falsify AWQ, vLLM, L40S capacity, or the batching hypothesis. Per the project terminal rule, do not repair or retry this Nebius route in this project.

Next move: reallocate the measurement to a project with a separately validated cloud-init serialization path, or repair that provider adapter outside this closed experiment before proposing a fresh, separately budgeted current-AWQ frontier.
