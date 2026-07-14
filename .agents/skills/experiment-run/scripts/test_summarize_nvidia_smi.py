import datetime as dt
import tempfile
import unittest
from pathlib import Path

from summarize_nvidia_smi import read_samples, summarize


class NvidiaSmiSummaryTests(unittest.TestCase):
    def test_phase_summary_excludes_setup_samples(self):
        base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        samples = [
            {"parsed_timestamp": base + dt.timedelta(seconds=index), "gpu_util_pct": value, **{key: 0.0 for key in (
                "memory_util_pct", "memory_used_mib", "memory_total_mib", "power_draw_w", "power_limit_w",
                "temperature_c", "sm_clock_mhz", "memory_clock_mhz")}}
            for index, value in enumerate((0.0, 20.0, 80.0, 100.0))
        ]
        result = summarize(samples, [("science", base + dt.timedelta(seconds=2), base + dt.timedelta(seconds=3))])
        phase = result["phases"]["science"]
        self.assertEqual(phase["sample_count"], 2)
        self.assertEqual(phase["metrics"]["gpu_util_pct"]["mean"], 90.0)

    def test_explicit_timezone_offset_aligns_driver_local_timestamp(self):
        row = "2026/01/01 05:00:00.000, uuid, L40S, P0, 1, 2, 3, 4, 5, 6, 7, 8, 9\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.csv"
            path.write_text(row)
            sample = read_samples(path, timestamp_offset_hours=7)[0]
        self.assertEqual(sample["parsed_timestamp"].hour, 12)

    def test_phase_summary_integrates_energy_and_reports_sampling_gaps(self):
        base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        samples = [
            {"parsed_timestamp": base + dt.timedelta(seconds=second), "power_draw_w": power, **{key: 0.0 for key in (
                "gpu_util_pct", "memory_util_pct", "memory_used_mib", "memory_total_mib", "power_limit_w",
                "temperature_c", "sm_clock_mhz", "memory_clock_mhz")}}
            for second, power in ((0, 10.0), (1, 20.0), (3, 30.0))
        ]
        phase = summarize(samples, [("science", base, base + dt.timedelta(seconds=3))])["phases"]["science"]
        self.assertEqual(phase["energy_joules_trapezoidal"], 65.0)
        self.assertEqual(phase["sampling"]["max_gap_seconds"], 2.0)
        self.assertEqual(phase["sampling"]["coverage_fraction_at_1hz"], 0.75)


if __name__ == "__main__":
    unittest.main()
