#!/usr/bin/env python3
"""Verify the director binding and materialize its immutable input bytes."""
import hashlib
import json
import shutil
from pathlib import Path

P = Path(__file__).resolve().parent
B = json.loads((P / "DIRECTOR_BINDING.json").read_text())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    verified = {"schema_version": 1, "binding": "DIRECTOR_BINDING.json", "inputs": {}}
    for name, entry in B["bound_inputs"].items():
        source = (P / entry["path"]).resolve()
        actual = digest(source)
        if actual != entry["sha256"]:
            raise RuntimeError(f"binding_hash_mismatch:{name}:{actual}")
        destination = (
            P / "inputs" / "evidence" / f"{name}--{source.name}"
            if name.endswith("_terminal")
            else P / "inputs" / "bound" / source.name
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and digest(destination) != actual:
            raise RuntimeError(f"local_snapshot_hash_mismatch:{destination}")
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + ".part")
            shutil.copyfile(source, temporary)
            if digest(temporary) != actual:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(f"snapshot_copy_hash_mismatch:{name}")
            temporary.replace(destination)
        verified["inputs"][name] = {"source": str(source), "snapshot": str(destination.relative_to(P)), "sha256": actual}
    sums = P / "inputs" / "bound" / "SHA256SUMS.json"
    source_sums = (P / B["bound_inputs"]["requests"]["path"]).resolve().parent / "SHA256SUMS.json"
    if source_sums.exists():
        shutil.copyfile(source_sums, sums)
        verified["inputs"]["input_manifest"] = {"snapshot": str(sums.relative_to(P)), "sha256": digest(sums)}
        for filename, expected in json.loads(sums.read_text()).items():
            source_file = source_sums.parent / filename
            snapshot_file = P / "inputs" / "bound" / filename
            if not source_file.exists() or digest(source_file) != expected:
                raise RuntimeError(f"manifest_source_mismatch:{filename}")
            if not snapshot_file.exists():
                shutil.copyfile(source_file, snapshot_file)
            if digest(snapshot_file) != expected:
                raise RuntimeError(f"manifest_snapshot_mismatch:{filename}")
    trace_source = source_sums.parent / "TRACE_PACKET.json"
    trace_snapshot = P / "inputs" / "bound" / "TRACE_PACKET.json"
    if trace_source.exists():
        shutil.copyfile(trace_source, trace_snapshot)
        verified["inputs"]["trace_packet"] = {"snapshot": str(trace_snapshot.relative_to(P)), "sha256": digest(trace_snapshot)}
    output = P / "DIRECTOR_BINDING_VERIFIED.json"
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(verified, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)

if __name__ == "__main__":
    main()
