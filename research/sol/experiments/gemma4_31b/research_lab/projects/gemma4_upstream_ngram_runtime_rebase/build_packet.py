#!/usr/bin/env python3
import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
WORKSPACE = next(parent for parent in PROJECT.parents if parent.name == "workspace")
PINNED_SOURCE = WORKSPACE / ".agents/runtime/sglang-v0.5.13-source"
CANDIDATE_SOURCE = WORKSPACE / ".agents/runtime/sglang-v0.5.15-full-checkout"
PACKET = PROJECT / "artifacts/candidate-v0.5.15"
PINNED_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
CANDIDATE_COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
)
IMAGE_INDEX_DIGEST = (
    "sha256:cf821c60ddc04db0e0c7f92b3612a344a08f78136968a40122eb5ba67bb69910"
)
SOURCE_PATHS = [
    "docker/Dockerfile",
    "python/sglang/srt/server_args.py",
    "python/sglang/srt/arg_groups/speculative_hook.py",
    "python/sglang/srt/speculative/cpp_ngram/ngram_corpus.py",
    "python/sglang/srt/speculative/ngram_worker.py",
    "python/sglang/srt/speculative/ngram_info.py",
    "python/sglang/srt/speculative/spec_info.py",
    "python/sglang/srt/speculative/spec_utils.py",
    "python/sglang/srt/managers/scheduler_components/batch_result_processor.py",
    "python/sglang/srt/layers/attention/triton_backend.py",
    "python/sglang/srt/layers/attention/hybrid_attn_backend.py",
    "python/sglang/srt/models/gemma4_causal.py",
    "python/sglang/srt/model_executor/runner/decode_cuda_graph_runner.py",
]
CAUSAL_COMMITS = [
    (
        "111009ea542e3430d8eed6e8e99dd8558982699f",
        "NGRAM spec-v2 migration",
    ),
    (
        "854c688121ed29f49bc862fe19357eecd6c72b30",
        "single-owner accepted-KV settlement",
    ),
]
EXTRA_BOUND_INPUTS = {
    "TRACE_PACKET.json": "ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68"
}


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest(path):
    return digest_bytes(path.read_bytes())


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    part.replace(path)


def command(*args, cwd=None):
    return subprocess.run(
        args, cwd=cwd, text=True, capture_output=True, check=True
    ).stdout.strip()


def git_blob(source, revision, path):
    return command("git", "rev-parse", f"{revision}:{path}", cwd=source)


def source_text(source, path):
    return (source / path).read_text()


def verify_checkout(source, expected):
    actual = command("git", "rev-parse", "HEAD", cwd=source)
    if actual != expected:
        raise RuntimeError(f"checkout_identity_mismatch:{source}:{actual}")
    if command("git", "status", "--porcelain", cwd=source):
        raise RuntimeError(f"checkout_dirty:{source}")


def verify_binding():
    binding = json.loads((PROJECT / "DIRECTOR_BINDING.json").read_text())
    rows = []
    for name, spec in binding["bound_inputs"].items():
        path = (PROJECT / spec["path"]).resolve()
        actual = digest(path)
        rows.append(
            {
                "name": name,
                "source_path": str(path),
                "expected_sha256": spec["sha256"],
                "actual_sha256": actual,
                "verified": actual == spec["sha256"],
            }
        )
    if not all(row["verified"] for row in rows):
        raise RuntimeError("director_binding_verification_failed")
    result = {
        "schema_version": 1,
        "director_binding_sha256": digest(PROJECT / "DIRECTOR_BINDING.json"),
        "baseline": binding["baseline"],
        "bound_inputs": rows,
        "all_verified": True,
    }
    atomic_json(PROJECT / "DIRECTOR_BINDING_VERIFIED.json", result)
    return binding, result


