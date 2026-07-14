from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .records import EVIDENCE_CLASSES
from .telemetry import (
    CAPTURE_TIERS,
    TELEMETRY_CATEGORIES,
    required_artifact_roles,
    validate_telemetry_contract,
    validate_telemetry_summary,
)
from .util import (
    ValidationError,
    canonical_json_bytes,
    content_hash,
    file_hash,
    require_id,
    require_sha256,
    require_text,
    safe_relative_path,
)


class ArtifactIntegrityError(RuntimeError):
    """A content-addressed artifact or bundle no longer matches its identity."""


class ArtifactStore:
    def __init__(self, root: str | Path, program_id: str):
        self.root = Path(root)
        self.program_id = require_id("program_id", program_id)
        self.artifact_dir = self.root / "programs" / self.program_id / "artifacts"
        self.objects_dir = self.artifact_dir / "objects"
        self.entries_dir = self.artifact_dir / "entries"
        self.bundles_dir = self.artifact_dir / "bundles"
        for path in (self.objects_dir, self.entries_dir, self.bundles_dir):
            path.mkdir(parents=True, exist_ok=True)

    def object_path(self, sha256: str) -> Path:
        require_sha256("artifact sha256", sha256)
        return self.objects_dir / sha256[:2] / sha256

    def has_reference(self, sha256: str) -> bool:
        return self.object_path(sha256).is_file()

    def _commit_temp(self, temporary: Path, sha256: str) -> Path:
        destination = self.object_path(sha256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            temporary_size = temporary.stat().st_size
            temporary.unlink(missing_ok=True)
            if destination.stat().st_size == 0 or destination.stat().st_size != temporary_size:
                raise ArtifactIntegrityError(f"existing artifact {sha256} is corrupt")
            return destination
        os.replace(temporary, destination)
        destination.chmod(0o444)
        return destination

    def put_bytes(self, data: bytes) -> str:
        if not isinstance(data, bytes) or not data:
            raise ValidationError("artifact bytes must be nonempty")
        sha256 = hashlib.sha256(data).hexdigest()
        destination = self.object_path(sha256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.stat().st_size != len(data) or file_hash(destination) != sha256:
                raise ArtifactIntegrityError(f"existing artifact {sha256} is corrupt")
            return sha256
        handle = tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".artifact-", delete=False)
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            self._commit_temp(temporary, sha256)
        finally:
            temporary.unlink(missing_ok=True)
        return sha256

    def put_json(self, value: Any) -> str:
        return self.put_bytes(canonical_json_bytes(value))

    def put_file(self, source: str | Path) -> str:
        source = Path(source)
        if not source.is_file() or source.stat().st_size == 0:
            raise ValidationError(f"artifact source is absent or empty: {source}")
        digest = hashlib.sha256()
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(dir=self.objects_dir, prefix=".artifact-", delete=False)
        temporary = Path(handle.name)
        try:
            with source.open("rb") as input_handle, handle:
                while chunk := input_handle.read(1024 * 1024):
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            sha256 = digest.hexdigest()
            self._commit_temp(temporary, sha256)
            return sha256
        finally:
            temporary.unlink(missing_ok=True)

    def _register_entry(
        self,
        bundle_id: str,
        *,
        sha256: str,
        role: str,
        source_name: str,
        media_type: str,
        evidence_class: str,
        producer: str,
        telemetry_categories: Iterable[str],
        capture_tiers: Iterable[str],
    ) -> dict[str, Any]:
        require_id("bundle_id", bundle_id)
        require_sha256("artifact sha256", sha256)
        require_id("artifact role", role)
        require_text("artifact source_name", source_name)
        require_text("artifact media_type", media_type)
        require_text("artifact producer", producer)
        if evidence_class not in EVIDENCE_CLASSES:
            raise ValidationError("artifact evidence_class is unsupported")
        categories = sorted(set(telemetry_categories))
        tiers = sorted(set(capture_tiers))
        invalid_categories = sorted(set(categories) - TELEMETRY_CATEGORIES)
        invalid_tiers = sorted(set(tiers) - CAPTURE_TIERS)
        if invalid_categories:
            raise ValidationError("artifact has unsupported telemetry categories: " + ", ".join(invalid_categories))
        if invalid_tiers:
            raise ValidationError("artifact has unsupported capture tiers: " + ", ".join(invalid_tiers))
        object_path = self.object_path(sha256)
        if not object_path.is_file():
            raise ArtifactIntegrityError(f"artifact object {sha256} is absent")
        entry = {
            "schema_version": 1,
            "sha256": sha256,
            "size_bytes": object_path.stat().st_size,
            "role": role,
            "source_name": source_name,
            "media_type": media_type,
            "evidence_class": evidence_class,
            "producer": producer,
            "telemetry_categories": categories,
            "capture_tiers": tiers,
        }
        directory = self.entries_dir / bundle_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{role}--{sha256}.json"
        encoded = canonical_json_bytes(entry) + b"\n"
        if path.exists():
            if path.read_bytes() != encoded:
                raise ArtifactIntegrityError(f"artifact entry {path.name} changed identity")
        else:
            temporary = path.with_suffix(".json.tmp")
            temporary.write_bytes(encoded)
            os.replace(temporary, path)
        return entry

    def capture_file(
        self,
        bundle_id: str,
        source: str | Path,
        *,
        role: str,
        media_type: str,
        evidence_class: str,
        producer: str,
        telemetry_categories: Iterable[str] = (),
        capture_tiers: Iterable[str] = (),
    ) -> dict[str, Any]:
        source = Path(source)
        sha256 = self.put_file(source)
        return self._register_entry(
            bundle_id,
            sha256=sha256,
            role=role,
            source_name=source.name,
            media_type=media_type,
            evidence_class=evidence_class,
            producer=producer,
            telemetry_categories=telemetry_categories,
            capture_tiers=capture_tiers,
        )

    def capture_bytes(
        self,
        bundle_id: str,
        data: bytes,
        *,
        role: str,
        source_name: str,
        media_type: str,
        evidence_class: str,
        producer: str,
        telemetry_categories: Iterable[str] = (),
        capture_tiers: Iterable[str] = (),
    ) -> dict[str, Any]:
        sha256 = self.put_bytes(data)
        return self._register_entry(
            bundle_id,
            sha256=sha256,
            role=role,
            source_name=source_name,
            media_type=media_type,
            evidence_class=evidence_class,
            producer=producer,
            telemetry_categories=telemetry_categories,
            capture_tiers=capture_tiers,
        )

    def _entries(self, bundle_id: str) -> list[dict[str, Any]]:
        require_id("bundle_id", bundle_id)
        directory = self.entries_dir / bundle_id
        if not directory.is_dir():
            return []
        return [json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))]

    def finalize_bundle(
        self,
        bundle_id: str,
        *,
        kind: str,
        required_roles: Iterable[str],
        telemetry_contract_sha256: str | None = None,
    ) -> dict[str, Any]:
        require_id("bundle_id", bundle_id)
        require_id("bundle kind", kind)
        roles = sorted({require_id("required artifact role", role) for role in required_roles})
        if not roles:
            raise ValidationError("artifact bundle requires at least one role")
        if telemetry_contract_sha256 is not None:
            require_sha256("telemetry_contract_sha256", telemetry_contract_sha256)
        entries = self._entries(bundle_id)
        present_roles = {entry["role"] for entry in entries}
        missing = sorted(set(roles) - present_roles)
        if missing:
            raise ValidationError("artifact bundle is missing required roles: " + ", ".join(missing))
        if kind in {"run", "run_failure"}:
            role_counts: dict[str, int] = {}
            for entry in entries:
                role_counts[entry["role"]] = role_counts.get(entry["role"], 0) + 1
            duplicates = sorted(role for role, count in role_counts.items() if count != 1)
            if duplicates:
                raise ValidationError(
                    "run artifact bundle requires exactly one object per role: " + ", ".join(duplicates)
                )
        for entry in entries:
            path = self.object_path(entry["sha256"])
            if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
                raise ArtifactIntegrityError(f"artifact object {entry['sha256']} is absent or changed")
        manifest = {
            "schema_version": 1,
            "program_id": self.program_id,
            "bundle_id": bundle_id,
            "kind": kind,
            "telemetry_contract_sha256": telemetry_contract_sha256,
            "required_roles": roles,
            "entries": entries,
        }
        encoded = canonical_json_bytes(manifest)
        manifest_sha256 = self.put_bytes(encoded)
        alias = self.bundles_dir / f"{bundle_id}.json"
        alias_bytes = encoded + b"\n"
        if alias.exists() and alias.read_bytes() != alias_bytes:
            raise ArtifactIntegrityError(f"finalized bundle {bundle_id} cannot be mutated")
        if not alias.exists():
            temporary = alias.with_suffix(".json.tmp")
            temporary.write_bytes(alias_bytes)
            os.replace(temporary, alias)
        return {
            "manifest_sha256": manifest_sha256,
            "manifest": manifest,
            "path": alias,
        }

    def verify_reference(self, sha256: str, *, deep: bool = False) -> Path:
        path = self.object_path(sha256)
        if not path.is_file() or path.stat().st_size == 0:
            raise ArtifactIntegrityError(f"artifact reference {sha256} is absent")
        if deep and file_hash(path) != sha256:
            raise ArtifactIntegrityError(f"artifact reference {sha256} failed its hash")
        return path

    def load_json_reference(self, sha256: str) -> Any:
        path = self.verify_reference(sha256)
        try:
            return json.loads(path.read_text())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArtifactIntegrityError(f"artifact reference {sha256} is not JSON") from error

    def verify_bundle(self, manifest_sha256: str, *, deep: bool = False) -> dict[str, Any]:
        manifest_path = self.verify_reference(manifest_sha256, deep=True)
        try:
            manifest = json.loads(manifest_path.read_text())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArtifactIntegrityError("artifact bundle manifest is not JSON") from error
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise ArtifactIntegrityError("artifact bundle manifest is malformed")
        if manifest.get("program_id") != self.program_id:
            raise ArtifactIntegrityError("artifact bundle belongs to another program")
        for entry in manifest.get("entries", []):
            path = self.verify_reference(entry["sha256"], deep=deep)
            if path.stat().st_size != entry.get("size_bytes"):
                raise ArtifactIntegrityError(f"artifact object {entry['sha256']} changed size")
        present_roles = {entry["role"] for entry in manifest.get("entries", [])}
        missing = sorted(set(manifest.get("required_roles", [])) - present_roles)
        if missing:
            raise ArtifactIntegrityError("artifact bundle lost required roles: " + ", ".join(missing))
        return manifest


