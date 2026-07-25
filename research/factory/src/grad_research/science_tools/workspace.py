from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..util import content_hash, utc_now
from .common import ScienceToolError, artifact_identity, load_json, write_json_atomic


MANIFEST_NAME = "WORKSPACE.json"
ENV_NAME = "workspace.env"
IDENTITY_FIELDS = (
    "hardware_identity",
    "runtime_identity",
    "checkpoint_identity",
    "source_identity",
    "image_identity",
)
CACHE_LAYOUT = {
    "huggingface": "cache/huggingface",
    "triton": "cache/triton",
    "cute": "cache/cute",
    "torch": "cache/torch",
    "torch_extensions": "cache/torch-extensions",
    "sccache": "cache/sccache",
}
SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "bearer",
    "cookie",
    "password",
    "private_key",
    "secret",
    "token",
}


def _require_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScienceToolError(f"{name} must be a JSON object")
    return dict(value)


def _reject_secrets(value: Any, path: str = "metadata") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ScienceToolError(f"{path} keys must be strings")
            lowered = key.lower().replace("-", "_")
            sensitive = lowered in SENSITIVE_KEYS or lowered.endswith(
                ("_api_key", "_password", "_private_key", "_secret", "_token")
            )
            if sensitive:
                raise ScienceToolError(f"{path}.{key} looks secret-bearing")
            _reject_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.strip().lower()
        if (
            lowered.startswith(("bearer ", "basic ", "sk-", "ghp_", "github_pat_"))
            or "-----begin private key-----" in lowered
            or re.fullmatch(
                r"eyj[a-z0-9_-]*=*\.[a-z0-9_-]+=*\.[a-z0-9_-]+=*",
                lowered,
            )
        ):
            raise ScienceToolError(f"{path} looks secret-bearing")