def verify_source_contract():
    verify_checkout(CANDIDATE_SOURCE, CANDIDATE_COMMIT)
    pinned_worker = (
        PINNED_SOURCE / "python/sglang/srt/speculative/ngram_worker.py"
    )
    binding = json.loads((PROJECT / "DIRECTOR_BINDING.json").read_text())
    expected_worker = binding["bound_inputs"]["pinned_ngram_worker_source"]["sha256"]
    if digest(pinned_worker) != expected_worker:
        raise RuntimeError("pinned_checkout_worker_mismatch")

    hook = source_text(
        CANDIDATE_SOURCE, "python/sglang/srt/arg_groups/speculative_hook.py"
    )
    server_args = source_text(
        CANDIDATE_SOURCE, "python/sglang/srt/server_args.py"
    )
    worker = source_text(
        CANDIDATE_SOURCE, "python/sglang/srt/speculative/ngram_worker.py"
    )
    info = source_text(
        CANDIDATE_SOURCE, "python/sglang/srt/speculative/ngram_info.py"
    )
    processor = source_text(
        CANDIDATE_SOURCE,
        "python/sglang/srt/managers/scheduler_components/batch_result_processor.py",
    )
    gemma = source_text(
        CANDIDATE_SOURCE, "python/sglang/srt/models/gemma4_causal.py"
    )
    triton = source_text(
        CANDIDATE_SOURCE, "python/sglang/srt/layers/attention/triton_backend.py"
    )
    cuda_graph = source_text(
        CANDIDATE_SOURCE,
        "python/sglang/srt/model_executor/runner/decode_cuda_graph_runner.py",
    )
    checks = {
        "native_ngram_registered": '"NGRAM"' in server_args,
        "native_ngram_depth_12_default": (
            "server_args.speculative_num_draft_tokens = 12" in hook
        ),
        "fp8_quantization_supported": '"fp8"' in server_args,
        "fp8_e5m2_kv_supported": '"fp8_e5m2"' in server_args,
        "tree_reconstruction_present": (
            "reconstruct_indices_from_tree_mask(" in worker
        ),
        "target_verify_present": "ForwardMode.TARGET_VERIFY" in worker,
        "accepted_kv_move_present": (
            "move_accept_tokens_to_target_kvcache(" in worker
        ),
        "accepted_seq_len_uses_full_run": (
            "new_seq_lens = batch.seq_lens + accept_lens" in worker
        ),
        "request_cleanup_present": (
            "departed_rids = self._prev_decode_rids - cur_rids" in worker
            and "erase_match_state(list(departed_rids))" in worker
        ),
        "ngram_info_has_no_worker_kv_commit": "kv_committed_len" not in info,
        "scheduler_is_single_kv_commit_owner": (
            "req.kv_committed_len += num_accept_tokens" in processor
            and "req.kv_committed_len += num_accept_tokens - 1" not in processor
        ),
        "gemma_hybrid_local_global_dispatch": (
            'layer_type == "sliding_attention"' in gemma
            and "sliding_window_size=self.sliding_window" in gemma
        ),
        "triton_target_verify_geometry": (
            "target_verify" in triton and "cuda_graph_custom_mask" in triton
        ),
        "ngram_cuda_graph_geometry": (
            "self.model_runner.spec_algorithm.is_ngram()" in cuda_graph
            and "NgramVerifyInput(" in cuda_graph
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("candidate_source_contract_failed:" + ",".join(failed))
    return checks


def materialize_inputs(binding):
    input_dir = PACKET / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, spec in binding["bound_inputs"].items():
        source = (PROJECT / spec["path"]).resolve()
        target = input_dir / source.name
        shutil.copy2(source, target)
        manifest[target.name] = digest(target)
    for name, expected in EXTRA_BOUND_INPUTS.items():
        source = (
            PROJECT
            / "../gemma4_ngram_completed_request_commit_gate/inputs/bound"
            / name
        ).resolve()
        if digest(source) != expected:
            raise RuntimeError(f"extra_input_hash_mismatch:{name}")
        target = input_dir / name
        shutil.copy2(source, target)
        manifest[name] = digest(target)
    atomic_json(input_dir / "INPUT_MANIFEST.json", manifest)
    return manifest


def materialize_sources():
    source_rows = []
    diffs = []
    for path in SOURCE_PATHS:
        candidate = CANDIDATE_SOURCE / path
        target = PACKET / "source" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, target)
        pinned = PINNED_SOURCE / path
        pinned_text = pinned.read_text().splitlines(keepends=True) if pinned.exists() else []
        candidate_text = candidate.read_text().splitlines(keepends=True)
        diffs.extend(
            difflib.unified_diff(
                pinned_text,
                candidate_text,
                fromfile=f"pinned/{path}",
                tofile=f"candidate/{path}",
            )
        )
        source_rows.append(
            {
                "path": path,
                "git_blob": git_blob(CANDIDATE_SOURCE, "HEAD", path),
                "sha256": digest(candidate),
                "pinned_sha256": digest(pinned) if pinned.exists() else None,
            }
        )
    diff_path = PACKET / "diffs/pinned-to-v0.5.15-relevant.patch"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text("".join(diffs))
    history_source = WORKSPACE / ".agents/runtime/sglang-v0.5.13-source"
    commit_rows = []
    for commit, role in CAUSAL_COMMITS:
        patch = command(
            "git", "show", "--format=fuller", "--no-ext-diff", commit,
            cwd=history_source,
        )
        path = PACKET / "diffs" / f"{commit}.patch"
        path.write_text(patch + "\n")
        commit_rows.append(
            {"commit": commit, "role": role, "patch_sha256": digest(path)}
        )
    return source_rows, commit_rows, digest(diff_path)


def write_packet(binding, checks, inputs, sources, commits, diff_sha):
    launch = json.loads((PACKET / "inputs/ngram-launch.json").read_text())
    causal_map = {
        "schema_version": 1,
        "evidence_label": "source-derived",
        "pinned_runtime": PINNED_COMMIT,
        "candidate_runtime": CANDIDATE_COMMIT,
        "mechanism": (
            "The pinned release uses NGRAM spec-v1: NgramVerifyInput._free_cache "
            "selects and moves accepted KV, mutates req.kv_committed_len and "
            "req.kv_allocated_len, and rewrites req_to_token before the next verify. "
            "v0.5.15 uses the upstream NGRAM spec-v2 producer/consumer path: target "
            "verification moves accepted KV, publishes seq_lens + accept_lens, and the "
            "scheduler is the sole owner of req.kv_committed_len. This replaces the "
            "entire cache-position state transition that feeds the next Gemma "
            "sliding/global attention verification."
        ),
        "paths": [
            {
                "stage": "proposal",
                "path": "python/sglang/srt/speculative/cpp_ngram/ngram_corpus.py",
                "symbol": "NgramCorpus.batch_get",
            },
            {
                "stage": "tree_and_positions",
                "path": "python/sglang/srt/speculative/ngram_worker.py",
                "symbol": "reconstruct_indices_from_tree_mask",
            },
            {
                "stage": "target_verification",
                "path": "python/sglang/srt/speculative/ngram_worker.py",
                "symbol": "NGRAMWorker.forward_batch_generation",
            },
            {
                "stage": "accepted_kv_move",
                "path": "python/sglang/srt/speculative/ngram_worker.py",
                "symbol": "move_accept_tokens_to_target_kvcache",
            },
            {
                "stage": "accepted_kv_commit_owner",
                "path": (
                    "python/sglang/srt/managers/scheduler_components/"
                    "batch_result_processor.py"
                ),
                "symbol": "SchedulerBatchResultProcessor._resolve_spec_v2_tokens",
            },
            {
                "stage": "request_cleanup",
                "path": "python/sglang/srt/speculative/ngram_worker.py",
                "symbol": "_prev_decode_rids/erase_match_state",
            },
            {
                "stage": "gemma_hybrid_attention",
                "path": "python/sglang/srt/models/gemma4_causal.py",
                "symbol": "Gemma4Attention",
            },
            {
                "stage": "triton_tree_verify",
                "path": "python/sglang/srt/layers/attention/triton_backend.py",
                "symbol": "TritonAttnBackend target_verify metadata",
            },
            {
                "stage": "cuda_graph_geometry",
                "path": (
                    "python/sglang/srt/model_executor/runner/"
                    "decode_cuda_graph_runner.py"
                ),
                "symbol": "NgramVerifyInput capture",
            },
        ],
        "causal_commits": commits,
        "falsifier": (
            "The candidate is rejected if requests 0..170 at bound arrivals are not "
            "exact, native NGRAM activation is not observed, or source/image identity "
            "does not match. Passing admits one unmodified 791-request endpoint only; "
            "it does not transfer pinned-runtime economics."
        ),
    }
    atomic_json(PACKET / "SOURCE_PATH_CAUSAL_MAP.json", causal_map)
    upstream_audit = {
        "schema_version": 1,
        "evidence_label": "official-git-source-derived",
        "source_observed_date": "2026-07-25",
        "ref_query": [
            "git",
            "ls-remote",
            "https://github.com/sgl-project/sglang.git",
            "HEAD",
            "refs/tags/v0.5.14^{}",
            "refs/tags/v0.5.15^{}",
            "refs/tags/v0.5.16^{}",
        ],
        "refs": {
            "HEAD": "6a046fad09d4ea4b377c5d98149edd1e55d52d5d",
            "v0.5.14": "49e384ce9d304648e9959666ecb8ce8cd98d0deb",
            "v0.5.15": CANDIDATE_COMMIT,
            "v0.5.16": "fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1",
        },
        "path_findings": {
            "pinned_v0.5.13": (
                "NGRAM spec-v1 owns accepted-KV free/move, req KV watermarks, "
                "req_to_token mapping, and finish/output mutation inside verify."
            ),
            "v0.5.14": (
                "Contains part of the newer stack but retains algorithm-split "
                "scheduler KV settlement; rejected as an intermediate state."
            ),
            "v0.5.15": (
                "First stable release containing upstream NGRAM spec-v2 plus commit "
                "854c688 single-owner full accepted-run settlement."
            ),
            "v0.5.16_and_HEAD": (
                "Retain the v0.5.15 repair. Later relevant-path changes are "
                "refactors, retraction policy, grammar, or non-Triton backends; "
                "none adds a narrower causal fix for this bound launch."
            ),
        },
        "candidate_minimizes_runtime_drift": True,
    }
    atomic_json(PACKET / "UPSTREAM_AUDIT.json", upstream_audit)
    runtime = {
        "schema_version": 1,
        "decision": "nominate_one",
        "candidate": {
            "release": "v0.5.15",
            "tag_object": "d80c135a4f961a5118959de022934fc2dc598c21",
            "commit": CANDIDATE_COMMIT,
            "official_repository": "https://github.com/sgl-project/sglang.git",
            "official_image": IMAGE,
            "official_image_index_digest": IMAGE_INDEX_DIGEST,
            "official_image_platform": "linux/amd64",
            "image_build_commit_label": CANDIDATE_COMMIT,
            "cuda_version": "12.9.1",
            "dockerfile_sha256": digest(CANDIDATE_SOURCE / "docker/Dockerfile"),
        },
        "selection": {
            "current_official_head_inspected": (
                "6a046fad09d4ea4b377c5d98149edd1e55d52d5d"
            ),
            "v0.5.14": "rejected: retains split speculative KV settlement",
            "v0.5.15": "selected: first stable release with single-owner settlement",
            "v0.5.16": "not selected: no additional Triton NGRAM semantic repair; more drift",
        },
        "model": binding["baseline"]["model"],
        "launch": launch,
        "launch_change": "image identity only; no overlay and no flag change",
        "reproduction": {
            "registry_identity_command": [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                "docker.io/lmsysorg/sglang:v0.5.15-cu129",
                "--format",
                "{{json .Image}}",
            ],
            "pull_command": ["docker", "pull", IMAGE],
            "container": {
                "name": "gemma4-ngram-upstream-v0515",
                "image": IMAGE,
                "runtime_options": [
                    "--gpus",
                    "all",
                    "--ipc=host",
                    "--network=host",
                ],
                "mounts": [
                    {
                        "source": (
                            "/home/glmrunner/"
                            "gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
                        ),
                        "target": "/work/checkpoint",
                        "read_only": True,
                    }
                ],
                "command": ["python3", "-m", "sglang.launch_server", *launch["args"]],
            },
            "runner_command": [
                "env",
                "UPSTREAM_REBASE_ROOT=/absolute/path/to/staged/candidate-v0.5.15",
                "UPSTREAM_REBASE_REQUESTS=171",
                "python3",
                "remote_runtime_discriminator.py",
            ],
            "authority_boundary": (
                "Do not pull, replace the resident server, claim the bench, or run "
                "this packet until the director authorizes paid execution after the "
                "priority-8500 predecessor releases."
            ),
        },
        "source_contract": checks,
        "source_files": sources,
        "relevant_diff_sha256": diff_sha,
        "discriminator": {
            "runner": "remote_runtime_discriminator.py",
            "requests": {"begin": 0, "end_exclusive": 171},
            "release_policy": "individual_bound_arrival_s",
            "semantic_gate": "all 171 normalized responses exact; zero failures",
            "activation_gate": (
                "container image/commit/argv exact and observed spec_accept_length > 1"
            ),
            "deadline": "45 claimed minutes",
            "spend_cap_usd": 3.0,
            "conditional_next": (
                "Only after every discriminator gate passes, run the unmodified "
                "791-request endpoint and apply PROJECT.md economic/queue gates."
            ),
        },
        "provider_authority": "none in this phase",
        "inputs": inputs,
    }
    atomic_json(PACKET / "CANDIDATE_RUNTIME.json", runtime)
    shutil.copy2(
        PROJECT / "remote_runtime_discriminator.py",
        PACKET / "remote_runtime_discriminator.py",
    )


def write_manifest():
    rows = {}
    for path in sorted(PACKET.rglob("*")):
        if (
            path.is_file()
            and path.name != "SHA256SUMS.json"
            and path.suffix != ".pyc"
            and "__pycache__" not in path.parts
        ):
            rows[path.relative_to(PACKET).as_posix()] = digest(path)
    atomic_json(PACKET / "SHA256SUMS.json", rows)
    return rows


def verify_packet():
    manifest_path = PACKET / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text())
    failures = []
    actual_files = {
        path.relative_to(PACKET).as_posix()
        for path in PACKET.rglob("*")
        if path.is_file()
        and path.name != "SHA256SUMS.json"
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
    }
    unexpected = sorted(actual_files - set(manifest))
    missing = sorted(set(manifest) - actual_files)
    if unexpected or missing:
        failures.append({"unexpected_files": unexpected, "missing_files": missing})
    for name, expected in manifest.items():
        path = PACKET / name
        actual = digest(path) if path.is_file() else None
        if actual != expected:
            failures.append(
                {"path": name, "expected_sha256": expected, "actual_sha256": actual}
            )
    runtime = json.loads((PACKET / "CANDIDATE_RUNTIME.json").read_text())
    result = {
        "schema_version": 1,
        "packet": str(PACKET),
        "candidate_commit": runtime["candidate"]["commit"],
        "candidate_image": runtime["candidate"]["official_image"],
        "files": len(manifest),
        "failures": failures,
        "verified": not failures,
    }
    if failures:
        raise RuntimeError("packet_hash_verification_failed:" + repr(failures))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        print(json.dumps(verify_packet(), sort_keys=True, indent=2))
        return
    binding, _ = verify_binding()
    checks = verify_source_contract()
    PACKET.mkdir(parents=True, exist_ok=True)
    for cache in PACKET.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache)
    inputs = materialize_inputs(binding)
    sources, commits, diff_sha = materialize_sources()
    write_packet(binding, checks, inputs, sources, commits, diff_sha)
    write_manifest()
    print(json.dumps(verify_packet(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
