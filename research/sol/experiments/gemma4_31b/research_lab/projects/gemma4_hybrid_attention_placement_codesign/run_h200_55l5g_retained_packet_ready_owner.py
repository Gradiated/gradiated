#!/usr/bin/env python3
"""Repair only immutable packet preparation under the retained H200 claim."""
from __future__ import annotations
import hashlib, json, shlex, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "run_h200_55l5g_retained_stock_server_owner.py"
BINDING = ROOT / "DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_PACKET_IDEMPOTENCE_REPAIR_20260729T0154Z.json"
OLD = "artifacts/h200-55l5g-endpoint-stock-health-repair-20260729t0128z"
NEW = "artifacts/h200-55l5g-endpoint-packet-idempotence-repair-20260729t0154z"

def load(path: Path) -> dict: return json.loads(path.read_text())
def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    binding = load(BINDING)
    if digest(SOURCE) != binding["mutable_repair"]["source_owner_sha256"]: raise RuntimeError("packet_repair_source_hash_mismatch")
    source = SOURCE.read_text().replace(OLD, NEW).replace("sudo -n docker exec hybrid-55l5g python3 -c", "sudo -n docker exec -w /work hybrid-55l5g python3 -c")
    namespace = {"__name__": "_packet_repair_base", "__file__": str(SOURCE)}
    exec(compile(source, str(SOURCE), "exec"), namespace)
    original_call = namespace["call"]
    artifact = ROOT / NEW
    def packet_call(command: list[str], timeout: float):
        if not (len(command) >= 3 and command[0] == "/usr/bin/scp"):
            return original_call(command, timeout)
        local, remote = Path(command[-2]), command[-1]
        if not remote.startswith("glmrunner@") or ":" not in remote: return original_call(command, timeout)
        host, destination = remote.split(":", 1)
        options = command[1:-2]
        inspect = ["/usr/bin/ssh", *options, host, f"if [ -e {shlex.quote(destination)} ]; then sha256sum {shlex.quote(destination)}; else echo MISSING; fi"]
        observed = original_call(inspect, 60)
        expected = digest(local); text = observed.stdout.strip(); present = text != "MISSING" and observed.returncode == 0
        remote_hash = text.split()[0] if present and text.split() else None
        evidence = {"local":str(local), "destination":destination, "expected_sha256":expected, "observed_sha256":remote_hash, "inspect_returncode":observed.returncode, "inspect_stderr":observed.stderr[-2000:]}
        if present:
            evidence["action"] = "reuse_exact" if remote_hash == expected else "fail_mismatch"
            namespace["atomic"](artifact / "PACKET_PREPARATION.json", evidence)
            return subprocess.CompletedProcess(command, 0 if remote_hash == expected else 2, observed.stdout, observed.stderr)
        temporary = destination + ".part." + expected[:16]
        copied = original_call([*command[:-1], host + ":" + temporary], timeout)
        if copied.returncode:
            evidence.update({"action":"copy_failed", "copy_stderr":copied.stderr[-2000:]}); namespace["atomic"](artifact / "PACKET_PREPARATION.json", evidence); return copied
        verified = original_call(["/usr/bin/ssh", *options, host, f"test $(sha256sum {shlex.quote(temporary)} | awk '{{print $1}}') = {expected} && mv {shlex.quote(temporary)} {shlex.quote(destination)}"], 60)
        evidence.update({"action":"copy_atomic_finalize", "copy_returncode":copied.returncode, "verify_returncode":verified.returncode, "verify_stderr":verified.stderr[-2000:]})
        namespace["atomic"](artifact / "PACKET_PREPARATION.json", evidence)
        return verified
    namespace["call"] = packet_call
    sys.argv = [str(SOURCE)]
    return namespace["main"]()

if __name__ == "__main__": raise SystemExit(main())
