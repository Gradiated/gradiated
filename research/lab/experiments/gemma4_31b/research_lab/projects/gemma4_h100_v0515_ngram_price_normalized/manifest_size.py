#!/usr/bin/env python3
"""Fail-closed compressed-byte accounting for the bound Docker manifest."""
from __future__ import annotations

import json
import re
from typing import Any

EXPECTED_IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ManifestError(ValueError):
    pass


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ManifestError(f"{field}:invalid_digest")
    return value


def _size(value: Any, field: str) -> int:
    # JSON strings, floats, booleans, zero, and negative values are not safe
    # compressed-byte measurements and must never be coerced.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ManifestError(f"{field}:invalid_size")
    return value


def compressed_bytes(document: Any, *, expected_ref: str = EXPECTED_IMAGE,
                     expected_manifest_digest: str | None = None) -> int:
    if not isinstance(document, dict):
        raise ManifestError("document:not_object")
    if document.get("Ref") != expected_ref:
        raise ManifestError("ref:digest_mismatch")

    descriptor = document.get("Descriptor")
    if not isinstance(descriptor, dict):
        raise ManifestError("descriptor:missing")
    manifest_digest = _digest(descriptor.get("digest"), "descriptor.digest")
    expected_ref_digest = expected_ref.rsplit("@", 1)[-1]
    if manifest_digest != expected_ref_digest:
        raise ManifestError("descriptor:digest_mismatch")
    if expected_manifest_digest is not None and manifest_digest != expected_manifest_digest:
        raise ManifestError("descriptor:digest_mismatch")

    platform = descriptor.get("platform")
    if platform is not None and platform != {"architecture": "amd64", "os": "linux"}:
        raise ManifestError("descriptor:unsupported_platform")
    if isinstance(document.get("manifests"), list):
        raise ManifestError("manifest_list:ambiguous_platform")
    manifest = document.get("OCIManifest")
    if not isinstance(manifest, dict):
        manifest = document.get("SchemaV2Manifest")
    if not isinstance(manifest, dict):
        raise ManifestError("manifest:missing")
    config = manifest.get("config")
    layers = manifest.get("layers")
    if config is None:
        config = manifest.get("Config")
    if layers is None:
        layers = manifest.get("Layers")
    if not isinstance(config, dict) or not isinstance(layers, list) or not layers:
        raise ManifestError("manifest:malformed")

    seen: dict[str, int] = {}
    total = 0
    config_digest = _digest(config.get("digest"), "config.digest")
    if config_digest in seen:
        raise ManifestError("descriptor:duplicate_digest")
    config_size = _size(config.get("size"), "config.size")
    seen[config_digest] = config_size
    total += config_size
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise ManifestError(f"layer[{index}]:malformed")
        digest = _digest(layer.get("digest"), f"layer[{index}].digest")
        layer_size = _size(layer.get("size"), f"layer[{index}].size")
        if digest in seen and seen[digest] != layer_size:
            raise ManifestError("descriptor:duplicate_digest_size_conflict")
        # OCI permits repeated content-addressed empty layers. Count each
        # ordered layer occurrence, while rejecting conflicting mutations.
        seen.setdefault(digest, layer_size)
        total += layer_size
    if total <= 0:
        raise ManifestError("total:non_positive")
    return total


def load_and_measure(path: str, **kwargs: Any) -> int:
    with open(path, encoding="utf-8") as handle:
        return compressed_bytes(json.load(handle), **kwargs)
