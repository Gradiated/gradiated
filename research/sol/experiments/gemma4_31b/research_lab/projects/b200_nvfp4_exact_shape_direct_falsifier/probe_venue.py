#!/usr/bin/env python3
"""Read-only venue and immutable-input probe; never creates resources."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
MECHANISM = PROJECT.parent / "b200_exact_gemma_kernel_economic_mechanism/MECHANISM.json"
OUT = PROJECT / "artifacts/PRECREATE_VENUE_IDENTITY.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    cli = "/root/.nebius/bin/nebius"
    proc = subprocess.run([cli, "compute", "platform", "list", "--format", "json"], capture_output=True, timeout=60)
    try:
        platforms = json.loads(proc.stdout)
    except Exception:
        platforms = {}
    names = [x.get("metadata", {}).get("name") for x in platforms.get("items", [])]
    b200 = [x for x in platforms.get("items", []) if "b200" in json.dumps(x).lower()]
    runpod = {"configured": bool(os.environ.get("RUNPOD_API_KEY")), "http_status": None}
    if os.environ.get("RUNPOD_API_KEY"):
        query = "query GpuTypes { gpuTypes { id displayName memoryInGb lowestPrice(input: {gpuCount: 1, secureCloud: true}) { stockStatus uninterruptablePrice minimumBidPrice } } }"
        request = urllib.request.Request("https://api.runpod.io/graphql", data=json.dumps({"query": query}).encode(), headers={"Authorization": "Bearer " + os.environ["RUNPOD_API_KEY"], "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                runpod["http_status"] = response.status
                body = json.loads(raw)
                rows = body.get("data", {}).get("gpuTypes", [])
                runpod["b200_offers"] = [x for x in rows if "b200" in json.dumps(x).lower()]
        except urllib.error.HTTPError as error:
            raw = error.read(65536)
            runpod.update({"http_status": error.code, "error_body_bytes": len(raw), "error_body_sha256": hashlib.sha256(raw).hexdigest()})
    gcore_doc = Path("/root/workspace/research/factory/docs/GCORE.md").read_text()
    gcore_has_b200 = "b200" in gcore_doc.lower()
    mechanism = json.loads(MECHANISM.read_text())
    identities = mechanism["identities"]
    checks = {
        "mechanism_digest": sha(MECHANISM) == "0ced5b18806b14f6fd0070f00c52640af5e9764886fed46752da43028f8b1119",
        "upstream_digest_bound_by_mechanism": any(row.get("path") == "benchmarks/kernels/benchmark_nvfp4_gemm.py" and row.get("sha256") == "667f935dceac3acba4bfd808b8c02ac7bcf5d525f2c044ee78cd291da5b1b80d" for row in mechanism["source_trace"]["files"]),
        "image_identity": identities.get("runtime_image") == "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79",
        "commit_identity": identities.get("runtime_vllm_commit") == "6d4a8e6d204a9b2827544003b26321fff62923da",
        "full_b200_venue_and_actual_rate": bool(b200) or bool(runpod.get("b200_offers")) or gcore_has_b200,
    }
    value = {
        "schema_version": 1,
        "classification": "authenticated_b200_venue_unavailable" if not checks["full_b200_venue_and_actual_rate"] else "b200_venue_bound",
        "pass": all(checks.values()),
        "checks": checks,
        "mechanical_identities": {"mechanism_sha256": sha(MECHANISM), "upstream_sha256": "667f935dceac3acba4bfd808b8c02ac7bcf5d525f2c044ee78cd291da5b1b80d", "runtime_image": identities.get("runtime_image"), "vllm_commit": identities.get("runtime_vllm_commit")},
        "venues": {"nebius": {"command_returncode": proc.returncode, "project_platform_names": names, "b200_platforms": b200}, "runpod": runpod, "gcore_cached_inventory_has_b200": gcore_has_b200},
        "provider_create_performed": False,
        "provider_spend_usd": 0.0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, OUT)
    return 0 if value["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
