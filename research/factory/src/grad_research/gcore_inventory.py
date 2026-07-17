"""Read-only Gcore GPU bare-metal inventory discovery.

The snapshot is deliberately Markdown so researchers can inspect current
capacity and pricing without learning another data format.  A compact JSON
record in an HTML comment makes the same file safe to refresh programmatically
without storing credentials or private-key material.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GcoreInventoryError(ValueError):
    """Raised when Gcore inventory cannot be read or refreshed."""


GCORE_API_BASE = "https://api.gcore.com"
INVENTORY_SCHEMA_VERSION = 1
REFRESH_INTERVAL = timedelta(days=1)
_META_RE = re.compile(r"<!-- gcore-inventory-meta:\s*(\{.*?\})\s*-->", re.DOTALL)
_LIVE_START = "<!-- gcore-inventory-start -->"
_LIVE_END = "<!-- gcore-inventory-end -->"

RequestJson = Callable[[str, str, dict[str, Any] | None], Any]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise GcoreInventoryError("Gcore inventory timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GcoreInventoryError("Gcore inventory timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise GcoreInventoryError("Gcore inventory timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _request_json(api_key: str, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, method=method)
    request.add_header("Authorization", f"APIKey {api_key}")
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except HTTPError as error:
        raise GcoreInventoryError(f"Gcore API returned HTTP {error.code} for {method} {url}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise GcoreInventoryError(f"Gcore API request failed for {method} {url}: {error}") from error


def _items(value: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in keys:
            rows = value.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    return []


def _redact(value: Any, *, parent_key: str = "") -> Any:
    """Keep useful catalog fields while excluding secret- or host-specific data."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(word in normalized for word in ("token", "password", "secret", "private_key", "user_data")):
                continue
            if normalized in {"credentials", "interfaces", "addresses", "ip_addresses"}:
                continue
            result[str(key)] = _redact(item, parent_key=normalized)
        return result
    if isinstance(value, list):
        return [_redact(item, parent_key=parent_key) for item in value]
    return value


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def _path(project_id: str, region_id: str, suffix: str) -> str:
    return (
        f"{GCORE_API_BASE}/cloud/v3/gpu/baremetal/"
        f"{quote(str(project_id), safe='')}/{quote(str(region_id), safe='')}/{suffix}"
    )


def fetch_gcore_inventory(
    *,
    api_key: str,
    project_id: str,
    region_id: str | None = None,
    now: datetime | None = None,
    request_json: RequestJson | None = None,
) -> dict[str, Any]:
    """Fetch Gcore regions and read-only GPU bare-metal catalog state."""
    if not api_key:
        raise GcoreInventoryError("GCORE_API_KEY is not set")
    if not project_id:
        raise GcoreInventoryError("GCORE_PROJECT_ID is not set")
    request = request_json or (lambda method, url, payload=None: _request_json(api_key, method, url, payload))
    retrieved_at = _timestamp(now or _utc_now())

    raw_regions = request("GET", f"{GCORE_API_BASE}/cloud/v1/ai/regions", None)
    regions = _items(raw_regions, "regions", "items", "results")
    if not regions:
        raise GcoreInventoryError("Gcore returned no GPU regions")

    selected: list[dict[str, Any]] = []
    for raw_region in regions:
        current_id = _value(raw_region, "id", "region_id")
        if current_id is None or not raw_region.get("has_baremetal", False):
            continue
        if region_id and str(current_id) != str(region_id):
            continue
        selected.append(raw_region)
    if region_id and not selected:
        raise GcoreInventoryError(f"GCORE_REGION_ID={region_id} is not a GPU bare-metal region")

    result_regions: list[dict[str, Any]] = []
    for raw_region in selected:
        current_id = str(_value(raw_region, "id", "region_id"))
        row: dict[str, Any] = {
            "id": _value(raw_region, "id", "region_id"),
            "name": _value(raw_region, "display_name", "name") or current_id,
            "country": raw_region.get("country"),
            "has_baremetal": True,
            "flavors": [],
            "images": [],
            "clusters": [],
            "errors": [],
        }

        try:
            flavors_payload = request(
                "GET",
                f"{_path(project_id, current_id, 'flavors')}?include_capacity=true&include_prices=true",
                None,
            )
            row["flavors"] = [_redact(item) for item in _items(flavors_payload, "flavors", "items", "results")]
        except GcoreInventoryError as error:
            row["errors"].append({"source": "flavors", "message": str(error)})

        try:
            images_payload = request("GET", _path(project_id, current_id, "images"), None)
            row["images"] = [_redact(item) for item in _items(images_payload, "images", "items", "results")]
        except GcoreInventoryError as error:
            row["errors"].append({"source": "images", "message": str(error)})

        try:
            clusters_payload = request(
                "GET",
                f"{_path(project_id, current_id, 'clusters')}?managed_by=user",
                None,
            )
            row["clusters"] = [_redact(item) for item in _items(clusters_payload, "clusters", "items", "results")]
        except GcoreInventoryError as error:
            row["errors"].append({"source": "clusters", "message": str(error)})

        available_flavor = next(
            (
                item
                for item in row["flavors"]
                if not item.get("disabled") and (_value(item, "flavor_id", "id", "name") is not None)
            ),
            None,
        )
        if available_flavor:
            flavor = _value(available_flavor, "flavor_id", "id", "name")
            try:
                row["quota_check"] = _redact(
                    request(
                        "POST",
                        _path(project_id, current_id, "check_limits"),
                        {
                            "flavor": flavor,
                            "servers_count": 1,
                            "existing_cluster": False,
                            "servers_settings": {
                                "interfaces": [{"type": "external", "ip_family": "ipv4"}]
                            },
                        },
                    )
                )
            except GcoreInventoryError as error:
                row["errors"].append({"source": "quota", "message": str(error)})

        result_regions.append(row)

    if not result_regions:
        raise GcoreInventoryError("Gcore returned no matching GPU bare-metal regions")
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "provider": "gcore",
        "project_id": str(project_id),
        "retrieved_at_utc": retrieved_at,
        "refresh_interval_hours": int(REFRESH_INTERVAL.total_seconds() // 3600),
        "regions": result_regions,
    }


