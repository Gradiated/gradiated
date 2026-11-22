"""Materialise a Vivado build from the pinned Experiment 16 DDR-only shell."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import tarfile

BASE_INPUT = "1d91850a3386d09172c053708be4b1eb39905c8b2b09e100a4e6a12a6e28838c"
BASE_FIRMWARE = "gradiated-tiny-logits-ddr4-burst-v1-50mhz"
FIRMWARE = "gradiated-tiny-logits-ddr4-prefetch-v1-50mhz"
BASE_PROGRAM = "kv260-logits-ddr4-burst-program.dtbo"
PROGRAM = "kv260-logits-ddr4-prefetch-program.dtbo"
DMA = "kv260-logits-ddr4-dma-direct"
PREFIX = "implementation/rtl/"
BUILD_TCL = "implementation/tools/autonomous-build.tcl"
CHANGED_MODULES = {"logits_group_reader", "transformer"}


def sha(data):
    return sha256(data).hexdigest()


def pins(files):
    return {name: sha(data) for name, data in files.items()}


def load_archive(path):
    data = path.read_bytes()
    if sha(data) != BASE_INPUT:
        raise ValueError("Experiment 16 input archive differs from its pin")
    with tarfile.open(fileobj=BytesIO(data)) as archive:
        files = {
            entry.name.removeprefix("./"): archive.extractfile(entry).read()
            for entry in archive.getmembers()
            if entry.isfile() and not Path(entry.name).name.startswith("._")
        }
    manifest = json.loads(files.pop("source-manifest.json"))
    if pins(files) != manifest["files"]:
        raise ValueError("Experiment 16 source closure differs from its manifest")
    return files, manifest


def module_pins(files):
    return {
        Path(name).stem: digest for name, digest in files.items()
        if name.startswith(PREFIX) and name.endswith(".sv")
    }


def load_rtl(directory):
    files = {path.stem: path.read_bytes() for path in directory.glob("*.sv")}
    if pins(files) != json.loads((directory / "source-manifest.json").read_text()):
        raise ValueError(f"Generated RTL closure differs from its manifest in {directory}")
    return files


def prepare(control_archive, control_rtl, candidate_rtl, protocol, destination):
    attempt = destination.name
    if not re.fullmatch(r"logits-ddr4-prefetch-build-[0-9]{8}T[0-9]{6}Z", attempt):
        raise ValueError("Unexpected build attempt name")
    files, base = load_archive(control_archive)
    control_modules = module_pins(base["files"])
    if len(control_modules) != 12 or pins(load_rtl(control_rtl)) != control_modules:
        raise ValueError("Generated control does not match the 12 routed Experiment 16 modules")
    rtl = load_rtl(candidate_rtl)
    if rtl.keys() != control_modules.keys():
        raise ValueError("Candidate must retain the Experiment 16 module set")
    changed = {name for name, digest in control_modules.items() if sha(rtl[name]) != digest}
    if changed != CHANGED_MODULES:
        raise ValueError(f"Unexpected changed candidate modules: {sorted(changed)}")
    tcl = files[BUILD_TCL].decode()
    for name in sorted(changed):
        old = f"    {name} {control_modules[name]}"
        if tcl.count(old) != 1:
            raise ValueError(f"Expected one module SHA anchor for {name}")
        tcl = tcl.replace(old, f"    {name} {sha(rtl[name])}")
        files[f"{PREFIX}{name}.sv"] = rtl[name]
    files[BUILD_TCL] = tcl.encode()
    old_root = base["remote_root"]
    new_root = f"{old_root.rsplit('/', 1)[0]}/{attempt}"
    for name in ("run-all.py", "run-phase.py", "convert-bit.py", "autonomous-program.dts"):
        files[name] = (files[name].decode().replace(old_root, new_root)
                       .replace(BASE_FIRMWARE, FIRMWARE).replace(BASE_PROGRAM, PROGRAM).encode())
    manifest = {
        **base,
        "remote_root": new_root,
        "files": pins(files),
        "protocol_sha256": sha(protocol.read_bytes()),
        "reused_control_input_sha256": BASE_INPUT,
        "reused_control_modules": control_modules,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    destination.mkdir()
    for name, data in {**files, "source-manifest.json": manifest_bytes}.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {"remote_root": new_root, "manifest_sha256": sha(manifest_bytes)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control_archive", "control_rtl", "candidate_rtl", "protocol", "destination"):
        parser.add_argument(name, type=Path)
    print(json.dumps(prepare(**vars(parser.parse_args()))))
