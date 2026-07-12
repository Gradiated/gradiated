from __future__ import annotations

import hashlib
import json
import os
import signal
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .commands import build_benchmark_command, build_server_command
from .host import (
    HostSnapshot,
    capture_host_state,
    evaluate_isolation,
    process_ancestry,
    process_descendants,
)
from .prompts import (
    PromptManifest,
    generate_vllm_prompt_manifest,
    write_prompt_fixture,
)
from .provenance import (
    SourceProvenance,
    capture_source,
    sha256_file,
    validate_source,
)
from .results import (
    RunContext,
    RunResult,
    normalize_vllm_result,
    run_result_from_mapping,
    summarize_campaign,
)
from .runtime import RuntimeEstimate, estimate_runtime
from .schedule import ScheduledRun, build_schedule
from .schema import CampaignSpec


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(value)
    file_bytes = payload + b"\n"
    path.write_bytes(file_bytes)
    return hashlib.sha256(file_bytes).hexdigest()


def load_spec(path: Path) -> tuple[CampaignSpec, Mapping[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CampaignSpec.from_mapping(raw), raw


def _prompt_manifest(spec: CampaignSpec) -> PromptManifest:
    workload = spec.workload
    return generate_vllm_prompt_manifest(
        model_path=spec.engine.model_path,
        seed=workload.dataset_seed,
        generator_revision=spec.engine.expected_revision,
        num_prompts=workload.num_prompts,
        input_tokens=workload.input_tokens,
        output_tokens=workload.output_tokens,
    )


def _runtime_estimate(
    spec: CampaignSpec,
    raw_spec: Mapping[str, Any],
    startup_seconds: float | None = None,
    client_setup_seconds: float | None = None,
) -> RuntimeEstimate:
    raw = raw_spec["runtime_estimate"]
    prior = {
        int(concurrency): float(duration)
        for concurrency, duration in raw[
            "prior_duration_seconds_by_concurrency"
        ].items()
    }
    return estimate_runtime(
        durations_by_concurrency=prior,
        repeats=spec.repeat_pairs,
        startup_seconds=(
            float(raw["startup_seconds"])
            if startup_seconds is None
            else startup_seconds
        ),
        cooldown_seconds=spec.isolation.cooldown_seconds,
        per_pair_overhead_seconds=float(raw["per_pair_overhead_seconds"]),
        per_run_client_setup_seconds=(
            float(raw["per_run_client_setup_seconds"])
            if client_setup_seconds is None
            else client_setup_seconds
        ),
    )


def _template_commands(
    spec: CampaignSpec, output_root: Path
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    server = build_server_command(spec)
    benchmark = build_benchmark_command(
        spec,
        concurrency=1,
        prompts_path=output_root / "prompts.jsonl",
        output_path=output_root / "raw" / "c1-r1-cold_engine.json",
        request_id_prefix="qwen-fixed-",
    )
    return server, benchmark


def _capture_preflight_host(output_root: Path) -> tuple[HostSnapshot, dict[str, Any]]:
    snapshot = capture_host_state()
    snapshot_path = output_root / "host" / "preflight.json"
    snapshot_id = _write_json(snapshot_path, snapshot.to_mapping())
    return snapshot, {"path": str(snapshot_path), "sha256": snapshot_id}


def prepare_campaign(
    spec: CampaignSpec, raw_spec: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / ".metadata_never_index").touch(exist_ok=True)
    prompts = _prompt_manifest(spec)
    prompts_path = output_root / "prompts.jsonl"
    prompt_manifest_path = output_root / "prompt-manifest.json"
    write_prompt_fixture(prompts, prompts_path)
    prompt_manifest_id = _write_json(prompt_manifest_path, prompts.to_mapping())
    source_command_root = Path(
        str(raw_spec.get("source_command_root", output_root))
    ).resolve()
    server_command, benchmark_template = _template_commands(spec, source_command_root)
    source = capture_source(spec.engine, server_command, benchmark_template)
    source_reasons = list(validate_source(source, spec.engine))
    checkpoint_path = spec.engine.model_path / "model.safetensors"
    checkpoint_sha256 = sha256_file(checkpoint_path)
    if checkpoint_sha256 != spec.engine.checkpoint_sha256:
        source_reasons.append("checkpoint content drift")
    prompt_reasons = []
    if prompts.content_id != spec.workload.prompt_content_id:
        prompt_reasons.append("prompt content drift")
    host, host_reference = _capture_preflight_host(output_root)
    isolation = evaluate_isolation(
        host, spec.isolation, process_ancestry(host.processes)
    )
    schedule = build_schedule(
        spec.concurrency_levels, spec.repeat_pairs, spec.schedule_seed
    )
    runtime = _runtime_estimate(spec, raw_spec)
    accepted = not source_reasons and not prompt_reasons and isolation.accepted
    manifest = {
        "schema_version": 1,
        "campaign_id": spec.campaign_id,
        "protocol": {
            "cold_engine": "first measured burst after a fresh server process reaches health; OS file cache is not purged",
            "warm_engine": "second identical burst on the same server immediately after its paired cold-engine burst",
            "randomization": "the twenty concurrency-repeat pairs are shuffled by the pinned schedule seed; cold then warm remain adjacent",
            "schedule_seed": spec.schedule_seed,
            "repeat_pairs": spec.repeat_pairs,
            "measured_run_count": spec.expected_run_count,
        },
        "schedule": [asdict(run) for run in schedule],
        "workload": {
            "geometry": list(spec.workload.geometry),
            "request_rate": spec.workload.request_rate,
            "ignore_eos": spec.workload.ignore_eos,
            "prompt_content_id": prompts.content_id,
            "prompt_fixture": str(prompts_path),
            "prompt_fixture_sha256": sha256_file(prompts_path),
            "prompt_manifest": str(prompt_manifest_path),
            "prompt_manifest_sha256": prompt_manifest_id,
        },
        "source": source.to_mapping(),
        "source_command_root": str(source_command_root),
        "checkpoint_sha256": checkpoint_sha256,
        "environment": _environment(spec),
        "host_preflight": host_reference,
        "isolation": isolation.to_mapping(),
        "runtime_estimate": runtime.to_mapping(),
        "preflight": {
            "accepted": accepted,
            "source_rejection_reasons": source_reasons,
            "prompt_rejection_reasons": prompt_reasons,
            "isolation_rejection_reasons": list(isolation.rejection_reasons),
        },
        "claims": dict(spec.claim_gates),
    }
    identity = dict(manifest)
    manifest["content_id"] = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    _write_json(output_root / "campaign-manifest.json", manifest)
    return manifest


@dataclass
class ServerProcess:
    process: subprocess.Popen
    stdout_handle: Any
    stderr_handle: Any
    started_at: float


class IsolationViolation(RuntimeError):
    pass


def _environment(spec: CampaignSpec) -> dict[str, str]:
    inherited_names = (
        "DYLD_LIBRARY_PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "TMPDIR",
        "USER",
    )
    environment = {
        name: os.environ[name] for name in inherited_names if name in os.environ
    }
    environment.update(dict(spec.engine.environment))
    return environment


def _launch_server(
    spec: CampaignSpec, stdout_path: Path, stderr_path: Path
) -> ServerProcess:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("wb")
    stderr_handle = stderr_path.open("wb")
    started_at = time.monotonic()
    process = subprocess.Popen(
        build_server_command(spec),
        cwd=spec.engine.checkout,
        env=_environment(spec),
        stdout=stdout_handle,
        stderr=stderr_handle,
        start_new_session=True,
    )
    return ServerProcess(process, stdout_handle, stderr_handle, started_at)


def _wait_until_ready(server: ServerProcess, spec: CampaignSpec) -> float:
    deadline = time.monotonic() + spec.isolation.startup_timeout_seconds
    url = f"http://{spec.engine.host}:{spec.engine.port}/health"
    while time.monotonic() < deadline:
        if server.process.poll() is not None:
            raise RuntimeError(f"vLLM server exited with {server.process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return time.monotonic() - server.started_at
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.5)
    raise TimeoutError("vLLM server readiness timeout")


def _stop_server(server: ServerProcess) -> None:
    try:
        if server.process.poll() is None:
            os.killpg(server.process.pid, signal.SIGTERM)
            try:
                server.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(server.process.pid, signal.SIGKILL)
                server.process.wait(timeout=10)
    finally:
        server.stdout_handle.close()
        server.stderr_handle.close()


def run_startup_probe(
    spec: CampaignSpec, raw_spec: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    output_root = output_root.resolve()
    manifest = prepare_campaign(spec, raw_spec, output_root)
    if not manifest["preflight"]["accepted"]:
        report = {
            "schema_version": 1,
            "started": False,
            "accepted": False,
            "preflight": manifest["preflight"],
            "claims": dict(spec.claim_gates),
        }
        _write_json(output_root / "startup-probe.json", report)
        return report
    server = _launch_server(
        spec,
        output_root / "logs" / "startup-probe.stdout",
        output_root / "logs" / "startup-probe.stderr",
    )
    startup_seconds = 0.0
    startup_error = None
    ready_isolation = None
    try:
        try:
            startup_seconds = _wait_until_ready(server, spec)
        except Exception as error:
            startup_error = f"{type(error).__name__}: {error}"
        ready_host = capture_host_state()
        ready_isolation = _runtime_isolation(ready_host, spec, server.process.pid)
        _write_json(
            output_root / "host" / "startup-probe-ready.json", ready_host.to_mapping()
        )
    finally:
        _stop_server(server)
    post_host = capture_host_state()
    post_isolation = evaluate_isolation(
        post_host, spec.isolation, process_ancestry(post_host.processes)
    )
    _write_json(
        output_root / "host" / "startup-probe-post.json", post_host.to_mapping()
    )
    accepted = (
        startup_error is None
        and ready_isolation is not None
        and ready_isolation.accepted
        and post_isolation.accepted
    )
    report = {
        "schema_version": 1,
        "started": True,
        "accepted": accepted,
        "startup_seconds": startup_seconds,
        "startup_error": startup_error,
        "isolation_ready": (
            ready_isolation.to_mapping() if ready_isolation is not None else None
        ),
        "isolation_post": post_isolation.to_mapping(),
        "runtime_estimate": _runtime_estimate(
            spec, raw_spec, startup_seconds
        ).to_mapping()
        if accepted
        else None,
        "server_command": list(build_server_command(spec)),
        "claims": dict(spec.claim_gates),
    }
    _write_json(output_root / "startup-probe.json", report)
    return report


def _client_setup_command(spec: CampaignSpec, prompts_path: Path) -> tuple[str, ...]:
    code = (
        "import json,sys;"
        "from vllm.benchmarks.datasets import CustomDataset;"
        "from vllm.tokenizers import get_tokenizer;"
        "tokenizer=get_tokenizer(sys.argv[1],trust_remote_code=False);"
        "requests=CustomDataset(dataset_path=sys.argv[2],disable_shuffle=True,random_seed=0).sample("
        "tokenizer=tokenizer,num_requests=8,output_len=32,skip_chat_template=True,request_id_prefix='qwen-fixed-');"
        "assert len(requests)==8 and all(r.prompt_len==128 and r.expected_output_len==32 for r in requests);"
        "print(json.dumps({'requests':len(requests),'geometry':[8,128,32]},sort_keys=True))"
    )
    return (
        str(spec.engine.python),
        "-c",
        code,
        str(spec.engine.model_path),
        str(prompts_path),
    )


def run_client_setup_probe(
    spec: CampaignSpec, raw_spec: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    output_root = output_root.resolve()
    manifest = prepare_campaign(spec, raw_spec, output_root)
    if not manifest["preflight"]["accepted"]:
        report = {
            "schema_version": 1,
            "accepted": False,
            "started": False,
            "preflight": manifest["preflight"],
            "claims": dict(spec.claim_gates),
        }
        _write_json(output_root / "client-setup-probe.json", report)
        return report
    command = _client_setup_command(spec, output_root / "prompts.jsonl")
    before = capture_host_state()
    before_isolation = evaluate_isolation(
        before, spec.isolation, process_ancestry(before.processes)
    )
    started_at = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=spec.engine.checkout,
        env=_environment(spec),
        capture_output=True,
        text=True,
        check=False,
        timeout=spec.isolation.startup_timeout_seconds,
    )
    wall_seconds = time.monotonic() - started_at
    after = capture_host_state()
    after_isolation = evaluate_isolation(
        after, spec.isolation, process_ancestry(after.processes)
    )
    _write_json(output_root / "host" / "client-setup-before.json", before.to_mapping())
    _write_json(output_root / "host" / "client-setup-after.json", after.to_mapping())
    logs = output_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "client-setup.stdout").write_text(completed.stdout, encoding="utf-8")
    (logs / "client-setup.stderr").write_text(completed.stderr, encoding="utf-8")
    accepted = (
        completed.returncode == 0
        and before_isolation.accepted
        and after_isolation.accepted
    )
    startup_probe_path = output_root / "startup-probe.json"
    startup_seconds = None
    if startup_probe_path.exists():
        startup_probe = json.loads(startup_probe_path.read_text(encoding="utf-8"))
        if startup_probe.get("accepted"):
            startup_seconds = float(startup_probe["startup_seconds"])
    report = {
        "schema_version": 1,
        "accepted": accepted,
        "started": True,
        "wall_seconds": wall_seconds,
        "returncode": completed.returncode,
        "command": list(command),
        "isolation_before": before_isolation.to_mapping(),
        "isolation_after": after_isolation.to_mapping(),
        "runtime_estimate": (
            _runtime_estimate(
                spec,
                raw_spec,
                startup_seconds=startup_seconds,
                client_setup_seconds=wall_seconds,
            ).to_mapping()
            if accepted
            else None
        ),
        "claims": dict(spec.claim_gates),
    }
    _write_json(output_root / "client-setup-probe.json", report)
    return report


def _capture_named_host(
    output_root: Path, name: str
) -> tuple[HostSnapshot, dict[str, str]]:
    snapshot = capture_host_state()
    path = output_root / "host" / f"{name}.json"
    reference = {"path": str(path), "sha256": _write_json(path, snapshot.to_mapping())}
    return snapshot, reference


def _runtime_isolation(snapshot: HostSnapshot, spec: CampaignSpec, server_pid: int):
    excluded = process_ancestry(snapshot.processes)
    excluded.update(process_descendants(snapshot.processes, {server_pid}))
    return evaluate_isolation(snapshot, spec.isolation, excluded)


def _run_benchmark(
    spec: CampaignSpec,
    scheduled: ScheduledRun,
    prompts_path: Path,
    output_root: Path,
    source: SourceProvenance,
    prompt_records: Sequence[Mapping[str, Any]],
    isolated: bool,
    server_pid: int,
) -> RunResult:
    run_name = f"{scheduled.pair_id}-{scheduled.state}"
    raw_path = output_root / "raw" / f"{run_name}.json"
    command = build_benchmark_command(
        spec,
        concurrency=scheduled.concurrency,
        prompts_path=prompts_path,
        output_path=raw_path,
        request_id_prefix="qwen-fixed-",
    )
    before_snapshot, before = _capture_named_host(output_root, f"{run_name}-before")
    before_isolation = _runtime_isolation(before_snapshot, spec, server_pid)
    if not before_isolation.accepted:
        _write_json(
            output_root / "aborted.json",
            {
                "run": run_name,
                "phase": "before_benchmark",
                "isolation": before_isolation.to_mapping(),
                "claims": dict(spec.claim_gates),
            },
        )
        raise IsolationViolation(f"runtime isolation failed before {run_name}")
    completed = subprocess.run(
        command,
        cwd=spec.engine.checkout,
        env=_environment(spec),
        capture_output=True,
        text=True,
        check=False,
        timeout=spec.isolation.startup_timeout_seconds,
    )
    logs = output_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{run_name}.stdout").write_text(completed.stdout, encoding="utf-8")
    (logs / f"{run_name}.stderr").write_text(completed.stderr, encoding="utf-8")
    after_snapshot, after = _capture_named_host(output_root, f"{run_name}-after")
    after_isolation = _runtime_isolation(after_snapshot, spec, server_pid)
    if completed.returncode != 0 or not raw_path.exists():
        raise RuntimeError(
            f"benchmark {run_name} failed with exit code {completed.returncode}"
        )
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    context = RunContext(
        pair_id=scheduled.pair_id,
        concurrency=scheduled.concurrency,
        repeat_index=scheduled.repeat_index,
        state=scheduled.state,
        prompt_content_id=spec.workload.prompt_content_id,
        source_content_id=source.content_id,
        isolated=isolated and before_isolation.accepted and after_isolation.accepted,
    )
    result = normalize_vllm_result(raw, prompt_records, context)
    wrapper = {
        "schema_version": 1,
        "schedule": asdict(scheduled),
        "command": list(command),
        "source_content_id": source.content_id,
        "raw_path": str(raw_path),
        "raw_sha256": sha256_file(raw_path),
        "host_before": before,
        "host_after": after,
        "isolation_before": before_isolation.to_mapping(),
        "isolation_after": after_isolation.to_mapping(),
        "result": result.to_mapping(),
        "claims": dict(spec.claim_gates),
    }
    _write_json(output_root / "runs" / f"{run_name}.json", wrapper)
    return result


def _load_accepted_pair(
    output_root: Path, cold: ScheduledRun, warm: ScheduledRun
) -> tuple[RunResult, RunResult] | None:
    index_path = output_root / "accepted-pairs" / f"{cold.pair_id}.json"
    if not index_path.exists():
        return None
    index = json.loads(index_path.read_text(encoding="utf-8"))
    attempt_root = Path(index["attempt_root"])
    loaded: list[RunResult] = []
    for scheduled in (cold, warm):
        run_name = f"{scheduled.pair_id}-{scheduled.state}"
        wrapper = json.loads(
            (attempt_root / "runs" / f"{run_name}.json").read_text(encoding="utf-8")
        )
        result = run_result_from_mapping(wrapper["result"])
        if not result.accepted or result.context.state != scheduled.state:
            raise RuntimeError(f"invalid accepted-pair index for {cold.pair_id}")
        loaded.append(result)
    return loaded[0], loaded[1]


def _load_rejections(output_root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((output_root / "attempts").glob("*/*/rejection.json"))
    ]


def _summarize_prior_evidence(raw_spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for raw_root in raw_spec.get("prior_evidence_roots", []):
        root = Path(str(raw_root))
        accepted = sorted((root / "accepted-pairs").glob("*.json"))
        rejected = sorted((root / "attempts").glob("*/*/rejection.json"))
        summaries.append(
            {
                "root": str(root),
                "accepted_pair_count": len(accepted),
                "accepted_pair_indexes": [
                    {"path": str(path), "sha256": sha256_file(path)}
                    for path in accepted
                ],
                "rejected_attempt_count": len(rejected),
                "rejection_evidence": [
                    {"path": str(path), "sha256": sha256_file(path)}
                    for path in rejected
                ],
            }
        )
    return summaries


def _accepted_pair_evidence(output_root: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index_path in sorted((output_root / "accepted-pairs").glob("*.json")):
        index = json.loads(index_path.read_text(encoding="utf-8"))
        pair = {
            "pair_id": index.get("pair_id", index_path.stem),
            "index_path": str(index_path),
            "index_sha256": sha256_file(index_path),
            "attempt_root": index.get("attempt_root"),
            "runs": [],
        }
        attempt_root_raw = index.get("attempt_root")
        if attempt_root_raw is not None:
            attempt_root = Path(str(attempt_root_raw))
            for state in ("cold_engine", "warm_engine"):
                wrapper_path = attempt_root / "runs" / f"{pair['pair_id']}-{state}.json"
                if not wrapper_path.exists():
                    continue
                wrapper = json.loads(wrapper_path.read_text(encoding="utf-8"))
                raw_path = Path(str(wrapper["raw_path"]))
                pair["runs"].append(
                    {
                        "state": state,
                        "wrapper_path": str(wrapper_path),
                        "wrapper_sha256": sha256_file(wrapper_path),
                        "raw_path": str(raw_path),
                        "raw_sha256": sha256_file(raw_path),
                    }
                )
        evidence.append(pair)
    return evidence


def _write_blocked_campaign_result(
    spec: CampaignSpec,
    raw_spec: Mapping[str, Any],
    output_root: Path,
    wait_report: Mapping[str, Any],
) -> dict[str, Any]:
    timeout_path = output_root / "wait-preflight" / "timeout.json"
    wait_samples = sorted((output_root / "wait-preflight").glob("sample-*.json"))
    wait_sample_identity = [
        {"name": path.name, "sha256": sha256_file(path)} for path in wait_samples
    ]
    accepted_pairs = _accepted_pair_evidence(output_root)
    report = {
        "schema_version": 1,
        "campaign_id": spec.campaign_id,
        "terminal_status": "host_contamination_blocked",
        "campaign_accepted": False,
        "blocked_reason": "the host did not produce the required consecutive clean samples before the frozen preflight timeout",
        "isolation_contract": {
            "quiet_process_cpu_percent": spec.isolation.quiet_process_cpu_percent,
            "required_consecutive_clean_samples": spec.isolation.quiet_consecutive_samples,
            "sample_interval_seconds": spec.isolation.quiet_sample_interval_seconds,
            "timeout_seconds": spec.isolation.preflight_wait_timeout_seconds,
        },
        "wait_preflight": dict(wait_report),
        "progress": {
            "expected_pair_count": spec.expected_run_count // 2,
            "expected_run_count": spec.expected_run_count,
            "accepted_pair_count": len(accepted_pairs),
            "accepted_run_count": sum(len(pair["runs"]) for pair in accepted_pairs),
            "new_measured_run_count": 0,
        },
        "evidence": {
            "raw_output_root": str(output_root),
            "timeout_path": str(timeout_path),
            "timeout_sha256": sha256_file(timeout_path),
            "wait_sample_count": len(wait_samples),
            "wait_samples_content_id": hashlib.sha256(
                _canonical_bytes(wait_sample_identity)
            ).hexdigest(),
            "accepted_pairs": accepted_pairs,
            "prior_evidence": _summarize_prior_evidence(raw_spec),
            "archive_root": raw_spec.get("archive_root"),
        },
        "interpretation": "no repeatability, provider, GPU, simulator-calibration, or cost conclusion can be drawn from this blocked campaign",
        "claims": dict(spec.claim_gates),
    }
    identity = dict(report)
    report["content_id"] = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    _write_json(output_root / "campaign-blocked.json", report)
    durable_path = raw_spec.get("durable_report_path")
    if durable_path is not None:
        _write_json(Path(str(durable_path)), report)
    archive_root_raw = raw_spec.get("archive_root")
    if archive_root_raw is not None:
        archive_root = Path(str(archive_root_raw)).resolve()
        if archive_root != output_root:
            shutil.copytree(output_root, archive_root, dirs_exist_ok=True)
    return report


def wait_for_clean_host(
    spec: CampaignSpec,
    output_root: Path,
    raw_spec: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / ".metadata_never_index").touch(exist_ok=True)
    wait_root = output_root / "wait-preflight"
    sample_offset = len(list(wait_root.glob("sample-*.json")))
    started_at = time.monotonic()
    sample_count = 0
    consecutive_clean_samples = 0
    last_isolation = None
    while True:
        sample_count += 1
        snapshot = capture_host_state()
        isolation = evaluate_isolation(
            snapshot, spec.isolation, process_ancestry(snapshot.processes)
        )
        consecutive_clean_samples = (
            consecutive_clean_samples + 1 if isolation.accepted else 0
        )
        elapsed_seconds = time.monotonic() - started_at
        sample = {
            "schema_version": 1,
            "sample_index": sample_count,
            "consecutive_clean_samples": consecutive_clean_samples,
            "elapsed_seconds": elapsed_seconds,
            "host": snapshot.to_mapping(),
            "isolation": isolation.to_mapping(),
            "claims": dict(spec.claim_gates),
        }
        _write_json(
            wait_root / f"sample-{sample_offset + sample_count:04d}.json", sample
        )
        last_isolation = isolation.to_mapping()
        report = {
            "schema_version": 1,
            "accepted": consecutive_clean_samples
            >= spec.isolation.quiet_consecutive_samples,
            "sample_count": sample_count,
            "consecutive_clean_samples": consecutive_clean_samples,
            "required_consecutive_clean_samples": spec.isolation.quiet_consecutive_samples,
            "elapsed_seconds": elapsed_seconds,
            "last_isolation": last_isolation,
            "claims": dict(spec.claim_gates),
        }
        if report["accepted"]:
            _write_json(wait_root / "accepted.json", report)
            return report
        if elapsed_seconds >= spec.isolation.preflight_wait_timeout_seconds:
            _write_json(wait_root / "timeout.json", report)
            if raw_spec is not None:
                _write_blocked_campaign_result(spec, raw_spec, output_root, report)
            raise RuntimeError("clean-host preflight timed out")
        time.sleep(spec.isolation.quiet_sample_interval_seconds)


def execute_campaign(
    spec: CampaignSpec, raw_spec: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    output_root = output_root.resolve()
    manifest = prepare_campaign(spec, raw_spec, output_root)
    if not manifest["preflight"]["accepted"]:
        raise RuntimeError("campaign preflight failed")
    source_mapping = manifest["source"]
    source = SourceProvenance(
        revision=source_mapping["revision"],
        version=source_mapping["version"],
        tracked_diff_sha256=source_mapping["tracked_diff_sha256"],
        installed_binary_sha256=source_mapping["installed_binary_sha256"],
        installed_binary_path=source_mapping["installed_binary_path"],
        dirty_paths=tuple(source_mapping["dirty_paths"]),
        server_command=tuple(source_mapping["server_command"]),
        benchmark_command=tuple(source_mapping["benchmark_command"]),
        content_id=source_mapping["content_id"],
    )
    schedule = build_schedule(
        spec.concurrency_levels, spec.repeat_pairs, spec.schedule_seed
    )
    prompts_path = output_root / "prompts.jsonl"
    prompt_manifest = json.loads(
        (output_root / "prompt-manifest.json").read_text(encoding="utf-8")
    )
    prompt_records = prompt_manifest["requests"]
    expected_prompt_fixture_sha256 = manifest["workload"]["prompt_fixture_sha256"]
    results: list[RunResult] = []
    rejection_records = _load_rejections(output_root)
    resumed_pair_count = 0
    campaign_started_at = time.monotonic()
    for cold_index in range(0, len(schedule), 2):
        cold, warm = schedule[cold_index], schedule[cold_index + 1]
        resumed = _load_accepted_pair(output_root, cold, warm)
        if resumed is not None:
            results.extend(resumed)
            resumed_pair_count += 1
            continue
        attempt = len(list((output_root / "attempts" / cold.pair_id).glob("attempt-*")))
        while True:
            attempt += 1
            wait_seconds = (
                spec.isolation.cooldown_seconds
                if attempt == 1
                else max(
                    spec.isolation.cooldown_seconds,
                    spec.isolation.retry_wait_seconds,
                )
            )
            time.sleep(wait_seconds)
            attempt_root = (
                output_root / "attempts" / cold.pair_id / f"attempt-{attempt:02d}"
            )
            if sha256_file(prompts_path) != expected_prompt_fixture_sha256:
                raise RuntimeError("prompt fixture changed during campaign")
            prelaunch = capture_host_state()
            prelaunch_path = attempt_root / "host" / "prelaunch.json"
            _write_json(prelaunch_path, prelaunch.to_mapping())
            isolation = evaluate_isolation(
                prelaunch, spec.isolation, process_ancestry(prelaunch.processes)
            )
            if not isolation.accepted:
                rejection = {
                    "pair_id": cold.pair_id,
                    "attempt": attempt,
                    "phase": "prelaunch",
                    "isolation": isolation.to_mapping(),
                    "claims": dict(spec.claim_gates),
                }
                _write_json(attempt_root / "rejection.json", rejection)
                rejection_records.append(rejection)
                if attempt > spec.isolation.maximum_isolation_retries_per_pair:
                    _write_json(output_root / "campaign-aborted.json", rejection)
                    raise RuntimeError(
                        f"isolation retry budget exhausted for {cold.pair_id}"
                    )
                continue
            server = _launch_server(
                spec,
                attempt_root / "logs" / "server.stdout",
                attempt_root / "logs" / "server.stderr",
            )
            attempt_results: list[RunResult] = []
            rejection_error = None
            fatal_error = None
            try:
                startup_seconds = _wait_until_ready(server, spec)
                _write_json(
                    attempt_root / "server.json",
                    {
                        "pair_id": cold.pair_id,
                        "attempt": attempt,
                        "startup_seconds": startup_seconds,
                        "command": list(build_server_command(spec)),
                    },
                )
                _capture_named_host(attempt_root, "ready")
                cold_result = _run_benchmark(
                    spec,
                    cold,
                    prompts_path,
                    attempt_root,
                    source,
                    prompt_records,
                    isolation.accepted,
                    server.process.pid,
                )
                attempt_results.append(cold_result)
                if not cold_result.accepted:
                    if "host isolation gate failed" in cold_result.rejection_reasons:
                        raise IsolationViolation(
                            f"runtime isolation failed after {cold.pair_id} cold"
                        )
                    raise RuntimeError(f"run validation failed for {cold.pair_id} cold")
                warm_result = _run_benchmark(
                    spec,
                    warm,
                    prompts_path,
                    attempt_root,
                    source,
                    prompt_records,
                    isolation.accepted,
                    server.process.pid,
                )
                attempt_results.append(warm_result)
                if not warm_result.accepted:
                    if "host isolation gate failed" in warm_result.rejection_reasons:
                        raise IsolationViolation(
                            f"runtime isolation failed after {warm.pair_id} warm"
                        )
                    raise RuntimeError(f"run validation failed for {warm.pair_id} warm")
            except IsolationViolation as error:
                rejection_error = str(error)
            except Exception as error:
                fatal_error = f"{type(error).__name__}: {error}"
            finally:
                _stop_server(server)
            _capture_named_host(attempt_root, "postserver")
            if fatal_error is not None:
                failure = {
                    "pair_id": cold.pair_id,
                    "attempt": attempt,
                    "phase": "runtime_fatal",
                    "error": fatal_error,
                    "claims": dict(spec.claim_gates),
                }
                _write_json(attempt_root / "fatal.json", failure)
                _write_json(output_root / "campaign-aborted.json", failure)
                raise RuntimeError(fatal_error)
            if rejection_error is not None:
                rejection = {
                    "pair_id": cold.pair_id,
                    "attempt": attempt,
                    "phase": "runtime",
                    "error": rejection_error,
                    "discarded_run_count": len(attempt_results),
                    "claims": dict(spec.claim_gates),
                }
                _write_json(attempt_root / "rejection.json", rejection)
                rejection_records.append(rejection)
                if attempt > spec.isolation.maximum_isolation_retries_per_pair:
                    _write_json(output_root / "campaign-aborted.json", rejection)
                    raise RuntimeError(
                        f"isolation retry budget exhausted for {cold.pair_id}"
                    )
                continue
            results.extend(attempt_results)
            _write_json(
                output_root / "accepted-pairs" / f"{cold.pair_id}.json",
                {
                    "pair_id": cold.pair_id,
                    "attempt": attempt,
                    "attempt_root": str(attempt_root),
                    "run_count": len(attempt_results),
                    "claims": dict(spec.claim_gates),
                },
            )
            break
    post_source = capture_source(
        spec.engine,
        *_template_commands(
            spec, Path(str(raw_spec.get("source_command_root", output_root))).resolve()
        ),
    )
    integrity_reasons: list[str] = []
    if post_source.content_id != source.content_id:
        integrity_reasons.append("vLLM source identity changed during campaign")
    if (
        sha256_file(spec.engine.model_path / "model.safetensors")
        != spec.engine.checkpoint_sha256
    ):
        integrity_reasons.append("checkpoint identity changed during campaign")
    if sha256_file(prompts_path) != expected_prompt_fixture_sha256:
        integrity_reasons.append("prompt fixture identity changed during campaign")
    summary = summarize_campaign(
        results,
        expected_concurrency=spec.concurrency_levels,
        minimum_repeats=spec.acceptance.minimum_repeats_per_cell,
        primary_metrics=spec.acceptance.primary_metrics,
        maximum_cv=spec.acceptance.maximum_coefficient_of_variation,
        maximum_relative_ci_half_width=spec.acceptance.maximum_relative_ci_half_width,
    )
    report = {
        "schema_version": 1,
        "campaign_id": spec.campaign_id,
        "manifest_content_id": manifest["content_id"],
        "campaign_wall_seconds": time.monotonic() - campaign_started_at,
        "resumed_pair_count": resumed_pair_count,
        "rejected_attempt_count": len(rejection_records),
        "rejected_attempts": rejection_records,
        "prior_evidence": _summarize_prior_evidence(raw_spec),
        "integrity": {
            "accepted": not integrity_reasons,
            "rejection_reasons": integrity_reasons,
            "post_source": post_source.to_mapping(),
        },
        "summary": summary.to_mapping(),
        "campaign_accepted": (
            summary.acceptance.value == "pass" and not integrity_reasons
        ),
        "claims": dict(spec.claim_gates),
    }
    identity = dict(report)
    report["content_id"] = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    _write_json(output_root / "campaign-report.json", report)
    _write_json(Path(str(raw_spec["durable_report_path"])), report)
    archive_root = raw_spec.get("archive_root")
    if archive_root is not None and Path(str(archive_root)).resolve() != output_root:
        shutil.copytree(output_root, Path(str(archive_root)), dirs_exist_ok=True)
    return report