def _read_cache(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text()
    except OSError as error:
        raise GcoreInventoryError(f"cannot read Gcore Markdown inventory: {error}") from error
    match = _META_RE.search(content)
    if not match:
        raise GcoreInventoryError(f"Gcore Markdown inventory has no machine-readable metadata: {path}")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise GcoreInventoryError(f"Gcore Markdown inventory metadata is invalid: {path}") from error
    if value.get("schema_version") != INVENTORY_SCHEMA_VERSION or value.get("provider") != "gcore":
        raise GcoreInventoryError(f"Gcore Markdown inventory schema is unsupported: {path}")
    _parse_timestamp(value.get("retrieved_at_utc"))
    return value


def _format(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_gcore_markdown(snapshot: dict[str, Any]) -> str:
    """Render a human-readable snapshot and preserve its data in metadata."""
    metadata = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    lines = [
        "<!-- gcore-inventory-meta: " + metadata + " -->",
        _LIVE_START,
        "# Gcore GPU bare-metal inventory",
        "",
        f"Last refreshed: **{snapshot['retrieved_at_utc']}** (automatic refresh window: 24 hours)",
        "",
        f"Project: `{_format(snapshot.get('project_id'))}`. Values below are vendor-reported catalog, capacity, pricing, and quota data; they are not a reservation guarantee.",
        "",
    ]
    for region in snapshot.get("regions", []):
        lines.extend([f"## {_format(region.get('name'))} (region `{_format(region.get('id'))}`)", ""])
        lines.extend([
            "### GPU flavors",
            "",
            "| Flavor | Capacity | Disabled | Currency | Hourly | Monthly | Hardware |",
            "| --- | ---: | :---: | :---: | ---: | ---: | --- |",
        ])
        flavors = region.get("flavors", [])
        if not flavors:
            lines.append("| — | — | — | — | — | No flavor data returned |")
        for flavor in flavors:
            price = flavor.get("price") if isinstance(flavor.get("price"), dict) else {}
            hardware = _value(flavor, "hardware_description", "gpu_description", "gpu")
            if isinstance(hardware, dict):
                hardware = hardware.get("gpu") or hardware.get("model") or json.dumps(hardware, sort_keys=True)
            lines.append(
                "| "
                + " | ".join([
                    _format(_value(flavor, "flavor_name", "name", "flavor_id", "id")),
                    _format(_value(flavor, "capacity", "available_capacity")),
                    _format(flavor.get("disabled")),
                    _format(_value(flavor, "currency_code") or _value(price, "currency_code")),
                    _format(_value(flavor, "price_per_hour", "hourly_price", "price_hourly") or _value(price, "price_per_hour")),
                    _format(_value(flavor, "price_per_month", "monthly_price", "price_monthly") or _value(price, "price_per_month")),
                    _format(hardware),
                ])
                + " |"
            )
        quota = region.get("quota_check")
        if quota is not None:
            lines.extend(["", "### Quota check (one-server read-only probe)", "", "```json", json.dumps(quota, indent=2, sort_keys=True), "```"])
        images = region.get("images", [])
        lines.extend(["", "### Images", ""])
        if images:
            lines.append("| ID | Name | Status | GPU driver |")
            lines.append("| --- | --- | --- | --- |")
            for image in images:
                lines.append(
                    "| "
                    + " | ".join([
                        _format(_value(image, "id", "image_id")),
                        _format(_value(image, "name", "display_name")),
                        _format(image.get("status")),
                        _format(_value(image, "gpu_driver", "gpu_driver_version")),
                    ])
                    + " |"
                )
        else:
            lines.append("No image data returned.")
        clusters = region.get("clusters", [])
        lines.extend(["", "### Existing user-managed clusters", ""])
        if clusters:
            lines.append("| ID | Name | Status | Flavor | Servers |")
            lines.append("| --- | --- | --- | --- | ---: |")
            for cluster in clusters:
                lines.append(
                    "| "
                    + " | ".join([
                        _format(cluster.get("id")),
                        _format(cluster.get("name")),
                        _format(cluster.get("status")),
                        _format(cluster.get("flavor")),
                        _format(cluster.get("servers_count")),
                    ])
                    + " |"
                )
        else:
            lines.append("No existing user-managed clusters returned.")
        if region.get("errors"):
            lines.extend(["", "### Refresh warnings", ""])
            for error in region["errors"]:
                lines.append(f"- `{_format(error.get('source'))}`: {_format(error.get('message'))}")
        lines.append("")
    lines.append(_LIVE_END)
    return "\n".join(lines)


def _write_markdown_cache(path: Path, snapshot: dict[str, Any]) -> None:
    rendered = render_gcore_markdown(snapshot)
    if path.exists():
        existing = path.read_text()
        if _LIVE_START in existing and _LIVE_END in existing:
            prefix, rest = existing.split(_LIVE_START, 1)
            _, suffix = rest.split(_LIVE_END, 1)
            prefix = _META_RE.sub("", prefix).rstrip()
            rendered = prefix.rstrip() + "\n\n" + rendered + suffix
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered.rstrip() + "\n")


def _report(snapshot: dict[str, Any], path: Path, *, now: datetime, refreshed: bool, refresh_error: str | None = None) -> dict[str, Any]:
    retrieved = _parse_timestamp(snapshot["retrieved_at_utc"])
    age = max(timedelta(0), now.astimezone(timezone.utc) - retrieved)
    result = dict(snapshot)
    result.update(
        {
            "inventory_path": str(path),
            "cache_age_hours": round(age.total_seconds() / 3600, 2),
            "fresh": age <= REFRESH_INTERVAL,
            "refreshed": refreshed,
        }
    )
    if refresh_error:
        result["refresh_error"] = refresh_error
    return result


def load_or_refresh_gcore_inventory(
    path: Path,
    *,
    api_key: str | None = None,
    project_id: str | None = None,
    region_id: str | None = None,
    force: bool = False,
    now: datetime | None = None,
    request_json: RequestJson | None = None,
) -> dict[str, Any]:
    """Read the Markdown snapshot, refreshing it when older than one day."""
    current_time = now or _utc_now()
    cached: dict[str, Any] | None = None
    if path.exists():
        try:
            cached = _read_cache(path)
        except GcoreInventoryError:
            # A checked-in guide can exist before its first live snapshot.
            # Refresh it in place while preserving its surrounding content.
            cached = None
        if cached is not None and not force and current_time.astimezone(timezone.utc) - _parse_timestamp(cached["retrieved_at_utc"]) <= REFRESH_INTERVAL:
            return _report(cached, path, now=current_time, refreshed=False)

    api_key = api_key if api_key is not None else os.environ.get("GCORE_API_KEY")
    project_id = project_id if project_id is not None else os.environ.get("GCORE_PROJECT_ID")
    selected_region = region_id if region_id is not None else os.environ.get("GCORE_REGION_ID") or None
    try:
        snapshot = fetch_gcore_inventory(
            api_key=api_key or "",
            project_id=project_id or "",
            region_id=selected_region,
            now=current_time,
            request_json=request_json,
        )
    except GcoreInventoryError as error:
        if cached is not None:
            return _report(cached, path, now=current_time, refreshed=False, refresh_error=str(error))
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    _write_markdown_cache(path, snapshot)
    return _report(snapshot, path, now=current_time, refreshed=True)


def load_cached_gcore_inventory(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    snapshot = _read_cache(path)
    return _report(snapshot, path, now=now or _utc_now(), refreshed=False)
