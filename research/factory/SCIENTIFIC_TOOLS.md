# Scientific tools

This directory is an instrument shelf for researchers, not another research
process. Use the smallest tool that shortens the path from a hypothesis to
decision-bearing evidence. Skip it when a direct command, native framework
tool, or project-specific fixture is clearer.

The tools never schedule agents, allocate GPUs, enforce experiment order, or
decide whether a scientific result passes. The existing lab harness, GPU pool,
spend ledger, role skills, and project logs retain those responsibilities.

## Decision map

| Research need | Instrument | Use it for |
| --- | --- | --- |
| Compare two serving paths under a matched schedule | `tools/lab-endpoint-pair` | Freeze a JSONL workload, retain raw control/candidate responses, and report request-level differences plus comparable timing only for parallel independent arms |
| Find why an expected semantics-preserving change diverged | `tools/lab-microscope` | Selectively record runtime state and identify the first differing field |
| Isolate a production hot operation | `tools/lab-reproducer` | Turn an observed call plus its real inputs into a content-addressed exact-shape fixture |
| Evaluate one kernel or component candidate | `tools/lab-kernel-eval` | Run compile, real-consumer correctness, timing, and optional metadata commands against that fixture |
| Switch a hot operation without forking a serving runtime | Python replacement registry | Select stock or candidate implementation at a narrow call boundary |
| Measure an architecture proxy or short recovery curve | `tools/lab-surgery` | Apply a declared transformation, run bounded recovery/evaluation commands, and retain checkpoint identities |
| Reuse source, checkpoint, image, and compiler state | `tools/lab-workspace` | Describe and update a retained workspace without owning GPU lifecycle |
| Find the right upstream tool for a route | `tools/lab-tools` | Query the pinned catalog by capability, accelerator, or disposition |

These are choices, not stages. A kernel project may use only the evaluator; an
endpoint experiment may need none of the other tools.

## Shared evidence contract

Tools write ordinary files under a caller-selected output directory. Material
artifacts carry a SHA-256 identity and byte size. Commands retain their exact
argument vector, start/completion timestamps, return code, and raw stdout and
stderr. JSONL is used for event or request rows so that interrupted work can
be inspected and, where supported, resumed without replaying completed work.

The useful minimum for a material run remains:

- metadata describing model, workload, software, hardware, and intervention;
- typed metrics or comparison rows;
- raw command logs and endpoint responses;
- selected tensor, profiler, or compiler evidence only when it answers the
  current question.

Do not collect every possible trace. Capture cost should be proportional to
the uncertainty it removes.

## Integration patterns

### Endpoint mechanism

Use a frozen JSONL request set for both endpoints. Keep the control and
candidate servers resident when that is scientifically valid, or restart
between arms when shared state would contaminate the comparison. Interpret the
generated comparison in the project; the runner deliberately does not impose
a quality threshold.

### Unexpected divergence

First reproduce the mismatch on the smallest request and step that still
fails. Enable the microscope only for the suspected request, layer, operation,
or tensor role, then compare captures. An A/A capture is useful when
nondeterminism or the observer itself is plausible. A first difference
localizes the repair; it does not by itself reject the mechanism.

### Kernel or component route

Extract the actual production shape, layout, dtype/scales, inputs, incumbent,
output consumer, and non-overlapping critical-time weight. Evaluate candidates
through that consumer and preserve generated code. Promote a positive
component to an endpoint run when its production-weighted opportunity and
integration cost justify it.

### Model architecture route

State the exact module transformation and whether it is a
semantics-preserving implementation, a semantics-changing cost proxy, or a
recovered candidate. Use a proxy to test the physical cost mechanism before
long recovery work when the campaign permits deferred quality. Export only
through the real serving consumer before making a deployable claim.

### Warm workspace

A workspace description records useful resident state; it does not claim,
release, create, or destroy a GPU. Continue using `grad_research.gpu_pool` for
resource ownership and the campaign watchdog/spend ledger for safety. Update
the description after checkpoint, source revision, runtime, compiled artifact,
or server state changes so the next researcher can patch rather than rebuild.

## Upstream tool policy

`data/tool_catalog.json` is a discovery catalog, not an installation manifest.
Its dispositions mean:

- `base`: cheap, stable diagnostics useful on most retained GPU workspaces;
- `route`: pin into a workspace when the admitted research route needs it;
- `reference`: source material or an on-demand dependency.

