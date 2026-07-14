from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .util import (
    ValidationError,
    content_hash,
    file_hash,
    require_sha256,
    require_text,
    safe_relative_path,
)


class PreflightError(ValidationError):
    """A local identity or recorded-fixture check failed."""


def verify_identity_manifest(
    root: str | Path,
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
    require_index_closure: bool = False,
) -> dict[str, Any]:
    root = Path(root)
    manifest_path = Path(manifest_path)
    require_sha256("expected_manifest_sha256", expected_manifest_sha256)
    observed_manifest_sha256 = file_hash(manifest_path)
    if observed_manifest_sha256 != expected_manifest_sha256:
        raise PreflightError("identity manifest hash mismatch")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"identity manifest is unreadable: {error}") from error
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise PreflightError("identity manifest requires schema_version 1 and files")
    observed = []
    declared_paths: set[str] = set()
    for index, entry in enumerate(manifest["files"]):
        if not isinstance(entry, dict):
            raise PreflightError(f"manifest file {index} must be an object")
        relative = safe_relative_path(f"manifest.files[{index}].path", entry.get("path"))
        if relative in declared_paths:
            raise PreflightError(f"manifest path is duplicated: {relative}")
        declared_paths.add(relative)
        expected_sha = require_sha256(f"manifest.files[{index}].sha256", entry.get("sha256"))
        expected_size = entry.get("size_bytes")
        if type(expected_size) is not int or expected_size < 0:
            raise PreflightError(f"manifest.files[{index}].size_bytes must be nonnegative")
        path = root / relative
        if not path.is_file():
            raise PreflightError(f"manifest file is missing: {relative}")
        size = path.stat().st_size
        digest = file_hash(path)
        if size != expected_size:
            raise PreflightError(f"manifest file size mismatch: {relative}")
        if digest != expected_sha:
            raise PreflightError(f"manifest file hash mismatch: {relative}")
        observed.append({"path": relative, "size_bytes": size, "sha256": digest})

    closure = None
    index_path = manifest.get("index_path")
    if require_index_closure:
        if not index_path:
            raise PreflightError("checkpoint closure requires index_path")
        index_relative = safe_relative_path("manifest.index_path", index_path)
        if index_relative not in declared_paths:
            raise PreflightError("checkpoint index is not bound by the manifest")
        try:
            index_value = json.loads((root / index_relative).read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise PreflightError(f"checkpoint index is unreadable: {error}") from error
        weight_map = index_value.get("weight_map")
        if not isinstance(weight_map, dict) or not weight_map:
            raise PreflightError("checkpoint index requires a nonempty weight_map")
        referenced = {safe_relative_path("checkpoint shard", value) for value in weight_map.values()}
        missing = sorted(referenced - declared_paths)
        if missing:
            raise PreflightError(f"checkpoint index references unbound shards: {', '.join(missing)}")
        closure = {
            "index_path": index_relative,
            "tensor_count": len(weight_map),
            "referenced_shards": sorted(referenced),
            "referenced_shard_count": len(referenced),
        }

    report = {
        "schema_version": 1,
        "pass": True,
        "bound_sha256": expected_manifest_sha256,
        "manifest_path": str(manifest_path),
        "file_count": len(observed),
        "total_bytes": sum(row["size_bytes"] for row in observed),
        "files": observed,
        "index_closure": closure,
    }
    report["evidence_sha256"] = content_hash(report)
    return report


def verify_recorded_fixture(
    path: str | Path,
    *,
    expected_fixture_sha256: str,
    bound_sha256: str,
) -> dict[str, Any]:
    path = Path(path)
    require_sha256("expected_fixture_sha256", expected_fixture_sha256)
    require_sha256("bound_sha256", bound_sha256)
    if not path.is_file():
        raise PreflightError("recorded fixture is missing")
    observed = file_hash(path)
    if observed != expected_fixture_sha256:
        raise PreflightError("recorded fixture hash mismatch")
    report = {
        "schema_version": 1,
        "pass": True,
        "bound_sha256": bound_sha256,
        "fixture_sha256": observed,
        "fixture_path": str(path),
        "size_bytes": path.stat().st_size,
    }
    report["evidence_sha256"] = content_hash(report)
    return report
