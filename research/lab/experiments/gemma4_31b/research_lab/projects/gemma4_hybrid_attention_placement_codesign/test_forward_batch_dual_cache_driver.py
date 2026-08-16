from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path



ROOT = Path(__file__).resolve().parent


def module(name: str, path: Path):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


class Mode:
    def __init__(self, name): self.name = name


class Batch:
    def __init__(self, mode, slots, logical=None, padded=-1):
        self.forward_mode = Mode(mode)
        self.out_cache_loc = slots
        self.input_ids = list(range(logical if logical is not None else len(slots)))
        self.num_token_non_padded = None
        self.num_token_non_padded_cpu = logical
        self.padded_static_len = padded
        # These fixtures exercise cache ownership, not the torch-backed
        # missing-mirror path; retain a stock mirror verbatim.
        self.seq_lens_cpu = [len(self.input_ids)]


class NativeSlots(list):
    device = "cuda:0"

    def tolist(self):
        return list(self)

    def __getitem__(self, key):
        if isinstance(key, list):
            return NativeSlots([list.__getitem__(self, index) for index in key])
        value = super().__getitem__(key)
        return NativeSlots(value) if isinstance(key, slice) else value


class Allocator:
    def __init__(self, pool=None, start=10000): self.next = start; self.freed = []; self.pool = pool; self.alloc_calls = []
    def alloc(self, count):
        self.alloc_calls.append(count)
        result = NativeSlots(range(self.next, self.next + count)); self.next += count; return result
    def free(self, slots): self.freed.extend(slots)
    def get_kvcache(self): return self.pool


class Pool:
    def __init__(self): self.writes = []
    def set_kv_buffer(self, attention, slots, k, v): self.writes.append((attention, list(slots), k, v))


class Radix:
    def __init__(self): self.calls = []
    def forward(self, q, k, v, *args, **kwargs):
        self.calls.append(list(kwargs["forward_batch"].out_cache_loc)); return "attention-output"


class Layer:
    def __init__(self): self.self_attn = type("Self", (), {"attn": Radix()})()


class Model:
    def __init__(self): self.language_model = type("Text", (), {"layers": [Layer() for _ in range(60)]})()


class Backend:
    def __init__(self):
        self.token_to_kv_pool = Pool()
        self.token_to_kv_pool_allocator = Allocator(self.token_to_kv_pool)


class TreeCache:
    def __init__(self, allocator): self.token_to_kv_pool_allocator = allocator


class Runner:
    def __init__(self): self.model = Model(); self.attn_backend = Backend()


class NgramInfo:
    def prepare_for_verify(self, batch, page_size): return None
    def sample(self, batch, logits_output, vocab_mask=None): return (None, None, self.accept_indices)


class NgramV2Info:
    def prepare_for_v2_verify(self, req_to_token_pool, batch, target_worker): return None
    def sample(self, batch, logits_output, vocab_mask=None): return (None, None, self.accept_indices)


class NgramWorker:
    def forward_batch_generation(self, batch, *args, **kwargs): return "target-consumed"


class ForwardBatchDualCacheDriverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = module("forward_batch_dual_cache_driver_test", ROOT / "forward_batch_dual_cache_driver.py")

    def test_none_geometry_is_authoritative_and_nonfatal(self):
        batch = Batch("EXTEND", [1, 2, 3], logical=None)
        evidence = self.driver.validate_forward_batch(batch)
        self.assertEqual(evidence["logical_rows"], 3)
        self.assertFalse(evidence["target_verify"])

    def test_target_geometry_rejects_missing_slots(self):
        with self.assertRaisesRegex(RuntimeError, "below logical rows"):
            self.driver.validate_forward_batch(Batch("TARGET_VERIFY", [1], logical=384))

    def test_production_symbols_allocate_write_consume_and_free(self):
        runner = Runner()
        binding = self.driver.install_production_ngram_dual_cache(
            runner, ngram_info_cls=NgramInfo, ngram_worker_cls=NgramWorker
        )
        self.assertEqual(binding["first_target_consumer"], "NGRAMWorker.forward_batch_generation")
        batch = Batch("TARGET_VERIFY", range(384), logical=384, padded=512)
        batch.tree_cache = TreeCache(runner.attn_backend.token_to_kv_pool_allocator)
        info = NgramInfo()
        info.prepare_for_verify(batch, 1)
        record = batch._phase_selective_dual_cache
        self.assertEqual(len(record.proxy_slots), 384)
        self.assertTrue(set(record.proxy_slots).isdisjoint(record.stock_slots))
        # The converted RadixAttention uses proxy slots then explicitly shadows stock.
        radix = runner.model.language_model.layers[11].self_attn.attn
        self.assertEqual(radix.forward("q", "k", "v", forward_batch=batch), "attention-output")
        self.assertEqual(radix.calls[-1], record.proxy_slots)
        self.assertEqual(runner.attn_backend.token_to_kv_pool.writes[-1][1], list(record.stock_slots))
        self.assertEqual(NgramWorker().forward_batch_generation(batch), "target-consumed")
        info.accept_indices = [0, 2, 7]
        self.assertEqual(info.sample(batch, object()), (None, None, [0, 2, 7]))
        self.assertEqual(batch._phase_selective_proxy_cache_loc, [record.proxy_slots[i] for i in [0, 2, 7]])
        self.assertEqual(len(runner.attn_backend.token_to_kv_pool_allocator.freed), 381)

    def test_stock_extend_allocates_no_proxy_and_preserves_8192_capacity(self):
        runner = Runner()
        pool = Pool()
        allocator = Allocator(pool, start=8193)
        batch = Batch("EXTEND", NativeSlots(range(1, 8193)), logical=8192, padded=8192)
        batch.tree_cache = TreeCache(allocator)
        cache = self.driver.ProductionDualCache(runner.attn_backend.token_to_kv_pool_allocator, runner.attn_backend.token_to_kv_pool)
        self.assertIsNone(cache.allocate(batch, self.driver.validate_forward_batch(batch)))
        self.assertEqual(allocator.alloc_calls, [])
        self.assertEqual(allocator.next, 8193)
        self.assertFalse(hasattr(batch, "_phase_selective_dual_cache"))

    def test_prior_8192_eager_geometry_exhausts_before_repair_and_target_only_passes(self):
        class ExhaustedAllocator(Allocator):
            def alloc(self, count):
                self.alloc_calls.append(count)
                return None

        allocator = ExhaustedAllocator(Pool())
        batch = Batch("EXTEND", NativeSlots(range(1, 8193)), logical=8192, padded=8192)
        batch.tree_cache = TreeCache(allocator)
        # This is the exact pre-repair branch: all non-IDLE batches attempted
        # to reserve a peer vector and failed before TARGET_VERIFY.
        self.assertIsNone(allocator.alloc(8192))
        self.assertEqual(allocator.alloc_calls, [8192])
        allocator.alloc_calls.clear()
        cache = self.driver.ProductionDualCache(allocator, allocator.pool)
        self.assertIsNone(cache.allocate(batch, self.driver.validate_forward_batch(batch)))
        self.assertEqual(allocator.alloc_calls, [])

    def test_v2_verify_keeps_its_pinned_signature_and_cache_lifecycle(self):
        runner = Runner()
        binding = self.driver.install_production_ngram_dual_cache(
            runner, ngram_info_cls=NgramV2Info, ngram_worker_cls=NgramWorker
        )
        self.assertEqual(binding["producer"], "NgramVerifyInput.prepare_for_v2_verify")
        batch = Batch("TARGET_VERIFY", range(384), logical=384, padded=512)
        batch.tree_cache = TreeCache(runner.attn_backend.token_to_kv_pool_allocator)
        NgramV2Info().prepare_for_v2_verify(object(), batch, object())
        self.assertEqual(len(batch._phase_selective_dual_cache.proxy_slots), 384)

    def test_target_verify_uses_tree_allocator_and_keeps_native_slot_vectors(self):
        runner = Runner()
        stock_pool = Pool()
        stock_allocator = Allocator(stock_pool, start=8193)
        batch = Batch("TARGET_VERIFY", NativeSlots(range(1, 385)), logical=384, padded=512)
        batch.tree_cache = TreeCache(stock_allocator)
        cache = self.driver.ProductionDualCache(
            runner.attn_backend.token_to_kv_pool_allocator,
            runner.attn_backend.token_to_kv_pool,
        )
        record = cache.allocate(batch, self.driver.validate_forward_batch(batch))
        self.assertIsInstance(record.stock_slots, NativeSlots)
        self.assertIsInstance(record.proxy_slots, NativeSlots)
        self.assertEqual(record.proxy_slots[:3], [8193, 8194, 8195])
        self.assertEqual(stock_allocator.alloc_calls, [384])
        self.assertTrue(set(record.proxy_slots).isdisjoint(record.stock_slots))
        self.assertEqual(runner.attn_backend.token_to_kv_pool_allocator.next, 10000)
        self.assertIs(record.pool, stock_pool)
        cache.release_rejected(batch, [0, 3, 383])
        self.assertIsInstance(batch._phase_selective_proxy_cache_loc, NativeSlots)
        self.assertEqual(len(stock_allocator.freed), 381)

    def test_target_accept_reject_lifecycle_is_once_and_post_accept_decode_is_stock(self):
        runner = Runner()
        self.driver.install_production_ngram_dual_cache(runner, ngram_info_cls=NgramInfo, ngram_worker_cls=NgramWorker)
        allocator = runner.attn_backend.token_to_kv_pool_allocator
        target = Batch("TARGET_VERIFY", NativeSlots(range(384)), logical=384, padded=512)
        target.tree_cache = TreeCache(allocator)
        info = NgramInfo()
        info.prepare_for_verify(target, 1)
        record = target._phase_selective_dual_cache
        info.accept_indices = [0, 2, 7]
        info.sample(target, object())
        self.assertEqual(len(allocator.freed), 381)
        info.sample(target, object())
        self.assertEqual(len(allocator.freed), 381, "rejected rows must free exactly once")
        decode = Batch("DECODE", NativeSlots([9]), logical=1)
        decode.tree_cache = TreeCache(allocator)
        cache = self.driver.ProductionDualCache(allocator, runner.attn_backend.token_to_kv_pool)
        self.assertIsNone(cache.allocate(decode, self.driver.validate_forward_batch(decode)))
        radix = runner.model.language_model.layers[11].self_attn.attn
        radix.forward("q", "k", "v", forward_batch=decode)
        self.assertEqual(radix.calls[-1], [9])
        self.assertEqual(allocator.alloc_calls, [384])
        self.assertEqual(target._phase_selective_proxy_cache_loc, [record.proxy_slots[i] for i in [0, 2, 7]])

    def test_source_binds_the_pinned_production_symbols(self):
        source = (ROOT / "forward_batch_dual_cache_driver.py").read_text()
        for symbol in (
            "NgramVerifyInput.prepare_for_verify",
            "NGRAMWorker.forward_batch_generation",
            "NgramVerifyInput.sample (EagleVerifyInputV2Mixin)",
            "RadixAttention.forward",
            "allocator.alloc",
            "allocator.free",
            "pool.set_kv_buffer",
            "tree_cache.token_to_kv_pool_allocator",
        ):
            self.assertIn(symbol, source)


if __name__ == "__main__":
    unittest.main()