Prefer upstream tools for difficult generic mechanisms and keep their raw
output. Add lab code only for production identity, matched comparison,
artifact retention, real-consumer correctness, or cost normalization. Pin the
version used by an experiment in its metadata; do not install every catalog
entry into every environment.

## Command reference

The endpoint workload is JSONL:

```json
{"request_id":"q-001","payload":{"model":"model-id","messages":[{"role":"user","content":"..."}]}}
```

Run or resume both arms, then construct the comparison offline:

```bash
research/factory/tools/lab-endpoint-pair run \
  --workload workload.jsonl --output-dir artifacts/pair \
  --control-url http://127.0.0.1:8000/v1/chat/completions \
  --candidate-url http://127.0.0.1:8001/v1/chat/completions \
  --concurrency 16 --request-interval-seconds 0.01 \
  --parallel-arms --compare-latency
research/factory/tools/lab-endpoint-pair compare \
  --run-dir artifacts/pair
```

`--parallel-arms` is appropriate only for independent endpoints that can run
simultaneously without resource interference. Omit it for restart-separated
arms. The same ordered schedule and request bodies are replayed in both cases;
add `--compare-latency` only when the endpoints are independently provisioned
and equally warm. Without that explicit assertion, raw latencies are retained
but no comparative ratio is emitted. Use AIPerf, GuideLLM, or the runtime's
production load generator when more
complex arrival distributions are the research subject.

The run summary distinguishes `artifact_complete`,
`all_requests_successful`, and `performance_comparable`. A serial-arm run
retains each raw latency but deliberately does not emit comparative latency
deltas. The CLI exits nonzero when either arm has an unsuccessful request.

For authenticated endpoints, pass only an environment-variable name, for
example `--header-env Authorization=ENDPOINT_AUTH_HEADER`; never put a secret
in the URL, workload, or a literal `--header`.

The microscope is imported in the runtime and is zero-use when disabled:

```python
from grad_research.science_tools.microscope import CaptureSelector, Recorder

trace = Recorder(
    "candidate.jsonl",
    selector=CaptureSelector(request="q-001", layer=17, phase="decode"),
    byte_mode="sample",
    max_bytes=4096,
)
trace.tensor(hidden, name="post_attention", tensor_role="hidden", decode_step=3)
trace.kv(
    source=source_slot,
    destination=destination_slot,
    valid_length=valid_length,
    ownership=request_id,
    decode_step=3,
)
```

Compare captures with an explicit tolerance and ignore process-local pointer
fields by default:

```bash
research/factory/tools/lab-microscope diff control.jsonl candidate.jsonl \
  --atol 1e-6 --rtol 1e-5
```

Use `--compare-pointers` only when storage aliasing or address reuse is the
question. `byte_mode="none"` captures shape/layout/dtype without copying tensor
values; `sample` performs a bounded selected-tensor copy; `complete` is an
explicit potentially expensive full digest.

For an exact-shape route, extract one normalized trace operation and evaluate
explicit reference/baseline/candidate commands:

```bash
research/factory/tools/lab-reproducer \
  --trace normalized-ops.jsonl --operation-id decode-qkv \
  --artifact-root trace-artifacts --output repro/decode-qkv
research/factory/tools/lab-kernel-eval \
  --repro repro/decode-qkv --spec evaluation.json \
  --output artifacts/decode-qkv-eval
```

A normalized operation has this small shape; artifact paths are relative to
`--artifact-root` and valid roles are `inputs`, `reference`, `consumer`, and
`candidate`:

```json
{
  "operation_id": "decode-qkv",
  "semantic": {"phase": "decode", "operation": "qkv"},
  "shape": [16, 4096, 6144],
  "layout": {"input": "row-major"},
  "dtype": {"input": "float16", "weight": "fp8"},
  "production_non_overlap_wall_share": 0.17,
  "artifacts": {
    "inputs": [{"path": "decode-qkv-inputs.pt"}],
    "reference": "reference.py",
    "consumer": "benchmark.py",
    "candidate": "candidate.py"
  }
}
```

The evaluator refuses fixtures without a shape and captured input. Its spec
contains explicit commands. By default each command must emit one complete
JSON value to stdout:

