# Shared research tools

Small reusable scripts that help several projects may live here. Agents may also use model-specific tools in the campaign directory. Tools support researcher judgment; they do not define the research process.

The canonical GPU price data is [`../data/gpu_prices.json`](../data/gpu_prices.json). Validate and query it through `PYTHONPATH=research/factory/src python3 -m grad_research gpu-prices`; do not create project-local price tables.

The canonical hardware-capability data is [`../data/accelerator_inventory.json`](../data/accelerator_inventory.json). Query it through `PYTHONPATH=research/factory/src python3 -m grad_research accelerators` before building a model-specific chip dossier; add only measurements and facts that are absent or specific to the project.

`./grad-profile` is the shared GPU evidence tool. It captures profiler-off baselines, short Nsight or ROCm diagnostics, hashes compiler artifacts, normalizes traces/counters, compares $/token, and appends exact-shape measurements. Read [`../PROFILING.md`](../PROFILING.md) for commands. It never provisions provider resources.

`./lab-endpoint-pair`, `./lab-microscope`, `./lab-reproducer`, `./lab-kernel-eval`, `./lab-surgery`, `./lab-workspace`, and `./lab-tools` are optional scientific instruments. They standardize repeated evidence plumbing without prescribing experiment order or scientific conclusions. Read [`../SCIENTIFIC_TOOLS.md`](../SCIENTIFIC_TOOLS.md) and invoke only the tool needed by the current question.

`./detached-owner` launches a bounded guest process in a new session, redirects
all output to a durable log, and records both its PID and Linux start time so
status checks cannot mistake PID reuse for a live owner. Copy it to an already
claimed guest and use `start --state OWNER.json --log OWNER.log -- COMMAND...`
when an SSH child or session-scoped user service would otherwise die as the
launcher exits. Record its state path with `unit_manager: remote-shell`; the
experiment command still owns its timeout, claim heartbeats, terminal, and
artifact retrieval.

The same tool can detach a controller-host outer owner with
`start --unit-manager pid --state OWNER.json --log OWNER.log -- COMMAND...`.
Use that form when the outer owner—not only its guest worker—maintains the GPU
claim heartbeat, repair handshake, terminal retrieval, or final release. Copy
the emitted PID and start time into `STATUS.json.active_session`, set `unit`
to the absolute owner-state path, and set `unit_manager` to `pid`. A detached
guest process does not make a foreground claim controller durable.
For a replacement-owner handoff, also pass `--ready-file FRESH_PATH` and a
bounded `--stabilize-seconds`: launch succeeds only after the live owner creates
that runtime artifact. A still-live process that misses the readiness deadline
remains recorded for explicit reconciliation, but the command returns nonzero
and must not be advertised as a ready executor.

`grad_research.gpu_claim_session.GpuClaimSession` is the optional lifecycle
primitive for that controller-host owner. It atomically claims one exact bench,
heartbeats it, binds release to the returned `claimed_at` generation, and
releases to maintenance if the owner exits without an explicit release.
Catch recoverable integration errors and complete the repair handshake inside
the context so the same claim remains live; leaving the context is the final
lifecycle boundary. The helper does not detach the owner, choose experiments,
or interpret failures.

`./repair-handshake` provides the atomic coordination files used by the
harness when a durable outer owner encounters an ordinary integration or
consumer defect. While the owner keeps heartbeating the existing claim, run
`ready --root ARTIFACT_ROOT --deadline RFC3339 --failure-kind integration
--diagnostic PATH --retry-scope TEXT`. The harness wakes the same researcher,
who patches the resident environment and runs `request --root ARTIFACT_ROOT
--patch-artifact PATH`; the request is hash-bound to the exact ready record.
For an exception path that must not return between publishing the marker and
waiting for repair, use the same arguments with `hold` instead of `ready`.
`hold` atomically creates or verifies the ready record, then blocks until a
hash-bound request, repair terminal, project terminal, or the persisted
deadline. The owner's existing heartbeat thread must remain active.
The request inherits the ready record's retry scope. An optional
`--retry-scope` may restate that exact value, but cannot broaden a
later-consumer repair into upstream staging or rebuilding.
Requests expose the path as canonical `patch_artifact` and the identical
backward-compatible `packet_path` alias so an older durable owner does not
release a warm claim at this repair boundary.
If the researcher must execute the requested scope outside the waiting owner,
record the outcome atomically with `terminal --root ARTIFACT_ROOT --exit-code
N --classification TEXT --cuda-started true|false|unknown --science-started
true|false|unknown --evidence PATH [--evidence PATH ...] [--result PATH]`.
The record is bound to both the ready and request digests. `status` and `wait`
then return `state: repair_terminal` plus the record so the durable owner can
adopt it without rerunning the repaired scope; this command does not create or
replace the project's own `TERMINAL.json`.
The owner can use `status --root ARTIFACT_ROOT` to distinguish waiting,
requested, repair-terminal, expired, and project-terminal states. After `ready`, use
`wait --root ARTIFACT_ROOT [--deadline RFC3339]` inside the durable outer owner
to block until a hash-bound request, terminal, or absolute deadline. When
supplied, the wait deadline must match the persisted ready deadline. Keep the
owner's existing heartbeat thread active while it waits; do not return merely because
`REPAIR_READY.json` exists. This tool does not own GPU heartbeats, choose a
repair, validate scientific claims, or authorize replay of a completed stage.
When one project can encounter multiple repair episodes, pass the same
`--repair-id CLAIM_OR_ATTEMPT_ID` to every command in an episode. The helper
then preserves each pair under
`ARTIFACT_ROOT/.repair-handshakes/CLAIM_OR_ATTEMPT_ID/`, so a durable request
from an earlier episode cannot block a later in-place repair. Set the harness
session's `artifact_root` to the emitted `handshake_root` when it must discover
and wake that episode.

`./artifact-snapshot --archive compact.tar.gz --root RETRIEVALS` extracts a
verified local archive into `RETRIEVALS/<sha256>`. Repeating the same archive
is idempotent, while a changed repair snapshot gets a distinct directory.
Use the returned destination instead of reusing one mutable `retrieved/`
directory across monitoring, repair, and terminal retrieval passes.

`./manifest-pack --root PROJECT --manifest PROJECT/PACKET_MANIFEST.json
--archive PACKET.tar` builds a packet directly from every manifest member plus
the manifest itself. It accepts both the list-based `files` schema and the
path-keyed schema, verifies sizes and SHA-256 values before writing, rejects
unsafe paths and symlinks, and atomically replaces the output. Use it instead
of maintaining a second hand-written tar member list.
