#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


binding = json.loads((HERE / "DIRECTOR_BINDING.json").read_text())
checks = (
    (binding["checkpoint"]["manifest_path"], binding["checkpoint"]["manifest_sha256"]),
    (binding["closed_predecessor"]["path"], binding["closed_predecessor"]["sha256"]),
    (
        binding["consumed_direct_replay_component"]["path"],
        binding["consumed_direct_replay_component"]["sha256"],
    ),
    (binding["comparator"]["path"], binding["comparator"]["sha256"]),
    (binding["workload"]["runner_path"], binding["workload"]["runner_sha256"]),
    (
        binding["dependency_supergraph_intervention"]["sitecustomize_path"],
        binding["dependency_supergraph_intervention"]["sitecustomize_sha256"],
    ),
    (
        binding["dependency_supergraph_intervention"]["remote_worker_path"],
        binding["dependency_supergraph_intervention"]["remote_worker_sha256"],
    ),
    (
        binding["dependency_supergraph_intervention"]["analyzer_path"],
        binding["dependency_supergraph_intervention"]["analyzer_sha256"],
    ),
    (
        binding["dependency_supergraph_intervention"][
            "cuda_graph_runner_source_path"
        ],
        binding["dependency_supergraph_intervention"][
            "cuda_graph_runner_source_sha256"
        ],
    ),
    (
        binding["dependency_supergraph_intervention"][
            "triton_backend_source_path"
        ],
        binding["dependency_supergraph_intervention"][
            "triton_backend_source_sha256"
        ],
    ),
)
for relative_path, expected in checks:
    path = (HERE / relative_path).resolve()
    observed = sha256(path)
    if observed != expected:
        raise SystemExit(f"binding mismatch: {path}: {observed} != {expected}")

assert binding["checkpoint"]["identity"] == (
    "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
)
assert binding["runtime"]["image"] == (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
assert binding["candidate"]["concurrency"] == 32
assert binding["candidate"]["decode_block_tokens"] == 8
assert binding["candidate"]["total_completion_tokens_per_request"] == 358
assert binding["comparator"]["service_seconds_per_request"] == 0.6556567115001144
assert binding["workload"]["cached_prompt_tokens"] == 17120
assert binding["workload"]["fresh_prompt_tokens"] == 117728
print(json.dumps({"binding": "valid", "decode_block_tokens": 8, "concurrency": 32}))