```json
{
  "commands": {
    "reference": {
      "argv": ["python3", "reference.py"],
      "output": {"kind": "json", "source": "stdout", "value_path": "values"}
    },
    "baseline": {
      "argv": ["python3", "benchmark.py", "--implementation", "stock"],
      "output": {"kind": "json", "source": "stdout", "value_path": "values"}
    },
    "candidate": {
      "argv": ["python3", "benchmark.py", "--implementation", "candidate"],
      "output": {"kind": "json", "source": "stdout", "value_path": "values"}
    }
  },
  "correctness": {"atol": 1e-5, "rtol": 1e-5},
  "timing": {
    "source": "output_json",
    "value_path": "latency_us",
    "unit": "microseconds",
    "warmup": 3,
    "repetitions": 20
  }
}
```

For credible GPU timing, have the benchmark command synchronize and report its
own measured value in JSON, select only the correctness output with
`command.output.value_path`, and configure:

```json
{"timing":{"source":"output_json","value_path":"latency_us","unit":"microseconds","warmup":3,"repetitions":20}}
```

Subprocess wall time remains available as `timing.source="command_wall"` for
coarse components, not short kernels.

Every file output and candidate-proof file must be newly created or changed by
that exact invocation. Every candidate evaluation declares
`candidate_path_proof`, for example:

```json
{"candidate_path_proof":{"path":"candidate-proof.json","contains":{"selected":"candidate"}}}
```

The benchmark receives the unique path in
`LAB_CANDIDATE_PROOF_PATH`. The replacement seam can write the proof directly:

```python
import os
from grad_research.science_tools.replacement import ReplacementRegistry

registry = ReplacementRegistry(
    proof_path=os.environ.get("LAB_CANDIDATE_PROOF_PATH")
)
registry.register("attention", stock_attention, candidate_attention,
                  phase="decode", shape=(16, 32, 128))
output = registry.call("attention", *inputs, phase="decode",
                       shape=(16, 32, 128), mode="candidate")
```

Candidate fallback after an exception is opt-in. Use it only when the
candidate cannot mutate inputs before failing; otherwise rerun stock from
clean inputs.

Initialize a retained source/checkpoint/compiler workspace and query tools
without changing GPU ownership:

```bash
research/factory/tools/lab-workspace init --workspace /path/to/warm-workspace
research/factory/tools/lab-workspace status \
  --workspace /path/to/warm-workspace --probe ncu --probe nvdisasm
research/factory/tools/lab-tools list --category kernel
```

Workspace `--metadata` is a JSON file whose accepted top-level fields are
`hardware_identity`, `runtime_identity`, `checkpoint_identity`,
`source_identity`, `image_identity`, `compatible_tags`, and `claim`.
`--probe` accepts one executable name per occurrence, not shell arguments.

Model surgery is a small resumable command chain, not a training framework.
Define only the phases the intervention needs:

```json
{
  "phases": {
    "replace": {
      "argv": ["python3", "replace_module.py"],
      "cwd": ".",
      "env": {},
      "timeout_seconds": 300,
      "expected_outputs": ["changed-checkpoint"]
    },
    "recover": {
      "argv": ["python3", "recover.py"],
      "cwd": ".",
      "env": {},
      "timeout_seconds": 7200,
      "expected_outputs": ["recovered-checkpoint"],
      "metrics_jsonl": "recovery-curve.jsonl"
    },
    "evaluate": {
      "argv": ["python3", "evaluate.py"],
      "cwd": ".",
      "env": {},
      "timeout_seconds": 1800,
      "expected_outputs": ["evaluation.json"]
    }
  }
}
```

Valid phase names, in dependency order, are `capture`, `replace`, `recover`,
`export`, and `evaluate`. A changed upstream output invalidates downstream
resume automatically. `--from-phase` therefore requires valid compatible
terminals for any configured earlier phases.

Catalog probes are trusted, pinned repository data used for discovery. They
are not a sandbox for arbitrary untrusted catalogs or commands.

Every wrapper is self-documenting:

```bash
research/factory/tools/lab-endpoint-pair --help
research/factory/tools/lab-microscope --help
research/factory/tools/lab-reproducer --help
research/factory/tools/lab-kernel-eval --help
research/factory/tools/lab-surgery --help
research/factory/tools/lab-workspace --help
research/factory/tools/lab-tools --help
```

Run wrappers from any checkout; each wrapper adds the factory package to
`PYTHONPATH`. Python modules can also be imported directly from
`grad_research.science_tools`.
