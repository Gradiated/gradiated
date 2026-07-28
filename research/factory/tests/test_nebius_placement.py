from __future__ import annotations

import unittest

from grad_research.nebius_placement import price_and_rank_candidates, select_candidates


PROJECTS = {
    "items": [
        {
            "metadata": {"id": "project-us", "name": "US"},
            "status": {
                "region": "us-central1",
                "container_state": "ACTIVE",
                "suspension_state": "NONE",
            },
        },
        {
            "metadata": {"id": "project-me", "name": "ME"},
            "status": {
                "region": "me-west1",
                "container_state": "ACTIVE",
                "suspension_state": "NONE",
            },
        },
    ]
}


def advice(
    region: str,
    *,
    preset: str = "1gpu-20vcpu-224gb",
    gpu_count: int = 1,
    spot_available: int = 8,
    on_demand_available: int = 1,
) -> dict:
    return {
        "spec": {
            "region": region,
            "fabric": f"{region}-a",
            "compute_instance": {
                "platform": "gpu-b200-sxm",
                "preset": {
                    "name": preset,
                    "resources": {"gpu_count": gpu_count},
                },
                "gpu_memory_gigabytes": 180,
            },
        },
        "status": {
            "preemptible": {
                "data_state": "DATA_STATE_FRESH",
                "available": spot_available,
                "limit": 8,
                "availability_level": (
                    "AVAILABILITY_LEVEL_HIGH"
                    if spot_available
                    else "AVAILABILITY_LEVEL_NONE"
                ),
            },
            "on_demand": {
                "data_state": "DATA_STATE_FRESH",
                "available": on_demand_available,
                "limit": 32,
                "availability_level": "AVAILABILITY_LEVEL_LOW",
            },
        },
    }


class NebiusPlacementTests(unittest.TestCase):
    def test_auto_prefers_spot_across_regions(self) -> None:
        rows = select_candidates(
            PROJECTS,
            {"items": [advice("us-central1"), advice("me-west1")]},
            accelerator="b200",
            gpu_count=1,
        )

        self.assertEqual("preemptible", rows[0].allocation_type)
        self.assertEqual("me-west1", rows[0].region)
        self.assertIn("--preemptible-on-preemption", rows[0].as_dict()["compute_create_flags"])
        self.assertEqual(
            {"me-west1", "us-central1"},
            {row.region for row in rows if row.allocation_type == "preemptible"},
        )

    def test_auto_falls_back_to_on_demand(self) -> None:
        rows = select_candidates(
            PROJECTS,
            {"items": [advice("us-central1", spot_available=0)]},
            accelerator="b200",
            gpu_count=1,
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("on-demand", rows[0].allocation_type)
        self.assertNotIn("--preemptible-on-preemption", rows[0].as_dict()["compute_create_flags"])

    def test_exact_gpu_count_and_region_are_respected(self) -> None:
        rows = select_candidates(
            PROJECTS,
            {
                "items": [
                    advice("us-central1"),
                    advice(
                        "us-central1",
                        preset="8gpu-160vcpu-1792gb",
                        gpu_count=8,
                        spot_available=8,
                        on_demand_available=0,
                    ),
                    advice(
                        "me-west1",
                        preset="8gpu-160vcpu-1792gb",
                        gpu_count=8,
                        spot_available=8,
                        on_demand_available=0,
                    ),
                ]
            },
            accelerator="b200",
            gpu_count=8,
            allocation="preemptible",
            regions={"us-central1"},
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("8gpu-160vcpu-1792gb", rows[0].preset)
        self.assertEqual("project-us", rows[0].project_id)

    def test_regional_price_breaks_capacity_tie_before_region(self) -> None:
        candidates = [
            {
                **row.as_dict(),
                "subnet_id": f"subnet-{row.region}",
            }
            for row in select_candidates(
                PROJECTS,
                {"items": [advice("us-central1"), advice("me-west1")]},
                accelerator="b200",
                gpu_count=1,
                allocation="preemptible",
            )
        ]
        prices = {
            "provider_regional_rates": [
                {
                    "provider": "nebius",
                    "region": "us-central1",
                    "platform": "gpu-b200-sxm",
                    "capacity_type": "preemptible",
                    "usd_per_gpu_hour": 2.5,
                    "source_id": "test",
                },
                {
                    "provider": "nebius",
                    "region": "me-west1",
                    "platform": "gpu-b200-sxm",
                    "capacity_type": "preemptible",
                    "usd_per_gpu_hour": 3.0,
                    "source_id": "test",
                },
            ]
        }

        ranked = price_and_rank_candidates(candidates, prices)

        self.assertEqual("us-central1", ranked[0]["region"])
        self.assertEqual(2.5, ranked[0]["estimated_compute_usd_per_instance_hour"])


if __name__ == "__main__":
    unittest.main()