def _artifact_role_metadata(contract: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    metadata: dict[str, dict[str, set[str]]] = {}
    for signal in contract["signals"]:
        if signal["status"] != "capture":
            continue
        row = metadata.setdefault(signal["artifact_role"], {"categories": set(), "tiers": set()})
        row["categories"].add(signal["category"])
        row["tiers"].add(signal["tier"])
    return metadata


def package_run_directory(
    store: ArtifactStore,
    spec: dict[str, Any],
    spec_path: str | Path,
    run_directory: str | Path,
    *,
    producer: str = "grad-research",
    failure_class: str | None = None,
) -> dict[str, Any]:
    run_id = require_id("paid run.run_id", spec.get("run_id"))
    spec_path = Path(spec_path)
    try:
        stored_spec = json.loads(spec_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError("paid run spec path is absent or invalid JSON") from error
    if stored_spec != spec:
        raise ValidationError("in-memory paid run spec differs from the stored spec file")
    contract = spec.get("telemetry_contract")
    report = validate_telemetry_contract(contract)
    artifact_contract = spec.get("artifact_contract")
    if not isinstance(artifact_contract, dict):
        raise ValidationError("paid run.artifact_contract must be an object")
    required = artifact_contract.get("required")
    if not isinstance(required, list) or not required:
        raise ValidationError("paid run.artifact_contract.required must be a nonempty list")
    role_metadata = _artifact_role_metadata(contract)
    if failure_class is not None:
        require_id("failure_class", failure_class)
        failure_roles = {"identities", "telemetry_summary", "cost", "logs"}
        required = [item for item in required if item.get("role") in failure_roles]
        required.append(
            {"role": "failure_summary", "path": "failure.json", "media_type": "application/json"}
        )
    bundle_alias = store.bundles_dir / f"{run_id}.json"
    if not bundle_alias.exists():
        shutil.rmtree(store.entries_dir / run_id, ignore_errors=True)
    run_directory = Path(run_directory)
    declared_paths = []
    for index, item in enumerate(required):
        if not isinstance(item, dict) or not {"role", "path", "media_type"} <= set(item):
            raise ValidationError(
                f"paid run.artifact_contract.required[{index}] must contain role, path, and media_type"
            )
        relative = safe_relative_path(f"paid run.artifact_contract.required[{index}].path", item["path"])
        source = run_directory / relative
        if not source.is_file() or source.stat().st_size == 0:
            raise ValidationError(f"artifact source is absent or empty: {source}")
        declared_paths.append(source)
    total_bytes = spec_path.stat().st_size + sum(path.stat().st_size for path in declared_paths)
    if total_bytes > contract["collection_budget"]["max_artifact_bytes"]:
        raise ValidationError("run artifacts exceed the preregistered collection budget")
    store.capture_file(
        run_id,
        spec_path,
        role="run_spec",
        media_type="application/json",
        evidence_class="measured",
        producer=producer,
        telemetry_categories=["provenance"],
        capture_tiers=["always_on"],
    )
    roles: set[str] = {"run_spec"}
    telemetry_summary: dict[str, Any] | None = None
    for index, item in enumerate(required):
        if not isinstance(item, dict) or not {"role", "path", "media_type"} <= set(item):
            raise ValidationError(
                f"paid run.artifact_contract.required[{index}] must contain role, path, and media_type"
            )
        role = require_id(f"paid run.artifact_contract.required[{index}].role", item["role"])
        relative = safe_relative_path(f"paid run.artifact_contract.required[{index}].path", item["path"])
        media_type = require_text(
            f"paid run.artifact_contract.required[{index}].media_type", item["media_type"]
        )
        source = run_directory / relative
        metadata = role_metadata.get(role, {"categories": set(), "tiers": set()})
        entry = store.capture_file(
            run_id,
            source,
            role=role,
            media_type=media_type,
            evidence_class="measured",
            producer=producer,
            telemetry_categories=metadata["categories"],
            capture_tiers=metadata["tiers"],
        )
        roles.add(role)
        if role == "telemetry_summary" and failure_class is None:
            telemetry_summary = validate_telemetry_summary(store.load_json_reference(entry["sha256"]), contract)
    expected_roles = (
        {"run_spec", "identities", "telemetry_summary", "cost", "logs", "failure_summary"}
        if failure_class is not None
        else required_artifact_roles(contract)
    )
    if roles != expected_roles:
        missing = sorted(expected_roles - roles)
        extra = sorted(roles - expected_roles)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unregistered " + ", ".join(extra))
        raise ValidationError("artifact role contract mismatch: " + "; ".join(details))
    if telemetry_summary is None and failure_class is None:
        raise ValidationError("run artifacts do not include a telemetry summary")
    draft_manifest = {
        "schema_version": 1,
        "program_id": store.program_id,
        "bundle_id": run_id,
        "kind": "run_failure" if failure_class is not None else "run",
        "telemetry_contract_sha256": report["contract_sha256"],
        "required_roles": sorted(expected_roles),
        "entries": store._entries(run_id),
    }
    from .evidence import validate_failure_evidence, validate_run_evidence

    derived_evidence = (
        validate_failure_evidence(store, draft_manifest, spec, failure_class=failure_class)
        if failure_class is not None
        else validate_run_evidence(store, draft_manifest, spec)
    )
    finalized = store.finalize_bundle(
        run_id,
        kind=draft_manifest["kind"],
        required_roles=expected_roles,
        telemetry_contract_sha256=report["contract_sha256"],
    )
    return {
        "run_id": run_id,
        "manifest_sha256": finalized["manifest_sha256"],
        "manifest_path": str(finalized["path"]),
        "telemetry_summary": telemetry_summary,
        "derived_evidence": derived_evidence,
    }
