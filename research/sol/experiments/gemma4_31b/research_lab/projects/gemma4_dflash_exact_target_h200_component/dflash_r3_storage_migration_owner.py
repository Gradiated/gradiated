#!/usr/bin/env python3
"""Claim-bound migration of the r3 cold-stage partial; no science execution."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

PROJECT = pathlib.Path(__file__).resolve().parent
ROOT = PROJECT / "artifacts/dflash-h200-r3-storage-migration"
DIRECTOR = PROJECT / "DIRECTOR_DFLASH_R3_STORAGE_MIGRATION_REPAIR_20260730T0141Z.json"
EXECUTION = PROJECT / "artifacts/dflash-h200-r3-cold-worker3/EXECUTION_BINDING.json"
RUN = PROJECT / "artifacts/dflash-h200-r3-cold-worker3/run"
DIAGNOSTIC = RUN / "COLD_STAGE_DIAGNOSTIC.json"
REPAIR_ID = "dflash-h200-r3-cold-worker3-20260730t0045z-recovery-r2-3-dispatch-0"
HANDSHAKE = RUN / ".repair-handshakes" / REPAIR_ID
REPAIR_TOOL = pathlib.Path("/root/workspace/research/factory/tools/repair-handshake")
PACKET = PROJECT / "artifacts/dflash-h200-direct-owner-r2-20260729t2344z/dflash-component-repair3-generation-output-packet.tar"
EXPECTED = {
    "binding": "2ad42cce7608172c9d9edd40c08a7edd53086008c5858c420e2adebcb2c46ad0",
    "ready": "b11608d38489e543a88d9fbd02c2c34247e8c9c8c7d093d877b4ec4ec30c1022",
    "diagnostic": "00e2cf8b6114a686f5467d5ac5fa2c6f17de5eb961dffe56172278e86cc9b325",
    "packet": "e3f0bd4f187ac688112238a1886ab63c5d4090fb8c0c46884bb279cf018cd93a",
}
DEADLINE = datetime.datetime.fromisoformat("2026-07-30T02:05:00+00:00")


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: pathlib.Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"not_object:{path}")
    return value


def start_ticks(pid: int) -> int | None:
    try:
        return int(pathlib.Path(f"/proc/{pid}/stat").read_text().split()[21])
    except (FileNotFoundError, ValueError):
        return None


def timeout(cap: int) -> int:
    remaining = int((DEADLINE - now()).total_seconds()) - 15
    if remaining <= 0:
        raise RuntimeError("migration_deadline_exhausted")
    return min(cap, remaining)


def preflight() -> tuple[dict[str, object], dict[str, object]]:
    director, binding = load(DIRECTOR), load(EXECUTION)
    if sha256(EXECUTION) != EXPECTED["binding"] or sha256(DIAGNOSTIC) != EXPECTED["diagnostic"]:
        raise RuntimeError("bound_input_digest_mismatch")
    if sha256(HANDSHAKE / "REPAIR_READY.json") != EXPECTED["ready"] or sha256(PACKET) != EXPECTED["packet"]:
        raise RuntimeError("repair_or_packet_digest_mismatch")
    owner = director["live_owner"]
    if owner["pid"] != 446635 or owner["start_ticks"] != 148998370 or start_ticks(446635) != 148998370:
        raise RuntimeError("live_owner_identity_mismatch")
    if binding["claimed_at"] != "2026-07-30T00:49:46.346350Z":
        raise RuntimeError("claim_generation_mismatch")
    inventory = load(PROJECT.parents[1] / "runtime/gpus.json")
    benches = inventory["benches"]
    bench = benches[binding["bench_id"]] if isinstance(benches, dict) else next(item for item in benches if item["id"] == binding["bench_id"])
    if bench["claim"]["claimed_at"] != binding["claimed_at"] or bench["claim"]["project"] != director["project"]:
        raise RuntimeError("live_claim_mismatch")
    if bench["lifecycle"]["watchdog"]["main_pid"] != 427838 or start_ticks(427838) is None:
        raise RuntimeError("watchdog_mismatch")
    resource = bench["resource"]
    if resource["ssh_ed25519_fingerprint"] != "SHA256:FyyWs3v7776yoRPt1Asg+jJ7hBH4lTGFmWpkfa7aOtw":
        raise RuntimeError("ssh_fingerprint_mismatch")
    if not pathlib.Path(resource["ssh_identity_path"]).is_file() or not pathlib.Path(resource["known_hosts_namespace"]).is_file():
        raise RuntimeError("ssh_identity_path_missing")
    disk = director["provider_storage"]
    if (disk["staging_disk_id"], disk["staging_disk_device_id"], disk["staging_disk_gibibytes"]) != ("computedisk-e00rwewnz08e4fgt41", "dflash-stage", 100):
        raise RuntimeError("managed_disk_binding_mismatch")
    return binding, resource


def migrate(resource: dict[str, object]) -> dict[str, object]:
    target = f"{resource['ssh_user']}@{resource['public_ipv4']}"
    command = ["ssh", "-i", str(resource["ssh_identity_path"]), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}", "-o", "ConnectTimeout=20", target, "bash", "-s"]
    remote = r'''set -euo pipefail
device=/dev/disk/by-id/virtio-dflash-stage
source=/home/glmrunner/dflash-component/r3-target/b9ea41a2887d8607f594846523f94c6cc75ac8a4-20260730T004946346350Z.part
mount=/mnt/dflash-r3-stage
stage="$mount/b9ea41a2887d8607f594846523f94c6cc75ac8a4-20260730T004946346350Z.part"
test -L "$device"
resolved=$(readlink -f "$device")
test -b "$resolved"
test "$(sudo -n blockdev --getsize64 "$resolved")" -eq 107374182400
test -d "$source"
if ! findmnt -rn -S "$resolved" >/dev/null; then
  sudo -n blkid "$resolved" >/dev/null 2>&1 && { echo disk_not_blank >&2; exit 42; } || true
  sudo -n mkfs.ext4 -F "$resolved" >/dev/null
  sudo -n install -d -m 0755 "$mount"
  sudo -n mount "$resolved" "$mount"
fi
test "$(findmnt -rn -o SOURCE --target "$mount")" = "$resolved"
sudo -n install -d -o glmrunner -g glmrunner -m 0755 "$stage"
sudo -n cp -a "$source/." "$stage/"
test "$(stat -c%s "$stage/config.json")" -eq 4621
test "$(sha256sum "$stage/config.json" | cut -d' ' -f1)" = e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1
test "$(stat -c%s "$stage/model-00001-of-00002.safetensors")" -eq 49784788364
test "$(sha256sum "$stage/model-00001-of-00002.safetensors" | cut -d' ' -f1)" = eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa
if ! findmnt -rn --target "$source" | grep -Fq " $source "; then sudo -n mount --bind "$stage" "$source"; fi
test "$(findmnt -rn -o SOURCE --target "$source")" = "$stage"
free=$(df -B1 --output=avail "$source" | tail -1 | tr -d ' ')
test "$free" -ge 32212254720
printf '{"device":"%s","stage":"%s","source":"%s","free_bytes":%s,"config_sha256":"%s","shard1_sha256":"%s","shard1_bytes":%s}\n' "$resolved" "$stage" "$source" "$free" "$(sha256sum "$stage/config.json" | cut -d' ' -f1)" "$(sha256sum "$stage/model-00001-of-00002.safetensors" | cut -d' ' -f1)" "$(stat -c%s "$stage/model-00001-of-00002.safetensors")"
'''
    result = subprocess.run(command, input=remote, text=True, capture_output=True, timeout=timeout(900), check=False)
    (ROOT / "remote-migration.stdout").write_text(result.stdout)
    (ROOT / "remote-migration.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(f"remote_migration_failed:{result.returncode}")
    return json.loads(result.stdout)


def update_status(value: dict[str, object]) -> None:
    path = PROJECT / "STATUS.json"
    status = load(path)
    prior = status.get("storage_migration_session")
    session = dict(prior) if isinstance(prior, dict) else {}
    session.update(value)
    status["storage_migration_session"] = session
    atomic(path, status)


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    try:
        binding, resource = preflight()
        update_status({"phase": "migrating", "unit": str(ROOT / "OWNER_STATE.json"), "unit_manager": "pid", "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z")})
        evidence = migrate(resource)
        terminal = {"schema_version": 1, "state": "storage_migration_complete", "created_at_utc": now().isoformat().replace("+00:00", "Z"), "binding_sha256": EXPECTED["binding"], "claim_generation": binding["claimed_at"], "repair_id": REPAIR_ID, "managed_disk_id": "computedisk-e00rwewnz08e4fgt41", "managed_disk_cleanup": "deleted automatically with the managed instance", "remote": evidence}
        terminal_path = ROOT / "STORAGE_MIGRATION_TERMINAL.json"
        atomic(terminal_path, terminal)
        patch = {"schema_version": 1, "continuation_authorized": True, "claim_generation": binding["claimed_at"], "adoption_sha256": sha256(DIAGNOSTIC), "retry_scope": "cold_stage", "packet_archive": str(PACKET), "packet_archive_sha256": EXPECTED["packet"], "storage_migration_terminal_sha256": sha256(terminal_path)}
        patch_path = ROOT / "COLD_STAGE_CONTINUATION_PATCH.json"
        atomic(patch_path, patch)
        request = subprocess.run([str(REPAIR_TOOL), "request", "--root", str(RUN), "--repair-id", REPAIR_ID, "--retry-scope", "cold_stage", "--patch-artifact", str(patch_path)], text=True, capture_output=True, timeout=timeout(60), check=False)
        (ROOT / "repair-request.stdout").write_text(request.stdout)
        (ROOT / "repair-request.stderr").write_text(request.stderr)
        if request.returncode:
            raise RuntimeError(f"repair_request_rejected:{request.stderr.strip()[-500:]}")
        until = time.monotonic() + min(90, timeout(120))
        while time.monotonic() < until:
            consumed = list(HANDSHAKE.glob("REPAIR_REQUEST.*.consumed.json"))
            if consumed:
                update_status({"phase": "request_consumed", "terminal": str(terminal_path), "request": str(consumed[0]), "unit": str(ROOT / "OWNER_STATE.json"), "unit_manager": "pid"})
                return 0
            if not (HANDSHAKE / "REPAIR_REQUEST.json").exists():
                break
            time.sleep(2)
        update_status({"phase": "request_rejected_or_unobserved", "terminal": str(terminal_path), "unit": str(ROOT / "OWNER_STATE.json"), "unit_manager": "pid"})
        return 75
    except Exception as error:
        atomic(ROOT / "STORAGE_MIGRATION_FAILURE.json", {"created_at_utc": now().isoformat().replace("+00:00", "Z"), "classification": "storage_migration_integration_defect", "error": str(error)})
        return 76


if __name__ == "__main__":
    raise SystemExit(main())
