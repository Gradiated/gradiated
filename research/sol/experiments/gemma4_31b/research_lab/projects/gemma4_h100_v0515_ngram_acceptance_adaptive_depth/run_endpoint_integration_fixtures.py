#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json
from pathlib import Path

from adaptive_depth_contract import ContractError, ProducerRequest
from endpoint_integration import AdaptiveDepthEndpointLifecycle

ROOT = Path(__file__).resolve().parent


def requests(count: int, generation: int = 0, namespace: str = "request") -> tuple[ProducerRequest, ...]:
    return tuple(
        ProducerRequest(
            rid=f"{namespace}-{i}", seq_len=16 + i + generation,
            tail_tokens=(100 + i, 200 + generation, 300 + i),
            prefix_kv=tuple(10_000 * (i + 1) + j for j in range(16 + i + generation)),
            out_cache_base=1_000_000 + 100 * i + 20 * generation,
        ) for i in range(count)
    )


def paths(ids, depth):
    return {rid: tuple(range(1 + (i % min(depth, 4)))) for i, rid in enumerate(ids)}


def fail(name, fn):
    try: fn()
    except ContractError as e: return {"name": name, "result": "fail_closed", "error": str(e)}
    raise AssertionError(f"fixture_did_not_fail:{name}")


def main():
    life = AdaptiveDepthEndpointLifecycle()
    evidence = []
    b1 = life.run_cycle(requests(1), paths(["request-0"], 12))
    b7 = life.run_cycle(requests(7), paths([f"request-{i}" for i in range(7)], 12))
    b8 = life.run_cycle(requests(8, 1), paths([f"request-{i}" for i in range(8)], 6))
    b7back = life.run_cycle(requests(7, 2), paths([f"request-{i}" for i in range(7)], 12))
    assert (b1.batch.depth, b7.batch.depth, b8.batch.depth, b7back.batch.depth) == (12, 12, 6, 12)
    evidence.append({"name": "threshold_1_7_8_7", "result": "pass", "depths": [12, 12, 6, 12]})
    scale = AdaptiveDepthEndpointLifecycle()
    scale_batch = scale.run_cycle(requests(23, 20), paths([f"request-{i}" for i in range(23)], 6))
    assert scale_batch.batch.depth == 6 and scale_batch.batch.target_rows == 138
    evidence.append({"name": "eight_and_above", "result": "pass", "batch_size": 23, "depth": 6, "target_rows": 138})

    perm = (7, 0, 6, 1, 5, 2, 4, 3)
    high = requests(8, 3)
    permuted = tuple(high[i] for i in perm)
    a = life.run_cycle(high, paths([r.rid for r in high], 6))
    p = life.run_cycle(permuted, paths([r.rid for r in permuted], 6))
    assert all(a.batch.draft_tokens[a.batch.request_row_slice(i)] == p.batch.draft_tokens[p.batch.request_row_slice(j)] for j, i in enumerate(perm))
    evidence.append({"name": "permutation", "result": "pass", "order": perm})

    flow = AdaptiveDepthEndpointLifecycle()
    cancelled = flow.run_cycle(requests(8, 4), paths([f"request-{i}" for i in range(8)], 6), cancelled={"request-2"})
    completed = flow.run_cycle(requests(8, 5), paths([f"request-{i}" for i in range(8)], 6), completed={"request-0", "request-6"})
    assert cancelled.scheduler_rows["request-2"] == () and completed.scheduler_rows["request-0"] == ()
    evidence.append({"name": "cancellation_completion", "result": "pass"})

    empty_match = flow.run_cycle(requests(8, 6), {f"request-{i}": (0,) for i in range(8)})
    partial = flow.run_cycle(requests(8, 7), {f"request-{i}": ((0, 1) if i % 2 else (0,)) for i in range(8)})
    assert all(x == 1 for x in empty_match.carrier.accept_lens) and partial.batch.depth == 6
    evidence.append({"name": "empty_and_partial_match_bonus_only", "result": "pass", "empty_accept_lens": empty_match.carrier.accept_lens})

    slots = AdaptiveDepthEndpointLifecycle()
    slots.run_cycle(requests(1, 8, "slot"), {"slot-0": (0,)}, completed={"slot-0"})
    generation = slots.reuse_slot(requests(1, 9, "slot")[0])
    assert generation == 0
    reused = slots.run_cycle(requests(1, 9, "slot"), {"slot-0": (0,)})
    assert reused.batch.depth == 12
    evidence.append({"name": "reused_slot", "result": "pass", "generation": generation})

    failures = [
        fail("empty_batch", lambda: slots.run_cycle((), {})),
        fail("duplicate_ids", lambda: slots.run_cycle((requests(1)[0], requests(1)[0]), {"request-0": (0,)})),
        fail("unknown_completion", lambda: slots.run_cycle(requests(1, 10, "fail"), {"fail-0": (0,)}, completed={"not-present"})),
        fail("live_slot_reuse", lambda: slots.reuse_slot(requests(1, 11, "slot")[0])),
    ]
    assert all(row["result"] == "fail_closed" for row in failures)
    evidence.append({"name": "fail_closed", "result": "pass", "cases": failures})

    result = {
        "schema_version": 1,
        "result": "endpoint_ready_offline",
        "evidence_label": "project_local_endpoint_lifecycle_cpu_state_fixtures",
        "provider_gpu_seconds": 0,
        "endpoint_requests_submitted": 0,
        "endpoint_or_economic_claim": False,
        "fixtures": evidence,
        "frozen_rule": {"batches_1_through_7": 12, "batches_8_plus": 6, "graph_depth": 12, "fallback_depth": 6},
        "source_tree": "inputs/candidate-v0.5.15/source/python/sglang",
    }
    (ROOT / "ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__": main()
