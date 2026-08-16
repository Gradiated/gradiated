#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = json.loads((HERE / "DIRECTOR_BINDING.json").read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


control = (HERE / BINDING["control"]["path"]).resolve()
stack_path = (HERE / BINDING["stack_binding"]["path"]).resolve()
stack = json.loads(stack_path.read_text())
terminal = json.loads(control.read_text())

assert digest(control) == BINDING["control"]["sha256"]
assert digest(stack_path) == BINDING["stack_binding"]["sha256"]
assert f'{stack["model"]["id"]}@{stack["model"]["revision"]}' == BINDING["model"]
assert stack["model"]["checkpoint_index_sha256"] == BINDING["checkpoint_index_sha256"]
assert stack["runtime"]["release"] == BINDING["runtime"]["release"]
assert stack["runtime"]["commit"] == BINDING["runtime"]["commit"]
assert stack["runtime"]["image_linux_amd64"] == BINDING["runtime"]["image"]
assert stack["workload"] == BINDING["workload"]
assert terminal["batch_seconds"] == BINDING["control"]["batch_seconds"]
assert terminal["service_seconds_per_request"] == BINDING["control"]["service_seconds_per_request"]
assert terminal["complete_requests"] == BINDING["workload"]["requests"]
assert int(terminal["cache"]["cached_prompt_tokens_delta"]) == BINDING["workload"]["cached_prompt_tokens_total"]
assert int(terminal["cache"]["uncached_prompt_tokens_delta"]) == BINDING["workload"]["fresh_prompt_tokens_total"]
print(json.dumps({"pass": True, "binding": "DIRECTOR_BINDING.json"}, sort_keys=True))

