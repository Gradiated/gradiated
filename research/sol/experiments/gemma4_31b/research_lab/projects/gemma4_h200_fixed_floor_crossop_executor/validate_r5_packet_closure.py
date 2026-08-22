#!/usr/bin/env python3
"""Verify the R5 remote packet can be staged repeatedly without ambient bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: pathlib.Path, value: dict) -> None:
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def stage(project: pathlib.Path, packet: dict, root: pathlib.Path) -> None:
    for name, digest in packet["files"].items():
        source = project / name
        if sha256(source) != digest:
            raise RuntimeError(f"packet_member_hash:{name}")
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256(target) != digest:
            raise RuntimeError(f"staged_member_hash:{name}")


def import_chain(stage_root: pathlib.Path) -> None:
    shim = stage_root / "shim.py"
    shim.write_text("""import importlib.abc, importlib.util, sys, types
class Symbol(type):
    def __getattr__(cls, name): return Symbol(name, (), {})
class Module(types.ModuleType):
    def __getattr__(self, name):
        value = Module(self.__name__ + '.' + name) if name in {'nn'} else Symbol(name, (), {})
        setattr(self, name, value); return value
class Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    roots = ('torch', 'triton', 'transformers', 'sglang')
    def find_spec(self, name, path=None, target=None):
        return importlib.util.spec_from_loader(name, self, is_package=True) if name.split('.')[0] in self.roots else None
    def create_module(self, spec): return Module(spec.name)
    def exec_module(self, module):
        module.__path__=[]
        if module.__name__ == 'triton': module.jit=lambda fn: fn
        if module.__name__ == 'torch': module.no_grad=lambda: (lambda fn: fn)
sys.meta_path.insert(0, Finder())
sys.path[:] = [sys.argv[1]] + [p for p in sys.path if p != sys.argv[1]]
for name in ('install_fused_qkv_cache', 'fused_qkv_kv_cache', 'fixed_floor_crossop_endpoint_adapter', 'endpoint_candidate_gemma4_causal'):
    importlib.import_module(name)
print('import_chain_ok')
""")
    result = subprocess.run(
        [sys.executable, "-I", str(shim), str(stage_root)],
        text=True, capture_output=True, check=False, timeout=30,
    )
    if result.returncode or result.stdout.strip() != "import_chain_ok":
        raise RuntimeError("clean_stage_import_failed:" + result.stderr[-600:])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=pathlib.Path, required=True)
    parser.add_argument("--packet", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    project, packet_path = args.project.resolve(), args.packet.resolve()
    packet = json.loads(packet_path.read_text())
    required = {
        "endpoint_candidate_gemma4_causal.py",
        "fixed_floor_crossop_endpoint_adapter.py",
        "install_fused_qkv_cache.py",
        "fused_qkv_kv_cache.py",
    }
    missing = sorted(required - set(packet["files"]))
    if missing:
        raise RuntimeError("packet_transitive_source_missing:" + ",".join(missing))
    stages = []
    with tempfile.TemporaryDirectory(prefix="r5-packet-closure-", dir=project / "artifacts") as temporary:
        base = pathlib.Path(temporary)
        for generation in range(2):
            root = base / f"clean-stage-{generation}"
            stage(project, packet, root)
            import_chain(root)
            stages.append({"generation": generation, "member_count": len(packet["files"]), "installer_sha256": sha256(root / "install_fused_qkv_cache.py")})
    atomic(args.output, {
        "schema_version": 1,
        "classification": "r5_packet_clean_stage_closure_pass",
        "packet_sha256": sha256(packet_path),
        "required_transitive_sources": sorted(required),
        "container_pythonpath_order": ["/work/project", "/sgl-workspace/sglang/python"],
        "stages": stages,
        "claim_allowed": False,
        "ssh_allowed": False,
        "cuda_allowed": False,
        "endpoint_request_allowed": False,
    })


if __name__ == "__main__":
    main()
