#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = json.loads((HERE / "DIRECTOR_BINDING.json").read_text())


def bound(spec):
    path = (HERE / spec["path"]).resolve()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]
    return json.loads(path.read_text())


stack = bound(BINDING["stack_binding"])
control = bound(BINDING["control"])
trace = bound(BINDING["current_trace"])
source = bound(BINDING["source_chain"])
terminal = bound(BINDING["full_body_falsifier"])
runner_path = (HERE / BINDING["workload_runner"]["path"]).resolve()
assert hashlib.sha256(runner_path.read_bytes()).hexdigest() == BINDING["workload_runner"]["sha256"]
runner = runner_path.read_text()

assert stack["model"]["id"] == "google/gemma-4-31B-it"
assert stack["model"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"]["requests"] == 32
assert stack["workload"]["concurrency"] == 32
assert stack["workload"]["completion_tokens_per_request"] == 358
assert stack["workload"]["cached_prompt_tokens_total"] == 17120
assert stack["workload"]["fresh_prompt_tokens_total"] == 117728
assert control["service_seconds_per_request"] == BINDING["control"]["service_seconds_per_request"]
boundaries = {row["boundary"]: row for row in trace["trace_attribution"]["boundaries"]}
assert boundaries["synchronization"]["wall_fraction"] == BINDING["current_trace"]["synchronization_fraction"]
assert boundaries["scheduler_gap"]["wall_fraction"] == BINDING["current_trace"]["scheduler_gap_fraction"]
assert boundaries["launch"]["wall_fraction"] == BINDING["current_trace"]["launch_fraction"]
contract = source["source_contract"]
assert "Tensor.tolist" in contract["host_result_boundary"]
assert "ModelRunner.sample" in contract["sampling_boundary"]
assert "ScheduleBatch.prepare_for_decode" in contract["host_next_step_boundary"]
assert terminal["classification"] == BINDING["full_body_falsifier"]["classification"]
assert terminal["full_body_discriminator"]["host_intervention_proven"] is True
assert terminal["full_body_discriminator"]["fewer_host_round_trips_pass"] is False
assert '"temperature": 0' in runner
assert '"seed": 20260718' in runner
assert '"ignore_eos": True' in runner
assert '"stream": True' in runner
change = BINDING["candidate_change"]
assert change["ring_slots"] == 2
assert change["one_token_scheduling"] is True
assert change["token_emission_batched_or_delayed"] is False
assert change["conditional_graph"] is False
assert change["continuous_decode_steps_changed"] is False
assert change["graph_launch_count_changed"] is False
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
