#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import paged_fp8_contract as contract
import paged_fp8_execution as execution


def passing_oracles() -> dict:
    return {
        "bf16_vs_reference": {
            "finite": True,
            "nonzero": True,
            "cosine": 0.9999,
            "normalized_rmse": 0.001,
        },
        "fp8_vs_bf16": {
            "finite": True,
            "nonzero": True,
            "cosine": 0.995,
            "normalized_rmse": 0.02,
        },
    }


def counter(range_name: str, dram: float, launches: int = 2) -> dict:
    return {
        "pass": True,
        "range": range_name,
        "dram_bytes_read": dram,
        "l2_bytes": dram * 1.1,
        "sm_cycles": 1000.0,
        "achieved_active_warps_pct": 37.0,
        "kernel_launch_count": launches,
    }


def passing_row(
    case_name: str,
    concurrency: int,
    bf16_ms: float = 10.0,
    fp8_ms: float = 8.0,
) -> dict:
    case = contract.CASES[case_name]
    prefix = f"h100_paged_fp8::{case_name}::c{concurrency}"
    context_factor = case.context / 1024
    return {
        "case": case_name,
        "family": case.family,
        "context": case.context,
        "concurrency": concurrency,
        "producer_slots": concurrency * case.context,
        "native_trace": {"pass": True},
        "oracles": passing_oracles(),
        "timing": {
            "bf16": {
                "serialized_cuda_event_interval_union_ms_p50": bf16_ms,
            },
            "fp8_e4m3": {
                "serialized_cuda_event_interval_union_ms_p50": fp8_ms,
            },
        },
        "counters": {
            "bf16": counter(f"{prefix}::bf16", 1000.0 * context_factor),
            "fp8_e4m3": counter(
                f"{prefix}::fp8_e4m3", 500.0 * context_factor
            ),
        },
    }


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def to(self, device):
        return FakeTensor((self.value, device))


class FakeTorch:
    bfloat16 = "bfloat16"
    int32 = "int32"

    @staticmethod
    def device(value):
        return f"device:{value}"

    @staticmethod
    def arange(stop, dtype=None, device=None):
        return FakeTensor(("arange", stop, dtype, device))

    @staticmethod
    def full(shape, value, dtype=None, device=None):
        return FakeTensor(("full", shape, value, dtype, device))


class FakeCacheConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.kv_cache_dtype_skip_layers = []


class FakeVllmConfig:
    def __init__(self, model_config=None, cache_config=None):
        self.model_config = model_config
        self.cache_config = cache_config
        self.parallel_config = SimpleNamespace(
            tensor_parallel_size=1,
            decode_context_parallel_size=1,
        )
        self.compilation_config = SimpleNamespace(static_forward_context={})


class FakeBuilder:
    init_args = None
    build_kwargs = None

    def __init__(self, kv_cache_spec, layer_names, vllm_config, device):
        FakeBuilder.init_args = (
            kv_cache_spec,
            layer_names,
            vllm_config,
            device,
        )

    def build(
        self,
        common_prefix_len,
        common_attn_metadata,
        fast_build=False,
    ):
        FakeBuilder.build_kwargs = {
            "common_prefix_len": common_prefix_len,
            "common_attn_metadata": common_attn_metadata,
            "fast_build": fast_build,
        }
        return SimpleNamespace(native=True)


class FakeBackend:
    __module__ = "vllm.v1.attention.backends.triton_attn"

    @staticmethod
    def get_builder_cls():
        return FakeBuilder


class FakeLayer:
    def __init__(self, config, prefix):
        self.attn_backend = FakeBackend
        self.impl = SimpleNamespace()
        self.kv_cache_torch_dtype = "fake-cache-dtype"
        config.compilation_config.static_forward_context[prefix] = self

    def get_kv_cache_spec(self, config):
        return SimpleNamespace(native=True, block_size=config.cache_config.block_size)


class FakeCommonAttentionMetadata:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class ConstructionRuntime:
    def __init__(self):
        self.torch = FakeTorch
        self.VllmConfig = FakeVllmConfig
        self.CacheConfig = FakeCacheConfig
        self.CommonAttentionMetadata = FakeCommonAttentionMetadata
        self.TritonAttentionBackend = FakeBackend
        self.current_config = None
        self.context_entered = False

    @contextmanager
    def set_current_vllm_config(self, config):
        self.current_config = config
        self.context_entered = True
        yield
        self.context_entered = False

    def Attention(self, *args, **kwargs):
        if not self.context_entered:
            raise AssertionError("Attention constructed outside config context")
        self.attention_args = args
        self.attention_kwargs = kwargs
        return FakeLayer(self.current_config, kwargs["prefix"])


