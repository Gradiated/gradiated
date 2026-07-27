import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("run_offline_recovery.py")
SPEC = importlib.util.spec_from_file_location("offline_recovery", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_bf16_round_idempotent():
    values = np.asarray([0.0, 1.0, -2.5, 1e-7, 1e7], dtype=np.float32)
    once = MODULE.bf16_round(values)
    assert np.array_equal(once, MODULE.bf16_round(once))


def test_fp8_codebook_boundaries_and_sign():
    values = np.asarray([0.0, -0.0, 2**-9, -1.0, 448.0, -448.0], dtype=np.float32)
    decoded = MODULE.fp8_decode_normalized(MODULE.fp8_encode_normalized(values))
    assert np.array_equal(decoded, values)


def test_sparse_pack_has_two_values_and_roundtrips():
    rng = np.random.default_rng(7)
    weight = rng.standard_normal((8, 16), dtype=np.float32)
    codes, scales, metadata, decoded = MODULE.pack_sparse_2of4(weight)
    unpacked = MODULE.unpack_sparse_2of4(codes, scales, metadata, 16)
    assert np.array_equal(decoded, unpacked)
    assert np.all(np.count_nonzero(decoded.reshape(8, 4, 4), axis=2) == 2)


def test_rank_contract_is_single_closed_form_result():
    rank, physical = MODULE.derive_rank()
    assert rank == 512
    assert physical["rows"][32]["maximum_128_aligned_rank"] == 512
    assert physical["rows"][384]["maximum_128_aligned_rank"] >= 512
    assert physical["rows"][32]["candidate"]["modeled_saved_us"] > 0
    assert physical["rows"][384]["candidate"]["modeled_saved_us"] > 0
