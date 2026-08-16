#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

P = Path(__file__).resolve().parent
R = P / "stock_packet"
A = P / "artifacts" / "packet-id-repair"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    binding = json.loads((P / "DIRECTOR_STOCK_PACKET_ID_REPAIR_BINDING.json").read_text())
    if digest(P / "DIRECTOR_STOCK_PACKET_ID_REPAIR_BINDING.json") != "e99a07e25566cfd891e7c76b8be3530d67c6c0edfa646dfefa689e7c7f2ff615":
        raise RuntimeError("binding_hash")
    repair = binding["packet_repair"]
    if digest(R / "PACKET_MANIFEST.json") != repair["original_manifest_sha256"]:
        raise RuntimeError("original_manifest_hash")
    if digest(R / "PACKET_ID.json") != repair["existing_packet_id_sha256"]:
        raise RuntimeError("packet_id_hash")
    original = json.loads((R / "PACKET_MANIFEST.json").read_text())
    rows = list(original["files"])
    rows += [{"path": "PACKET_ID.json", "bytes": (R / "PACKET_ID.json").stat().st_size, "sha256": digest(R / "PACKET_ID.json")}, {"path": "PACKET_MANIFEST.json", "bytes": (R / "PACKET_MANIFEST.json").stat().st_size, "sha256": digest(R / "PACKET_MANIFEST.json")}]
    manifest = {"schema_version": 1, "purpose": "archive_manifest_includes_existing_packet_id", "files": sorted(rows, key=lambda x: x["path"])}
    A.mkdir(parents=True, exist_ok=True)
    path = R / "PACKET_ARCHIVE_MANIFEST.json"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    pack = ["/root/workspace/research/factory/tools/manifest-pack", "--root", str(R), "--manifest", str(path), "--archive", str(A / "stock_packet_complete.tar")]
    good = subprocess.run(pack, text=True, capture_output=True, check=False)
    (A / "manifest-pack.json").write_text(json.dumps({"returncode": good.returncode, "stdout": good.stdout, "stderr": good.stderr, "archive_manifest_sha256": digest(path)}, sort_keys=True, indent=2) + "\n")
    if good.returncode:
        raise RuntimeError("complete_manifest_pack")
    fixture = A / "missing-packet-id"; shutil.rmtree(fixture, ignore_errors=True); shutil.copytree(R, fixture); (fixture / "PACKET_ID.json").unlink()
    bad = subprocess.run(["python3", str(fixture / "stock_multiplex_runner.py"), "--packet-root", str(fixture), "--mode", "control", "--end", "171", "--out", str(fixture / "out")], text=True, capture_output=True, check=False)
    (A / "missing_packet_id_fixture.json").write_text(json.dumps({"returncode": bad.returncode, "stdout": bad.stdout, "stderr": bad.stderr, "fails_closed": bad.returncode != 0 and "PACKET_ID" in bad.stderr}, sort_keys=True, indent=2) + "\n")
    if bad.returncode == 0 or "PACKET_ID" not in bad.stderr:
        raise RuntimeError("missing_packet_id_fixture_did_not_fail_closed")
    print(json.dumps({"archive": str(A / "stock_packet_complete.tar"), "archive_sha256": digest(A / "stock_packet_complete.tar"), "fixture": "passed"}, sort_keys=True))


if __name__ == "__main__":
    main()
