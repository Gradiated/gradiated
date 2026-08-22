#!/usr/bin/env python3
"""Post-restart H200-bound cold-stage owner; worker 3 remains the first worker."""
from __future__ import annotations

import argparse
import pathlib
import shlex
import subprocess

import dflash_component_owner as base
import dflash_component_direct_recovery_owner_r2 as r2
import dflash_component_replacement_owner as retrieval

PROJECT = pathlib.Path(__file__).resolve().parent
DIRECTOR = PROJECT / "DIRECTOR_DFLASH_R3_POST_RESTART_HARDWARE_REBIND_20260730T0158Z.json"
PINNED_IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
RETAINED_PACKET_ARCHIVE_SHA256 = "e3f0bd4f187ac688112238a1886ab63c5d4090fb8c0c46884bb279cf018cd93a"


def require(value, fields, kind):
    for key, expected in fields.items():
        if value.get(key) != expected:
            raise base.Boundary(kind, f"{key}_mismatch", False)


def download_target_row(remote, binding, temporary, name, row):
    image = remote.run(
        f"sudo -n docker image inspect {shlex.quote(PINNED_IMAGE)} >/dev/null || "
        f"sudo -n docker pull {shlex.quote(PINNED_IMAGE)}",
        "cold-downloader-image", 1800, False,
    )
    if image.returncode:
        raise base.Boundary("cold_downloader_boundary", "pinned_image", True)
    quoted_name, quoted_target = shlex.quote(name), shlex.quote(temporary)
    downloader = (
        "from huggingface_hub import hf_hub_download; "
        f"hf_hub_download(repo_id='google/gemma-4-31B-it', filename={name!r}, "
        "revision='b9ea41a2887d8607f594846523f94c6cc75ac8a4', local_dir='/target')"
    )
    probe = remote.run(
        f"sudo -n docker run --rm --entrypoint python3 {shlex.quote(PINNED_IMAGE)} "
        "-c 'import huggingface_hub'",
        "cold-downloader-probe", 600, False,
    )
    if probe.returncode == 0:
        result = remote.run(
            f"sudo -n docker run --rm --entrypoint python3 "
            f"-v {quoted_target}:/target -v /home/glmrunner/.cache/huggingface:/root/.cache/huggingface "
            f"{shlex.quote(PINNED_IMAGE)} -c {shlex.quote(downloader)}",
            f"cold-target-download-image-{name}", 3600, False,
        )
    else:
        venv = binding["remote_run"] + "/claim-venv"
        result = remote.run(
            f"set -e; sudo -n apt-get update; sudo -n apt-get install -y python3-venv; "
            f"test -x {shlex.quote(venv + '/bin/python')} || python3 -m venv {shlex.quote(venv)}; "
            f"{shlex.quote(venv + '/bin/pip')} install --disable-pip-version-check 'huggingface_hub==0.26.2'; "
            f"{shlex.quote(venv + '/bin/python')} -c {shlex.quote(downloader.replace('/target', temporary))}",
            f"cold-target-download-venv-{name}", 3600, False,
        )
    if result.returncode:
        raise base.Boundary("cold_downloader_boundary", f"download:{name}", True)
    verified = remote.run(
        f"test \"$(sha256sum {shlex.quote(temporary + '/' + name)} | cut -d' ' -f1)\" = {shlex.quote(row['sha256'])}; "
        f"test $(stat -c%s {shlex.quote(temporary + '/' + name)}) -eq {row['bytes']}",
        f"cold-target-verify-{name}", 300, False,
    )
    if verified.returncode:
        raise base.Boundary("cold_downloader_boundary", f"verify:{name}", True)


