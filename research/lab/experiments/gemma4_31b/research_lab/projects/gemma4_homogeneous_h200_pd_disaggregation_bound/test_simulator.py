import simulator

def test_authoritative_calibration():
    c = simulator.calibration()
    assert c["pass"] and abs(c["simulated_batch_seconds"] / c["expected_batch_seconds"] - 1) < .01

def test_transfer_is_not_zero_by_default():
    r = simulator.run_sim(topology="disaggregated", total_gpus=8, prefill_gpus=3,
                          decode_gpus=5, offered_rps=0.5, requests=300, warmup=50)
    assert r.transfer_ms == 25.0 and r.completed > 0
