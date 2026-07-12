import unittest

from validation.qwen_vllm_repeatability.host import (
    HostSnapshot,
    ProcessRecord,
    evaluate_isolation,
    parse_vm_stat,
    process_descendants,
)
from validation.qwen_vllm_repeatability.schema import CampaignSpec
from validation.qwen_vllm_repeatability.tests.test_schema import valid_mapping


class HostTests(unittest.TestCase):
    def test_parses_available_memory_estimate_from_page_counts(self) -> None:
        raw = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free: 100.
Pages inactive: 200.
Pages speculative: 50.
Pages purgeable: 25.
"""

        self.assertEqual(parse_vm_stat(raw), 375 * 16384)

    def test_isolation_fails_on_external_cpu_pressure(self) -> None:
        mapping = valid_mapping()
        mapping["isolation"]["minimum_available_memory_bytes"] = 1
        spec = CampaignSpec.from_mapping(mapping)
        snapshot = HostSnapshot(
            captured_at="2026-07-12T00:00:00Z",
            ac_power=True,
            thermal_warning=False,
            available_memory_bytes=10_000,
            load_average=(1.0, 1.0, 1.0),
            processes=(
                ProcessRecord(1, 0, 0.1, 100, "launchd"),
                ProcessRecord(99, 1, 75.0, 1000, "python score_qwen.py"),
            ),
            raw_commands={},
        )

        decision = evaluate_isolation(snapshot, spec.isolation, excluded_pids={1})

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.blocking_processes[0].pid, 99)

    def test_isolation_accepts_recorded_quiet_ac_host(self) -> None:
        mapping = valid_mapping()
        mapping["isolation"]["minimum_available_memory_bytes"] = 1
        spec = CampaignSpec.from_mapping(mapping)
        snapshot = HostSnapshot(
            captured_at="2026-07-12T00:00:00Z",
            ac_power=True,
            thermal_warning=False,
            available_memory_bytes=10_000,
            load_average=(1.0, 1.0, 1.0),
            processes=(ProcessRecord(1, 0, 0.1, 100, "launchd"),),
            raw_commands={},
        )

        decision = evaluate_isolation(snapshot, spec.isolation, excluded_pids={1})

        self.assertTrue(decision.accepted)

    def test_process_descendants_cover_server_worker_tree(self) -> None:
        processes = (
            ProcessRecord(10, 1, 0.0, 1, "server"),
            ProcessRecord(11, 10, 0.0, 1, "engine"),
            ProcessRecord(12, 11, 0.0, 1, "worker"),
            ProcessRecord(20, 1, 0.0, 1, "unrelated"),
        )

        self.assertEqual(process_descendants(processes, {10}), {10, 11, 12})


if __name__ == "__main__":
    unittest.main()
