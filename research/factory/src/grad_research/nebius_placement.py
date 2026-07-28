from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


class NebiusPlacementError(RuntimeError):
    pass


JsonCommand = Callable[[Sequence[str]], dict[str, Any]]


@dataclass(frozen=True)
class Candidate:
    region: str
    fabric: str
    project_id: str
    project_name: str
    platform: str
    preset: str
    gpu_count: int
    gpu_memory_gb: float | None
    allocation_type: str
    available_gpus: int
    quota_limit_gpus: int | None
    availability_level: str
    effective_at: str | None

    def as_dict(self) -> dict[str, Any]:
        preemptible_flags = (
            ["--preemptible-on-preemption", "STOP", "--preemptible-priority", "0"]
            if self.allocation_type == "preemptible"
            else []
        )
        return {
            "region": self.region,
            "fabric": self.fabric,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "platform": self.platform,
            "preset": self.preset,
            "gpu_count": self.gpu_count,
            "gpu_memory_gb": self.gpu_memory_gb,
            "allocation_type": self.allocation_type,
            "available_gpus": self.available_gpus,
            "quota_limit_gpus": self.quota_limit_gpus,
            "availability_level": self.availability_level,
            "effective_at": self.effective_at,
            "compute_create_flags": [
                "--parent-id",
                self.project_id,
                "--resources-platform",
                self.platform,
                "--resources-preset",
                self.preset,
                *preemptible_flags,
            ],
        }


def _availability_rank(level: str) -> int:
    return {
        "AVAILABILITY_LEVEL_HIGH": 4,
        "AVAILABILITY_LEVEL_MEDIUM": 3,
        "AVAILABILITY_LEVEL_LOW": 2,
        "AVAILABILITY_LEVEL_NONE": 1,
        "AVAILABILITY_LEVEL_LIMIT_REACHED": 0,
    }.get(level, 0)


