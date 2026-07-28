from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TERMINAL = ROOT / "PROXY_ALLOCATOR_DISTINCTNESS_OFFLINE_TERMINAL.json"


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
    def __init__(self, pool, start):
        self.pool = pool
        self.next = start
        self.freed = []

    def alloc(self, count):
        result = NativeSlots(range(self.next, self.next + count))
        self.next += count
        return result

    def free(self, slots):
        self.freed.extend(slots)

    def get_kvcache(self):
        return self.pool


class Pool:
    def set_kv_buffer(self, *_args):
        return None


class TreeCache:
    def __init__(self, allocator):
        self.token_to_kv_pool_allocator = allocator


class Mode:
    def __init__(self, name):
        self.name = name


class Batch:
    def __init__(self, mode, slots, logical, captured):
        self.forward_mode = Mode(mode)
        self.out_cache_loc = NativeSlots(slots)
        self.input_ids = list(range(logical))
        self.num_token_non_padded_cpu = logical
        self.num_token_non_padded = None
        self.padded_static_len = captured


def load_driver():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("proxy_allocator_driver", ROOT / "forward_batch_dual_cache_driver.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    driver = load_driver()
    backend_pool = Pool()
    backend_allocator = Allocator(backend_pool, start=1)
    stock_pool = Pool()
    stock_allocator = Allocator(stock_pool, start=8193)
    extend = Batch("EXTEND", range(1, 8193), logical=8192, captured=8192)
    extend.tree_cache = TreeCache(stock_allocator)
    cache = driver.ProductionDualCache(backend_allocator, backend_pool)
    old_fixed_backend = backend_allocator.alloc(8192)
    old_fixed_backend_overlap = bool(set(old_fixed_backend) & set(extend.out_cache_loc))
    backend_allocator.next = 1
    extend_record = cache.allocate(extend, driver.validate_forward_batch(extend))
    cache.release_rejected(extend, [0, 3, 8191])

    verify_pool = Pool()
    verify_allocator = Allocator(verify_pool, start=20384)
    verify = Batch("TARGET_VERIFY", range(20000, 20384), logical=384, captured=512)
    verify.tree_cache = TreeCache(verify_allocator)
    verify_record = cache.allocate(verify, driver.validate_forward_batch(verify))

    decode_pool = Pool()
    decode_allocator = Allocator(decode_pool, start=77)
    decode = Batch("DECODE", [76], logical=1, captured=1)
    decode.tree_cache = TreeCache(decode_allocator)
    decode_record = cache.allocate(decode, driver.validate_forward_batch(decode))

    checks = {
        "old_fixed_backend_overlap_reproduced": old_fixed_backend_overlap,
        "extend_8192_distinct": not bool(set(extend_record.stock_slots) & set(extend_record.proxy_slots)),
        "extend_uses_batch_tree_allocator": extend_record.proxy_slots[0] == 8193,
        "extend_native_slots_preserved": isinstance(extend_record.stock_slots, NativeSlots)
        and isinstance(extend_record.proxy_slots, NativeSlots),
        "extend_pool_owned_by_tree_allocator": extend_record.pool is stock_pool,
        "request_reuse_native_slots_preserved": isinstance(extend._phase_selective_proxy_cache_loc, NativeSlots)
        and list(extend._phase_selective_proxy_cache_loc) == [8193, 8196, 16384],
        "rejected_slots_freed_by_tree_allocator": len(stock_allocator.freed) == 8189,
        "target_verify_padded_rows_inert": verify_record.logical_rows == 384
        and len(verify_record.stock_slots) == 384
        and len(verify_record.proxy_slots) == 384,
        "decode_distinct": list(decode_record.stock_slots) == [76] and list(decode_record.proxy_slots) == [77],
    }
    if not all(checks.values()):
        raise RuntimeError(f"proxy allocator distinctness contract failed: {checks}")
    payload = {
        "schema_version": 1,
        "classification": "offline_logical_slot_representation_contract_pass",
        "binding": "DIRECTOR_PROXY_ALLOCATOR_OFFLINE_LOCALIZATION_20260726T0411Z.json",
        "scope": "CPU synthetic target-runtime allocator contract; no GPU claim or request submission",
        "checks": checks,
        "source": {
            "forward_batch_dual_cache_driver.py": sha256(ROOT / "forward_batch_dual_cache_driver.py"),
            "proxy_allocator_distinctness_contract.py": sha256(Path(__file__)),
            "pinned_image": "lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
            "pinned_runtime": {
                "mem_cache/allocator/token.py": "8e9c936a0e51307eae876dcf175ed91f6e505a77b2c8a3a2e3f390d0440916a9",
                "mem_cache/common.py": "987c02d71dd773d32263d6d34d94d508b74c707e0ca3d918723e981088bb14a9",
                "speculative/ngram_info.py": "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c",
            },
        },
        "conclusion": "Raw slot integers are meaningful only within the batch tree allocator's KV pool. The repair keeps native vectors through allocation, shadow writes, reuse, and free, and allocates proxy slots from batch.tree_cache.token_to_kv_pool_allocator.",
        "gpu_claimed": False,
        "requests_submitted": 0,
        "additional_provider_spend_usd": 0.0,
        "scientific_sample_consumed": False,
    }
    part = TERMINAL.with_suffix(".part")
    part.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    part.replace(TERMINAL)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
