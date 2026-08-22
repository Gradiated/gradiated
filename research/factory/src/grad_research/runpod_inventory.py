from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable


RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"
RUNPOD_INVENTORY_QUERY = """
query LiveGpuInventory {
  gpuTypes {
    id
    displayName
    memoryInGb
    s1: lowestPrice(input: {gpuCount: 1, secureCloud: true}) {
      stockStatus
      uninterruptablePrice
      minimumBidPrice
      availableGpuCounts
    }
    s2: lowestPrice(input: {gpuCount: 2, secureCloud: true}) {
      stockStatus
      uninterruptablePrice
      minimumBidPrice
      availableGpuCounts
    }
    s4: lowestPrice(input: {gpuCount: 4, secureCloud: true}) {
      stockStatus
      uninterruptablePrice
      minimumBidPrice
      availableGpuCounts
    }
    s8: lowestPrice(input: {gpuCount: 8, secureCloud: true}) {
      stockStatus
      uninterruptablePrice
      minimumBidPrice
      availableGpuCounts
    }
    c1: lowestPrice(input: {gpuCount: 1, secureCloud: false}) {
      stockStatus
      uninterruptablePrice
      minimumBidPrice
      availableGpuCounts
    }
  }
}
"""


class RunPodInventoryError(ValueError):
    pass


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _request_graphql(api_key: str, query: str) -> dict[str, Any]:
    url = RUNPOD_GRAPHQL_URL + "?" + urllib.parse.urlencode({"api_key": api_key})
    request = urllib.request.Request(
        url,
        data=json.dumps({"query": query}, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "grad-research-inventory/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise RunPodInventoryError(
            f"RunPod inventory request failed with HTTP {error.code}"
        ) from None
    except urllib.error.URLError as error:
        raise RunPodInventoryError(
            f"RunPod inventory request failed: {error.reason}"
        ) from None
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RunPodInventoryError("RunPod inventory returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RunPodInventoryError("RunPod inventory returned an invalid response")
    return value


def _normalize_offer(
    value: Any,
    *,
    cloud: str,
    gpu_count: int,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    stock_status = value.get("stockStatus")
    if stock_status not in {"High", "Medium", "Low"}:
        return None
    on_demand = value.get("uninterruptablePrice")
    minimum_bid = value.get("minimumBidPrice")
    return {
        "cloud": cloud,
        "gpu_count": gpu_count,
        "stock_status": stock_status,
        "on_demand_usd_per_hour": on_demand if isinstance(on_demand, (int, float)) else None,
        "minimum_bid_usd_per_hour": (
            minimum_bid if isinstance(minimum_bid, (int, float)) else None
        ),
        "provider_available_gpu_counts": (
            value["availableGpuCounts"]
            if isinstance(value.get("availableGpuCounts"), list)
            else None
        ),
    }


def load_runpod_inventory(
    api_key: str | None = None,
    *,
    now: datetime | None = None,
    request_graphql: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    credential = api_key or os.environ.get("RUNPOD_API_KEY")
    if not credential:
        raise RunPodInventoryError("RUNPOD_API_KEY is not configured")
    requester = request_graphql or (lambda query: _request_graphql(credential, query))
    value = requester(RUNPOD_INVENTORY_QUERY)
    errors = value.get("errors") if isinstance(value, dict) else None
    if errors:
        raise RunPodInventoryError("RunPod inventory GraphQL response contained errors")
    rows = value.get("data", {}).get("gpuTypes") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        raise RunPodInventoryError("RunPod inventory response omitted gpuTypes")

    aliases = {
        "s1": ("secure", 1),
        "s2": ("secure", 2),
        "s4": ("secure", 4),
        "s8": ("secure", 8),
        "c1": ("community", 1),
    }
    gpu_types: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        offers = [
            offer
            for alias, (cloud, gpu_count) in aliases.items()
            if (
                offer := _normalize_offer(
                    row.get(alias),
                    cloud=cloud,
                    gpu_count=gpu_count,
                )
            )
            is not None
        ]
        if not offers:
            continue
        gpu_types.append(
            {
                "id": row["id"],
                "display_name": row.get("displayName"),
                "memory_gb": row.get("memoryInGb"),
                "offers": offers,
            }
        )
    gpu_types.sort(key=lambda row: (-(row["memory_gb"] or 0), row["id"]))

    mi300x = next(
        (row for row in gpu_types if row["id"] == "AMD Instinct MI300X OAM"),
        None,
    )
    mi300x_secure = (
        [offer for offer in mi300x["offers"] if offer["cloud"] == "secure"]
        if mi300x
        else []
    )
    mi300x_one = next(
        (offer for offer in mi300x_secure if offer["gpu_count"] == 1),
        None,
    )
    return {
        "schema_version": 1,
        "provider": "runpod",
        "retrieved_at_utc": _utc(now or datetime.now(timezone.utc)),
        "evidence_type": "measured_authenticated_provider_api",
        "source": RUNPOD_GRAPHQL_URL,
        "stock_labels_are_qualitative": True,
        "allocation_verified": False,
        "default_amd_experiment_route": {
            "provider": "runpod",
            "accelerator_id": "AMD Instinct MI300X OAM",
            "available": mi300x_one is not None,
            "stock_status": mi300x_one["stock_status"] if mi300x_one else None,
            "on_demand_usd_per_gpu_hour": (
                mi300x_one["on_demand_usd_per_hour"] if mi300x_one else None
            ),
            "minimum_bid_usd_per_gpu_hour": (
                mi300x_one["minimum_bid_usd_per_hour"] if mi300x_one else None
            ),
            "available_secure_gpu_counts": sorted(
                offer["gpu_count"] for offer in mi300x_secure
            ),
            "scope": "ordinary AMD Pod experiments; not verified bare metal or host-level profiling",
        },
        "gpu_types": gpu_types,
    }