class GeometryTests(unittest.TestCase):
    def test_full_context_slots_preserve_page_padding(self):
        case = contract.CASES["global4214"]
        slots = contract.full_slot_mapping(case, 2)
        pages = math.ceil(case.context / contract.PAGE_SIZE)
        self.assertEqual(len(slots), 2 * case.context)
        self.assertEqual(slots[0], 0)
        self.assertEqual(slots[case.context - 1], case.context - 1)
        self.assertEqual(slots[case.context], pages * contract.PAGE_SIZE)
        self.assertEqual(
            contract.decode_slot_mapping(case, 2),
            [case.context - 1, pages * contract.PAGE_SIZE + case.context - 1],
        )

    def test_exact_local_and_global_kv_geometry(self):
        local = contract.CASES["local1024"]
        global_case = contract.CASES["global4214"]
        self.assertEqual((local.kv_heads, local.head_dim), (16, 256))
        self.assertEqual((global_case.kv_heads, global_case.head_dim), (4, 512))
        self.assertEqual(local.q_heads, 32)
        self.assertEqual(global_case.q_heads, 32)
        self.assertIsNone(global_case.sliding_window)

    def test_pair_order_is_balanced_and_deterministic(self):
        first = contract.balanced_pair_orders(100, 17)
        second = contract.balanced_pair_orders(100, 17)
        self.assertEqual(first, second)
        self.assertEqual(first.count(("bf16", "fp8_e4m3")), 50)
        self.assertEqual(first.count(("fp8_e4m3", "bf16")), 50)


class NativeConstructionTests(unittest.TestCase):
    def test_registered_attention_native_spec_and_builder_are_reachable(self):
        runtime = ConstructionRuntime()
        case = contract.CASES["global4214"]
        config, layer, builder, trace = execution.construct_registered_layer(
            runtime, case, "fp8_e4m3", "registered.global"
        )
        self.assertTrue(trace["pass"])
        self.assertTrue(trace["config_context_entered"])
        self.assertFalse(config.model_config.is_mm_prefix_lm)
        self.assertFalse(config.model_config.use_mla)
        self.assertIs(
            config.compilation_config.static_forward_context["registered.global"],
            layer,
        )
        self.assertEqual(runtime.attention_kwargs["num_kv_heads"], 4)
        self.assertIsNone(runtime.attention_kwargs["per_layer_sliding_window"])
        self.assertIs(
            runtime.attention_kwargs["attn_backend"], FakeBackend
        )
        self.assertEqual(
            FakeBuilder.init_args,
            (
                FakeBuilder.init_args[0],
                ["registered.global"],
                config,
                "device:cuda",
            ),
        )
        _, metadata = execution.native_decode_metadata(
            runtime,
            builder,
            case,
            8,
            FakeTensor("block_table"),
            FakeTensor("decode_slots"),
        )
        self.assertTrue(metadata.native)
        self.assertEqual(FakeBuilder.build_kwargs["common_prefix_len"], 0)
        self.assertFalse(FakeBuilder.build_kwargs["fast_build"])
        common = FakeBuilder.build_kwargs["common_attn_metadata"]
        self.assertIsInstance(common, FakeCommonAttentionMetadata)
        self.assertEqual(common.num_reqs, 8)
        self.assertEqual(common.num_actual_tokens, 8)
        self.assertEqual(common.max_seq_len, 4214)


class AcceptanceTests(unittest.TestCase):
    def test_row_passes_all_semantic_counter_and_component_gates(self):
        result = contract.evaluate_row(passing_row("local1024", 8))
        self.assertTrue(result["pass"])
        self.assertAlmostEqual(result["saving_fraction"], 0.2)
        self.assertAlmostEqual(result["dram_fraction"], 0.5)

    def test_missing_counter_fails_closed(self):
        row = passing_row("local1024", 8)
        del row["counters"]["fp8_e4m3"]["dram_bytes_read"]
        with self.assertRaisesRegex(contract.ContractError, "dram_bytes_read"):
            contract.evaluate_row(row)

    def test_nonfinite_or_zero_oracle_fails_closed(self):
        row = passing_row("local1024", 8)
        row["oracles"]["fp8_vs_bf16"]["finite"] = False
        with self.assertRaisesRegex(contract.ContractError, "zero or non-finite"):
            contract.evaluate_row(row)

    def test_partial_context_producer_fails_closed(self):
        row = passing_row("global4214", 8)
        row["producer_slots"] -= 1
        with self.assertRaisesRegex(contract.ContractError, "complete context"):
            contract.evaluate_row(row)

    def test_sentinel_trigger_requires_both_rows_and_reserve(self):
        now = datetime(2026, 7, 26, 5, 0, tzinfo=timezone.utc)
        deadline = "2026-07-26T05:10:00Z"
        accepted = contract.sentinel_continuation(
            [
                passing_row("local1024", 8),
                passing_row("global4214", 8),
            ],
            deadline,
            now,
        )
        self.assertTrue(accepted["conditional_sweep_allowed"])
        rejected = contract.sentinel_continuation(
            [
                passing_row("local1024", 8),
                passing_row("global4214", 8),
            ],
            "2026-07-26T05:06:59Z",
            now,
        )
        self.assertFalse(rejected["conditional_sweep_allowed"])

    def test_context_byte_reduction_must_increase(self):
        rows = []
        for concurrency in contract.CONCURRENCIES:
            for case_name in ("global4214", "global4393", "global4571"):
                row = passing_row(case_name, concurrency)
                row = {
                    **row,
                    "evaluation": contract.evaluate_row(row),
                    "pass": True,
                }
                rows.append(row)
        contract.assert_context_byte_trend(rows)
        rows[-1]["counters"]["fp8_e4m3"]["dram_bytes_read"] = (
            rows[-1]["counters"]["bf16"]["dram_bytes_read"]
        )
        with self.assertRaisesRegex(contract.ContractError, "does not increase"):
            contract.assert_context_byte_trend(rows)


