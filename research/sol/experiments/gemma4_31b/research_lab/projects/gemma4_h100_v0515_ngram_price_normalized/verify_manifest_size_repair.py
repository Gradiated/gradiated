#!/usr/bin/env python3
"""Offline positive and fail-closed fixtures for manifest_size.py."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from manifest_size import EXPECTED_IMAGE, ManifestError, compressed_bytes

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "manifest-size-repair-20260725t1005z"
EXPECTED_MANIFEST_DIGEST = EXPECTED_IMAGE.rsplit("@", 1)[-1]


def fixture() -> dict:
    return {
        "Ref": EXPECTED_IMAGE,
        "Descriptor": {"digest": EXPECTED_MANIFEST_DIGEST, "size": 512},
        "SchemaV2Manifest": {
            "Config": {"digest": "sha256:" + "2" * 64, "size": 100},
            "Layers": [
                {"digest": "sha256:" + "3" * 64, "size": 200},
                {"digest": "sha256:" + "4" * 64, "size": 300},
            ],
        },
    }


def expect_fail(name: str, document: dict) -> dict:
    try:
        compressed_bytes(document, expected_manifest_digest=EXPECTED_MANIFEST_DIGEST)
    except ManifestError as error:
        return {"name": name, "pass": True, "error": str(error)}
    return {"name": name, "pass": False, "error": "accepted_invalid_fixture"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    positive = fixture()
    positive_path = OUT / "positive.json"
    positive_path.write_text(json.dumps(positive, indent=2, sort_keys=True) + "\n")
    first = compressed_bytes(positive, expected_manifest_digest=EXPECTED_MANIFEST_DIGEST)
    second = compressed_bytes(json.loads(positive_path.read_text()), expected_manifest_digest=EXPECTED_MANIFEST_DIGEST)
    negatives = []
    missing = copy.deepcopy(positive)
    del missing["SchemaV2Manifest"]["Layers"][0]["size"]
    negatives.append(expect_fail("missing_size", missing))
    malformed = copy.deepcopy(positive)
    malformed["SchemaV2Manifest"]["Layers"][0]["size"] = "200"
    negatives.append(expect_fail("malformed_numeric_size", malformed))
    duplicate = copy.deepcopy(positive)
    duplicate["SchemaV2Manifest"]["Layers"][1]["digest"] = duplicate["SchemaV2Manifest"]["Layers"][0]["digest"]
    duplicate["SchemaV2Manifest"]["Layers"][1]["size"] = 201
    negatives.append(expect_fail("duplicate_descriptor", duplicate))
    digest_mismatch = copy.deepcopy(positive)
    digest_mismatch["Ref"] = EXPECTED_IMAGE.replace("ae55a608", "be55a608")
    negatives.append(expect_fail("digest_mismatched_ref", digest_mismatch))
    schema_mismatch = copy.deepcopy(positive)
    del schema_mismatch["SchemaV2Manifest"]
    negatives.append(expect_fail("missing_schema", schema_mismatch))
    observed_path = ROOT / "artifacts" / "h100-endpoint-200g-r2-descriptor-repair-20260725t1118z" / "RAW_MANIFEST_INSPECT_VERBOSE.json"
    observed = None
    if observed_path.exists():
        observed = {
            "path": str(observed_path.relative_to(ROOT)),
            "sha256": hashlib.sha256(observed_path.read_bytes()).hexdigest(),
            "compressed_bytes": compressed_bytes(json.loads(observed_path.read_text())),
        }
    result = {
        "schema_version": 1,
        "positive": {
            "fixture": str(positive_path.relative_to(ROOT)),
            "fixture_sha256": hashlib.sha256(positive_path.read_bytes()).hexdigest(),
            "expected_manifest_digest": EXPECTED_MANIFEST_DIGEST,
            "compressed_bytes_first": first,
            "compressed_bytes_second": second,
            "deterministic": first == second,
            "sufficient_space_fixture": 4096 >= first + 1024,
        },
        "negative": negatives,
        "observed_registry_schema": observed,
    }
    result["pass"] = (
        first == 600 and result["positive"]["deterministic"]
        and result["positive"]["sufficient_space_fixture"]
        and all(item["pass"] for item in negatives)
        and (observed is None or observed["compressed_bytes"] > 0)
    )
    (OUT / "FIXTURE_RESULTS.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
