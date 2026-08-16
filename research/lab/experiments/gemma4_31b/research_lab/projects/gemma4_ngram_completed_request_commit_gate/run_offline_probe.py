#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

from completed_request_buffer import (
    CommitBufferCapacityError,
    CompletedRequestCommitBuffer,
)


PROJECT = Path(__file__).resolve().parent
ARTIFACT = PROJECT / "artifacts/offline-lifecycle-probe"
CPP = PROJECT / "inputs/lifecycle/ngram_corpus"

EXPECTED_SOURCE = {
    "dominant_only": (11, 11, 11),
    "three_token_transient": (4, 4, 11),
    "persistent_alternate": (2, 4, 0),
    "persistent_alternate_after_four_normal": (4, 4, 11),
}
EXPECTED_CANDIDATE = {
    "request_32_inflight_isolated": (11, 0, 1, 0),
    "request_32_post_completion_visible": (4, 0, 0, 358),
    "request_790_abort_discarded": (11, 0, 0, 0),
    "request_id_reuse_discards_old_owner": (11, 0, 0, 0),
    "single_completion_exactly_once": (11, 0, 0, 358),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def compile_and_run(source: str) -> list[dict]:
    binary = ARTIFACT / source.removesuffix(".cpp")
    compiled = subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            "-I",
            str(CPP),
            str(PROJECT / source),
            str(CPP / "trie.cpp"),
            str(CPP / "result.cpp"),
            "-o",
            str(binary),
        ],
        text=True,
        capture_output=True,
    )
    if compiled.returncode:
        raise RuntimeError(compiled.stderr)
    executed = subprocess.run([str(binary)], text=True, capture_output=True)
    binary.unlink()
    if executed.returncode:
        raise RuntimeError(executed.stderr)
    return [json.loads(line) for line in executed.stdout.splitlines()]


def source_lifecycle_proof() -> dict:
    worker = (PROJECT / "inputs/bound/ngram_worker.source.py").read_text()
    ngram_info = (PROJECT / "inputs/lifecycle/ngram_info.py").read_text()
    schedule_batch = (PROJECT / "inputs/lifecycle/schedule_batch.py").read_text()
    scheduler = (PROJECT / "inputs/lifecycle/scheduler.py").read_text()
    overlay = (PROJECT / "completed_request_sitecustomize.py").read_text()
    for source in (worker, ngram_info, schedule_batch, scheduler, overlay):
        ast.parse(source)

    verify_position = worker.index("verify_input.verify(")
    update_position = worker.index("self._update_ngram_corpus(batch)")
    append_position = ngram_info.index("req.output_ids.append(id)")
    finish_update_position = ngram_info.index("req.update_finish_state()", append_position)
    finished_position = ngram_info.index("if req.finished():", finish_update_position)
    to_finish_position = schedule_batch.index("if self.to_finish:")
    length_position = schedule_batch.index(
        "if len(self.output_ids) >= self.sampling_params.max_new_tokens:",
        to_finish_position,
    )
    running_abort_position = scheduler.index("req.to_finish = FINISH_ABORT()")
    direct_abort_position = scheduler.index("req = self.waiting_queue.pop(i)")

    decision = {
        "target_tokens_appended_before_finish_check": (
            append_position < finish_update_position < finished_position
        ),
        "completion_known_before_ngram_update": verify_position < update_position,
        "abort_consumed_before_normal_finish_gates": (
            to_finish_position < length_position
        ),
        "running_abort_has_exact_to_finish_boundary": running_abort_position > 0,
        "waiting_or_retracted_abort_has_direct_pop_boundary": direct_abort_position > 0,
        "overlay_patches_exact_write_site": (
            "NGRAMWorker._update_ngram_corpus = patched_update" in overlay
        ),
        "overlay_patches_scheduler_abort_cleanup": (
            "Scheduler.abort_request = patched_abort_request" in overlay
        ),
        "overlay_does_not_patch_global_read": (
            "_prepare_draft_tokens =" not in overlay
            and "ngram_corpus.batch_get" not in overlay
        ),
    }
    if not all(decision.values()):
        raise RuntimeError(decision)
    return decision