def price_and_rank_candidates(
    candidates: list[dict[str, Any]],
    accelerator_price: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    regional_rates = (
        accelerator_price.get("provider_regional_rates", [])
        if isinstance(accelerator_price, dict)
        else []
    )
    priced: list[dict[str, Any]] = []
    for candidate in candidates:
        value = dict(candidate)
        rate = next(
            (
                row
                for row in regional_rates
                if row.get("provider") == "nebius"
                and row.get("region") == value.get("region")
                and row.get("platform") == value.get("platform")
                and row.get("capacity_type") == value.get("allocation_type")
            ),
            None,
        )
        if rate is not None:
            hourly = float(rate["usd_per_gpu_hour"])
            value.update(
                {
                    "estimated_compute_usd_per_gpu_hour": hourly,
                    "estimated_compute_usd_per_instance_hour": hourly * value["gpu_count"],
                    "price_source_id": rate["source_id"],
                    "price_scope": "unified VM compute price; storage, public IPv4, and egress excluded",
                }
            )
        priced.append(value)

    priced.sort(
        key=lambda value: (
            0 if value["allocation_type"] == "preemptible" else 1,
            value.get("estimated_compute_usd_per_instance_hour", float("inf")),
            -_availability_rank(value["availability_level"]),
            -value["available_gpus"],
            value["region"],
            value["preset"],
        )
    )
    return priced


def select_candidates(
    projects_response: dict[str, Any],
    advice_response: dict[str, Any],
    *,
    accelerator: str,
    gpu_count: int,
    allocation: str = "auto",
    platform: str | None = None,
    preset: str | None = None,
    regions: set[str] | None = None,
) -> list[Candidate]:
    if gpu_count < 1:
        raise NebiusPlacementError("gpu_count must be positive")
    if allocation not in {"auto", "preemptible", "on-demand"}:
        raise NebiusPlacementError(f"unsupported allocation type: {allocation}")

    projects_by_region: dict[str, tuple[str, str]] = {}
    for item in projects_response.get("items", []):
        metadata = item.get("metadata", {})
        status = item.get("status", {})
        region = status.get("region")
        project_id = metadata.get("id")
        if (
            isinstance(region, str)
            and isinstance(project_id, str)
            and status.get("container_state") == "ACTIVE"
            and status.get("suspension_state") in {None, "NONE"}
        ):
            projects_by_region[region] = (project_id, str(metadata.get("name", "")))

    requested_allocations = (
        ("preemptible", "on_demand") if allocation == "auto" else (allocation.replace("-", "_"),)
    )
    candidates: list[Candidate] = []
    accelerator_key = accelerator.lower()
    for item in advice_response.get("items", []):
        spec = item.get("spec", {})
        compute = spec.get("compute_instance", {})
        row_platform = compute.get("platform")
        row_preset = compute.get("preset", {})
        resources = row_preset.get("resources", {})
        row_gpu_count = resources.get("gpu_count")
        region = spec.get("region")
        if not all(isinstance(value, str) for value in (row_platform, region)):
            continue
        if accelerator_key not in row_platform.lower():
            continue
        if platform and row_platform != platform:
            continue
        if not isinstance(row_preset.get("name"), str):
            continue
        if preset and row_preset["name"] != preset:
            continue
        if row_gpu_count != gpu_count:
            continue
        if regions and region not in regions:
            continue
        if region not in projects_by_region:
            continue

        for allocation_key in requested_allocations:
            availability = item.get("status", {}).get(allocation_key, {})
            available = availability.get("available")
            level = str(availability.get("availability_level", ""))
            if availability.get("data_state") != "DATA_STATE_FRESH":
                continue
            if not isinstance(available, int) or available < gpu_count:
                continue
            if _availability_rank(level) == 0:
                continue
            project_id, project_name = projects_by_region[region]
            candidates.append(
                Candidate(
                    region=region,
                    fabric=str(spec.get("fabric", "")),
                    project_id=project_id,
                    project_name=project_name,
                    platform=row_platform,
                    preset=row_preset["name"],
                    gpu_count=gpu_count,
                    gpu_memory_gb=compute.get("gpu_memory_gigabytes"),
                    allocation_type=allocation_key.replace("_", "-"),
                    available_gpus=available,
                    quota_limit_gpus=availability.get("limit"),
                    availability_level=level,
                    effective_at=availability.get("effective_at"),
                )
            )

    def rank(candidate: Candidate) -> tuple[int, int, int, str, str]:
        return (
            0 if candidate.allocation_type == "preemptible" else 1,
            -_availability_rank(candidate.availability_level),
            -candidate.available_gpus,
            candidate.region,
            candidate.preset,
        )

    return sorted(candidates, key=rank)


def _subprocess_json(command: Sequence[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        value = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise NebiusPlacementError(f"Nebius discovery command failed: {' '.join(command)}: {error}") from error
    if not isinstance(value, dict):
        raise NebiusPlacementError(f"Nebius command returned a non-object: {' '.join(command)}")
    return value


def discover_placement(
    *,
    cli: Path,
    profile: str,
    accelerator: str,
    gpu_count: int,
    allocation: str,
    platform: str | None,
    preset: str | None,
    regions: set[str] | None,
    price_inventory: Path | None = None,
    run_json: JsonCommand = _subprocess_json,
    run_text: Callable[[Sequence[str]], str] | None = None,
) -> dict[str, Any]:
    base = [str(cli), "--profile", profile, "--format", "json", "--no-progress"]
    if run_text is None:
        def run_text(command: Sequence[str]) -> str:
            try:
                return subprocess.run(
                    list(command),
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError) as error:
                raise NebiusPlacementError(
                    f"Nebius discovery command failed: {' '.join(command)}: {error}"
                ) from error

    parent_id = run_text(
        [str(cli), "config", "get", "parent-id", "--profile", profile, "--no-progress"]
    )
    if parent_id.startswith("project-"):
        project = run_json([*base, "iam", "project", "get", "--id", parent_id])
        tenant_id = project.get("metadata", {}).get("parent_id")
    elif parent_id.startswith("tenant-"):
        tenant_id = parent_id
    else:
        tenant_id = None
    if not isinstance(tenant_id, str) or not tenant_id.startswith("tenant-"):
        raise NebiusPlacementError("could not infer tenant from the profile parent-id")

    projects = run_json([*base, "iam", "project", "list", "--parent-id", tenant_id, "--all"])
    advice = run_json(
        [*base, "capacity", "resource-advice", "list", "--parent-id", tenant_id, "--all"]
    )
    candidates = select_candidates(
        projects,
        advice,
        accelerator=accelerator,
        gpu_count=gpu_count,
        allocation=allocation,
        platform=platform,
        preset=preset,
        regions=regions,
    )
    candidate_values = [candidate.as_dict() for candidate in candidates]
    subnets_by_project: dict[str, dict[str, Any] | None] = {}
    for value in candidate_values:
        project_id = value["project_id"]
        if project_id not in subnets_by_project:
            subnets = run_json(
                [*base, "vpc", "subnet", "list", "--parent-id", project_id, "--all"]
            )
            ready = [
                item
                for item in subnets.get("items", [])
                if item.get("status", {}).get("state") == "READY"
                and isinstance(item.get("metadata", {}).get("id"), str)
            ]
            ready.sort(key=lambda item: str(item.get("metadata", {}).get("name", "")))
            subnets_by_project[project_id] = ready[0] if ready else None
        subnet = subnets_by_project[project_id]
        if subnet is None:
            continue
        metadata = subnet["metadata"]
        value["subnet_id"] = metadata["id"]
        value["subnet_name"] = metadata.get("name")
        value["network_id"] = subnet.get("spec", {}).get("network_id")
        value["network_interface"] = {
            "name": "default-subnet",
            "subnet_id": metadata["id"],
            "ip_address": {},
            "public_ip_address": {"static": False},
        }
    candidate_values = [value for value in candidate_values if value.get("subnet_id")]
    accelerator_price = None
    if price_inventory is not None:
        try:
            price_data = json.loads(price_inventory.read_text())
            accelerator_price = next(
                (
                    row
                    for row in price_data.get("accelerators", [])
                    if accelerator.lower() in str(row.get("id", "")).lower()
                    or accelerator.lower() in str(row.get("model", "")).lower()
                ),
                None,
            )
        except (OSError, json.JSONDecodeError):
            accelerator_price = None
    candidate_values = price_and_rank_candidates(candidate_values, accelerator_price)
    return {
        "schema_version": 1,
        "provider": "nebius",
        "profile": profile,
        "tenant_id": tenant_id,
        "request": {
            "accelerator": accelerator,
            "gpu_count": gpu_count,
            "allocation": allocation,
            "platform": platform,
            "preset": preset,
            "regions": sorted(regions) if regions else [],
        },
        "selection_policy": (
            "fresh capacity and ready subnet; preemptible first; regional price; availability level; available GPUs"
        ),
        "choice": candidate_values[0] if candidate_values else None,
        "ranked_candidates": candidate_values,
        "provider_mutation_performed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover region-agnostic Nebius GPU placement without creating resources."
    )
    parser.add_argument("--profile", default="glm-campaign")
    parser.add_argument("--cli", type=Path, default=Path("/root/.nebius/bin/nebius"))
    parser.add_argument("--accelerator", required=True, help="platform substring, for example b200")
    parser.add_argument("--gpu-count", type=int, default=1)
    parser.add_argument(
        "--allocation",
        choices=("auto", "preemptible", "on-demand"),
        default="auto",
        help="auto prefers preemptible and falls back to on-demand",
    )
    parser.add_argument("--platform")
    parser.add_argument("--preset")
    parser.add_argument("--region", action="append", dest="regions")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--price-inventory",
        type=Path,
        default=Path("/root/workspace/research/factory/data/gpu_prices.json"),
    )
    args = parser.parse_args(argv)
    try:
        result = discover_placement(
            cli=args.cli,
            profile=args.profile,
            accelerator=args.accelerator,
            gpu_count=args.gpu_count,
            allocation=args.allocation,
            platform=args.platform,
            preset=args.preset,
            regions=set(args.regions) if args.regions else None,
            price_inventory=args.price_inventory,
        )
    except NebiusPlacementError as error:
        parser.error(str(error))

    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0 if result["choice"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