class EconomicsTests(unittest.TestCase):
    def test_50_10_by_358_aggregation_is_exact(self):
        rows = []
        for concurrency in contract.CONCURRENCIES:
            for case_name in contract.CASES:
                row = passing_row(
                    case_name,
                    concurrency,
                    bf16_ms=1.0 + 0.2 * concurrency,
                    fp8_ms=1.0,
                )
                evaluated = contract.evaluate_row(row)
                self.assertTrue(evaluated["pass"])
                rows.append({**row, "evaluation": evaluated, "pass": True})
        aggregate = contract.aggregate_economics(rows)
        self.assertTrue(aggregate["pass"])
        expected_local = 0.2 / 1000 * 50 * 358
        expected_global = 0.2 / 1000 * 10 * 358
        for result in aggregate["by_concurrency"].values():
            self.assertAlmostEqual(
                result["total_seconds_per_request"],
                expected_local + expected_global,
            )

    def test_missing_sweep_row_fails_closed(self):
        rows = []
        for concurrency in contract.CONCURRENCIES:
            for case_name in contract.CASES:
                if concurrency == 32 and case_name == "global4571":
                    continue
                row = passing_row(case_name, concurrency)
                rows.append(
                    {
                        **row,
                        "evaluation": contract.evaluate_row(row),
                        "pass": True,
                    }
                )
        with self.assertRaisesRegex(contract.ContractError, "missing global"):
            contract.aggregate_economics(rows)


class CounterParserTests(unittest.TestCase):
    HEADER = (
        '"ID","Process ID","Process Name","Host Name","Kernel Name","Context",'
        '"Stream","Section Name","Metric Name","Metric Unit","Metric Value"\n'
    )

    def test_ncu_csv_normalizes_required_metrics_and_launches(self):
        rows = []
        for kernel_id, kernel in ((1, "consumer_a"), (2, "consumer_b")):
            for metric, value in (
                ("dram__bytes_read.sum", "1,024"),
                ("lts__t_bytes.sum", "2,048"),
                ("sm__cycles_elapsed.avg", "100"),
                (
                    "sm__warps_active.avg.pct_of_peak_sustained_active",
                    "40",
                ),
            ):
                rows.append(
                    f'"{kernel_id}","1","python","host","{kernel}","1","7",'
                    f'"raw","{metric}","unit","{value}"\n'
                )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.csv"
            path.write_text(self.HEADER + "".join(rows))
            parsed = contract.parse_ncu_csv(path, "expected-range")
        self.assertEqual(parsed["kernel_launch_count"], 2)
        self.assertEqual(parsed["dram_bytes_read"], 2048)
        self.assertEqual(parsed["range"], "expected-range")

    def test_ncu_csv_missing_metric_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.csv"
            path.write_text(
                self.HEADER
                + '"1","1","python","host","kernel","1","7","raw",'
                  '"dram__bytes_read.sum","byte","100"\n'
            )
            with self.assertRaisesRegex(contract.ContractError, "missing metrics"):
                contract.parse_ncu_csv(path, "expected-range")


class BindingTests(unittest.TestCase):
    def test_pinned_signature_check_fails_closed(self):
        def wrong_producer(key, value):
            return None

        with self.assertRaisesRegex(RuntimeError, "signature mismatch"):
            execution.require_signature(
                "unified_kv_cache_update", wrong_producer
            )

    def test_rejected_program_is_not_reused(self):
        project = Path(__file__).resolve().parent
        rejected = (
            project.parent
            / "h100_paged_fp8_actual_consumer_packet_v2"
            / "paged_consumer_program.py"
        )
        self.assertNotEqual(
            contract.sha256_file(project / "paged_fp8_execution.py"),
            contract.sha256_file(rejected),
        )

    def test_worker_command_has_no_provider_lifecycle_operation(self):
        command = execution.worker_command(
            Path("/project/paged_fp8_execution.py"),
            "pair-worker",
            "local1024",
            8,
            Path("/artifacts/row.json"),
            17,
            contract.EXPECTED_IMAGE,
        )
        rendered = " ".join(command)
        for forbidden in ("create", "delete", "claim", "release", "nebius"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
