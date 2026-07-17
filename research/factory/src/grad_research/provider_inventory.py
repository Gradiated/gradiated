from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ProviderInventoryError(ValueError):
    pass


def load_provider_inventory(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ProviderInventoryError(f"cannot read provider inventory: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ProviderInventoryError("provider inventory must use schema_version 1")
    rows = value.get("providers")
    if not isinstance(rows, list) or not rows:
        raise ProviderInventoryError("providers must be a nonempty list")

    providers: dict[str, Any] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ProviderInventoryError(f"providers[{index}] must have an id")
        provider_id = row["id"]
        if provider_id in providers:
            raise ProviderInventoryError(f"duplicate provider id: {provider_id}")
        credentials = row.get("credentials")
        if not isinstance(credentials, list):
            raise ProviderInventoryError(f"{provider_id} credentials must be a list")
        names: list[str] = []
        for credential in credentials:
            if (
                not isinstance(credential, dict)
                or set(credential) - {"env", "purpose", "required"}
                or not isinstance(credential.get("env"), str)
            ):
                raise ProviderInventoryError(f"{provider_id} credential entries may contain names, never values")
            names.append(credential["env"])
        profiling = row.get("profiling")
        if not isinstance(profiling, dict) or profiling.get("hardware_counters") not in {
            "verified",
            "restricted",
            "unverified",
        }:
            raise ProviderInventoryError(f"{provider_id} profiling status is incomplete")
        normalized = dict(row)
        normalized["credential_env_names"] = names
        required_names = [item["env"] for item in credentials if item.get("required")]
        configured_names = [name for name in names if os.environ.get(name)]
        if required_names and all(os.environ.get(name) for name in required_names):
            credential_status = "configured"
        elif not required_names and configured_names:
            credential_status = "configured"
        elif configured_names:
            credential_status = "partial"
        else:
            credential_status = "not_configured"
        normalized["credential_status"] = credential_status
        normalized.pop("credentials", None)
        providers[provider_id] = normalized

    return {
        "schema_version": 1,
        "inventory_path": str(path),
        "reviewed_at_utc": value.get("reviewed_at_utc"),
        "scope": value.get("scope"),
        "providers": providers,
    }