def _workspace(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _manifest_path(root: Path) -> Path:
    return root / MANIFEST_NAME


def _load_manifest(root: Path) -> dict[str, Any]:
    path = _manifest_path(root)
    if not path.is_file():
        raise ScienceToolError(f"workspace is not initialized: {root}")
    manifest = _require_mapping("workspace manifest", load_json(path))
    if manifest.get("schema_version") != 1:
        raise ScienceToolError(f"unsupported workspace manifest: {path}")
    return manifest


def _cache_paths(root: Path) -> dict[str, str]:
    return {
        name: str((root / relative).resolve())
        for name, relative in CACHE_LAYOUT.items()
    }


def _environment(cache_paths: Mapping[str, str]) -> dict[str, str]:
    huggingface = Path(cache_paths["huggingface"])
    return {
        "CUTE_DSL_CACHE_DIR": cache_paths["cute"],
        "HF_HOME": str(huggingface),
        "HF_HUB_CACHE": str(huggingface / "hub"),
        "SCCACHE_DIR": cache_paths["sccache"],
        "TORCH_EXTENSIONS_DIR": cache_paths["torch_extensions"],
        "TORCH_HOME": cache_paths["torch"],
        "TRITON_CACHE_DIR": cache_paths["triton"],
    }


def _write_env(path: Path, environment: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}."
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("# Generated cache paths only; no credentials.\n")
            for key in sorted(environment):
                handle.write(f"export {key}={shlex.quote(environment[key])}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(tag, str) or not tag for tag in value
    ):
        raise ScienceToolError("compatible_tags must be a string list")
    return sorted(set(value))


def _metadata(path: str | None) -> dict[str, Any]:
    if path is None:
        return {}
    value = _require_mapping("metadata", load_json(path))
    _reject_secrets(value)
    allowed = set(IDENTITY_FIELDS) | {"compatible_tags", "claim"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ScienceToolError(f"unknown workspace metadata: {', '.join(unknown)}")
    return value


def initialize(root_value: str | Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    _reject_secrets(metadata)
    root = _workspace(root_value)
    root.mkdir(parents=True, exist_ok=True)
    cache_paths = _cache_paths(root)
    for path in cache_paths.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    now = utc_now()
    path = _manifest_path(root)
    if path.is_file():
        manifest = _load_manifest(root)
    else:
        manifest = {
            "schema_version": 1,
            "workspace": str(root),
            "created_at": now,
            "resident_contents": [],
            "resident_contents_sha256": content_hash([]),
            "compatible_tags": [],
            "claim": None,
        }
        for field in IDENTITY_FIELDS:
            manifest[field] = None
    for field in IDENTITY_FIELDS:
        if field in metadata:
            manifest[field] = metadata[field]
    if "compatible_tags" in metadata:
        manifest["compatible_tags"] = _tags(metadata["compatible_tags"])
    if "claim" in metadata:
        manifest["claim"] = metadata["claim"]
    manifest["cache_paths"] = cache_paths
    manifest["env_file"] = str((root / ENV_NAME).resolve())
    manifest["last_used_at"] = now
    write_json_atomic(path, manifest)
    _write_env(root / ENV_NAME, _environment(cache_paths))
    return manifest


def _resident_identity(path: Path) -> dict[str, Any]:
    if path.is_file():
        return {"kind": "file", **artifact_identity(path)}
    if not path.is_dir():
        raise ScienceToolError(f"resident path is absent: {path}")
    files = []
    for member in sorted(path.rglob("*")):
        if member.is_file() and not member.is_symlink():
            identity = artifact_identity(member)
            files.append(
                {
                    "path": member.relative_to(path).as_posix(),
                    "sha256": identity["sha256"],
                    "size_bytes": identity["size_bytes"],
                }
            )
    return {
        "kind": "directory",
        "path": str(path),
        "sha256": content_hash(files),
        "file_count": len(files),
        "size_bytes": sum(item["size_bytes"] for item in files),
    }


def record(
    root_value: str | Path,
    metadata: Mapping[str, Any],
    residents: Sequence[str],
    *,
    clear_claim: bool = False,
) -> dict[str, Any]:
    _reject_secrets(metadata)
    root = _workspace(root_value)
    manifest = _load_manifest(root)
    for field in IDENTITY_FIELDS:
        if field in metadata:
            manifest[field] = metadata[field]
    if "compatible_tags" in metadata:
        manifest["compatible_tags"] = _tags(metadata["compatible_tags"])
    if "claim" in metadata:
        manifest["claim"] = metadata["claim"]
    if clear_claim:
        manifest["claim"] = None
    if residents:
        identities = []
        for value in residents:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = root / path
            identities.append(_resident_identity(path.resolve()))
        manifest["resident_contents"] = identities
        manifest["resident_contents_sha256"] = content_hash(identities)
    manifest["last_used_at"] = utc_now()
    write_json_atomic(_manifest_path(root), manifest)
    return manifest


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for member in path.rglob("*"):
            if member.is_file() and not member.is_symlink():
                total += member.stat().st_size
    except OSError:
        return -1
    return total


def status(root_value: str | Path, probes: Sequence[str]) -> dict[str, Any]:
    root = _workspace(root_value)
    manifest = _load_manifest(root)
    cache_status = {
        name: {
            "path": path,
            "exists": Path(path).is_dir(),
            "size_bytes": _directory_size(Path(path)) if Path(path).is_dir() else 0,
        }
        for name, path in manifest.get("cache_paths", {}).items()
    }
    command_status = {
        command: {
            "available": shutil.which(command) is not None,
            "path": shutil.which(command),
        }
        for command in probes
    }
    manifest["last_used_at"] = utc_now()
    write_json_atomic(_manifest_path(root), manifest)
    return {
        "schema_version": 1,
        "workspace": str(root),
        "manifest": manifest,
        "caches": cache_status,
        "commands": command_status,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="lab-workspace",
        description="Retain and inspect a warm research workspace."
    )
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--workspace", required=True)
    init.add_argument(
        "--metadata",
        help="JSON file with identity fields, compatible_tags, and/or claim",
    )
    show = commands.add_parser("status")
    show.add_argument("--workspace", required=True)
    show.add_argument("--probe", action="append", default=[])
    update = commands.add_parser("record")
    update.add_argument("--workspace", required=True)
    update.add_argument(
        "--metadata",
        help="JSON file with identity fields, compatible_tags, and/or claim",
    )
    update.add_argument("--resident", action="append", default=[])
    update.add_argument("--clear-claim", action="store_true")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.workspace, _metadata(args.metadata))
        elif args.command == "record":
            result = record(
                args.workspace,
                _metadata(args.metadata),
                args.resident,
                clear_claim=args.clear_claim,
            )
        else:
            result = status(args.workspace, args.probe)
    except (OSError, ScienceToolError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