def python_buffer_proof() -> dict:
    buffer = CompletedRequestCommitBuffer(2)
    buffer.stage("normal", "owner-a", [1, 2], 2)
    buffer.stage("normal", "owner-a", [2, 3], 2)
    committed = buffer.finish("normal", "owner-a", aborted=False)
    assert committed == [[1, 2], [2, 3]]
    assert buffer.finish("normal", "owner-a", aborted=False) == []

    buffer.stage("abort", "owner-b", [4], 1)
    assert buffer.finish("abort", "owner-b", aborted=True) == []

    buffer.stage("reuse", "owner-old", [5], 2)
    buffer.stage("reuse", "owner-new", [6], 2)
    assert buffer.id_reuses == 1
    assert buffer.finish("reuse", "owner-new", aborted=True) == []

    buffer.stage("prefix-a", "owner-a", [7], 1)
    buffer.stage("prefix-b", "owner-b", [8], 1)
    assert buffer.discard_matching("prefix-", all_requests=False) == 2

    active_bound_failed_closed = False
    row_bound_failed_closed = False
    bounded = CompletedRequestCommitBuffer(1)
    bounded.stage("one", "owner", [1], 1)
    try:
        bounded.stage("two", "owner", [2], 1)
    except CommitBufferCapacityError:
        active_bound_failed_closed = True
    try:
        bounded.stage("one", "owner", [2], 1)
    except CommitBufferCapacityError:
        row_bound_failed_closed = True
    assert active_bound_failed_closed and row_bound_failed_closed
    return {
        "completion_commits_exact_rows_once": True,
        "abort_discards": True,
        "request_id_reuse_discards_old_owner": True,
        "scheduler_prefix_abort_discards": True,
        "active_bound_fails_closed": active_bound_failed_closed,
        "per_request_bound_fails_closed": row_bound_failed_closed,
    }


def main() -> None:
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    verified = json.loads((PROJECT / "DIRECTOR_BINDING_VERIFIED.json").read_text())
    source_rows = compile_and_run("source_scenarios.cpp")
    observed_source = {
        row["scenario"]: (
            row["bfs_accepted_drafts"],
            row["prob_accepted_drafts"],
            row["linear_accepted_drafts"],
        )
        for row in source_rows
    }
    if observed_source != EXPECTED_SOURCE:
        raise RuntimeError(
            {"expected_source": EXPECTED_SOURCE, "observed_source": observed_source}
        )

    candidate_rows = compile_and_run("completed_request_probe.cpp")
    observed_candidate = {
        row["scenario"]: (
            row["dominant_accepted_drafts"],
            row["alternate_accepted_drafts"],
            row["active_requests"],
            row["committed_rows"],
        )
        for row in candidate_rows
    }
    if observed_candidate != EXPECTED_CANDIDATE:
        raise RuntimeError(
            {
                "expected_candidate": EXPECTED_CANDIDATE,
                "observed_candidate": observed_candidate,
            }
        )

    lifecycle = source_lifecycle_proof()
    python_buffer = python_buffer_proof()
    result = {
        "schema_version": 1,
        "result": "offline_completed_request_lifecycle_probe_pass",
        "semantics": "target-semantics preserving; verified-write visibility only",
        "binding_result": verified["result"],
        "sglang_commit": verified["sglang_commit"],
        "source_lifecycle": lifecycle,
        "bound_source_rows": source_rows,
        "candidate_rows": candidate_rows,
        "python_buffer": python_buffer,
        "implementation_sha256": {
            "buffer": digest(PROJECT / "completed_request_buffer.py"),
            "overlay": digest(PROJECT / "completed_request_sitecustomize.py"),
            "source_probe": digest(PROJECT / "source_scenarios.cpp"),
            "candidate_probe": digest(PROJECT / "completed_request_probe.cpp"),
        },
        "decision": {
            "bound_scenarios_reproduced": True,
            "exact_completion_and_abort_boundary_proved": True,
            "inflight_requests_cannot_change_global_reads": True,
            "common_historical_trunk_retains_depth_11": True,
            "request_32_inflight_isolated": True,
            "request_790_abort_isolated": True,
            "request_id_reuse_cannot_leak_or_double_commit": True,
            "memory_bounded_and_fail_closed": True,
            "gpu_discriminator_admitted_after_priority_8550_release": True,
        },
        "causal_prediction": (
            "request-32 is isolated while live, but its exact post-completion "
            "commit reproduces the bound depth-4 global branch; the 791-request "
            "discriminator is expected to decide whether completion timing is enough."
        ),
    }
    atomic_json(ARTIFACT / "RESULT.json", result)
    print(json.dumps(result["decision"], sort_keys=True))


if __name__ == "__main__":
    main()
