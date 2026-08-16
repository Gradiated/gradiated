#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


project_dir = Path(__file__).resolve().parent
geometry_path = project_dir.parent / "exact_geometry_runtime_opportunities" / "GEOMETRY.json"
fp8_path = project_dir.parent / "fp8_l40s_fit_economic_falsifier" / "FP8_L40S_PACKET.json"
kv_path = project_dir.parent / "fp8_kv_c8_retained_arm" / "FP8_KV_ARM.json"
brief_path = project_dir / "PROJECT.md"


def load(path):
    return json.loads(path.read_text())


geometry = load(geometry_path)
fp8 = load(fp8_path)
kv = load(kv_path)
brief = brief_path.read_text()

target = geometry["identities"]["target_model"]
fp8_ids = fp8["identities"]
kv_ids = kv["identities"]
runtime = geometry["identities"]["runtime"]

expected = {
    "model": fp8_ids["model"],
    "revision": fp8_ids["revision"],
    "model_index_sha256": target["model_index_sha256"],
    "runtime_image": fp8_ids["runtime_image"],
    "runtime_amd64_manifest": fp8_ids["runtime_amd64_manifest"],
    "vllm_source_revision": fp8_ids["vllm_source_revision"],
    "workload": fp8["direct_arm"]["workload"],
}

agreements = {
    "geometry_model": target["id"] == expected["model"],
    "geometry_revision": target["revision"] == expected["revision"],
    "kv_model": kv_ids["model"] == expected["model"],
    "kv_revision": kv_ids["revision"] == expected["revision"],
    "kv_runtime_image": kv_ids["runtime_image"] == expected["runtime_image"],
    "kv_vllm_source_revision": kv_ids["vllm_source_revision"] == expected["vllm_source_revision"],
    "geometry_amd64_manifest": runtime["image_amd64_manifest_digest"]
    == expected["runtime_amd64_manifest"],
}

brief_matches = {
    key: value in brief
    for key, value in expected.items()
}

source_hashes = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (geometry_path, fp8_path, kv_path, brief_path)
}

passed = all(agreements.values()) and all(brief_matches.values())
result = {
    "schema_version": 1,
    "artifact": "director_immutable_identity_assertion",
    "evidence_type": "mechanically_extracted_local_authoritative_artifacts",
    "pass": passed,
    "expected": expected,
    "source_agreements": agreements,
    "project_brief_matches": brief_matches,
    "source_sha256": source_hashes,
}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if passed else 1)