def stage_target(remote, binding, root):
    manifest = base.load(PROJECT / "inputs/CHECKPOINT_MANIFEST.json")
    target, temporary = binding["remote_target_path"], binding["remote_target_path"] + ".part"
    complete = remote.run(f"test -f {shlex.quote(target + '/.COMPLETE.json')} && test -f {shlex.quote(target + '/config.json')}", "cold-target-reconcile", 60, False)
    if complete.returncode == 0:
        base.atomic(root / "COLD_STAGE.json", {"state": "reused_complete", "target": target})
        return
    remote.run(f"mkdir -p {shlex.quote(temporary)}", "cold-target-parent", 60)
    for row in manifest["files"]:
        name = row["name"]
        check = remote.run(
            f"test -f {shlex.quote(temporary + '/' + name)} && "
            f"test \"$(sha256sum {shlex.quote(temporary + '/' + name)} | cut -d' ' -f1)\" = {shlex.quote(row['sha256'])} && "
            f"test $(stat -c%s {shlex.quote(temporary + '/' + name)}) -eq {row['bytes']}",
            f"cold-target-check-{name}", 300, False,
        )
        if check.returncode:
            download_target_row(remote, binding, temporary, name, row)
        base.atomic(root / "COLD_STAGE.json", {"state": "transferring", "target": target, "last_verified": name})
    remote.run(f"set -e; test ! -e {shlex.quote(target)}; printf '%s\\n' {shlex.quote(binding['target_manifest_sha256'])} > {shlex.quote(temporary + '/.COMPLETE.json')}; mv {shlex.quote(temporary)} {shlex.quote(target)}", "cold-target-finalize", 120)
    base.atomic(root / "COLD_STAGE.json", {"state": "complete", "target": target, "manifest_sha256": binding["target_manifest_sha256"]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    binding = base.load(args.execution_binding.resolve())
    director = base.load(DIRECTOR)
    require(binding, {"schema_version": 1, "project": base.PROJECT_NAME,
                      "bench_id": director["claim"]["bench_id"], "claimed_at": director["claim"]["claimed_at"],
                      "gpu_uuid": director["claim"]["new_gpu_uuid"], "director_sha256": base.sha256(DIRECTOR),
                      "owner_source": pathlib.Path(__file__).name, "owner_source_sha256": base.sha256(pathlib.Path(__file__)),
                      "initial_worker_generation": 3, "packet_archive_sha256": RETAINED_PACKET_ARCHIVE_SHA256}, "r4_execution_boundary")
    root = args.artifact_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    deadline = base.parse_time(binding["owner_deadline_utc"])
    bench = base.validate_claim(binding)
    remote = base.Remote(bench, root, deadline)
    with base.Heartbeat(root, binding["claimed_at"]):
        base.atomic(root / "PHASE.json", {"phase": "cold_stage_resumed_expanded_root", "claimed_at": binding["claimed_at"]})
        while True:
            try:
                stage_target(remote, binding, root)
                break
            except (base.Boundary, subprocess.TimeoutExpired) as error:
                if isinstance(error, base.Boundary) and not error.recoverable:
                    raise
                diagnostic = root / "COLD_STAGE_DIAGNOSTIC.json"
                base.atomic(diagnostic, {"classification": "recoverable_pre_science_cold_stage_dependency", "kind": getattr(error, "kind", "remote_timeout"), "message": getattr(error, "message", str(error)), "retry_scope": "cold_stage", "claimed_at": binding["claimed_at"]})
                disposition, _, _ = r2.dispatch_repair(root, binding, diagnostic, "cold_stage", deadline, 3)
                if disposition == "valid":
                    continue
                if disposition == "repair_terminal":
                    base.release(binding, root, condition="maintenance", summary="r4 cold-stage repair terminal.", state="maintenance_r4_cold_stage_repair_terminal")
                    return 77
                base.release(binding, root, condition="maintenance", summary="r4 cold-stage repair deadline.", state="maintenance_r4_cold_stage_deadline")
                return 77
        archive = PROJECT / "DFLASH_H200_COMPONENT_PACKET.tar"
        if base.sha256(archive) != binding["packet_archive_sha256"]:
            raise base.Boundary("r4_packet_boundary", "digest", False)
        number, scope = 3, "all"
        while base.utc_now() < deadline:
            snap, adoption, diagnostic = r2.worker(remote, binding, {"remote_run": binding["remote_run"]}, archive, root, number, scope, deadline)
            if adoption["classification"] == "scientific_terminal":
                return retrieval.finalize_terminal(binding, root, snap)
            disposition, patch, _ = r2.dispatch_repair(root, binding, diagnostic, str(adoption.get("retry_scope", "classify")), deadline, number)
            if disposition != "valid":
                base.release(binding, root, condition="maintenance", summary=f"r4 {disposition} after retrieved worker.", state=f"maintenance_r4_{disposition}")
                return 77
            archive, scope, number = pathlib.Path(patch["packet_archive"]), str(patch["retry_scope"]), number + 1
    base.release(binding, root, condition="maintenance", summary="r4 owner deadline.", state="maintenance_r4_deadline")
    return 77


if __name__ == "__main__":
    raise SystemExit(main())
