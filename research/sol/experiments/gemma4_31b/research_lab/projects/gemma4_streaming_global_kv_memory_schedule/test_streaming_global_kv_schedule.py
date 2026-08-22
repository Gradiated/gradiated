from __future__ import annotations

import copy

import torch

import multiresolution_global_kv as activated
from streaming_global_kv_schedule import LayerRequest, forward_layer_local_inplace


def _state_for(
    k: torch.Tensor,
    v: torch.Tensor,
    query_start: int,
    protected_positions=(),
):
    state = activated.IncrementalGlobalSummaryState(protected_positions)
    state.append_committed(k[:query_start], v[:query_start])
    return state


def test_c32_layer_local_matches_activated_consumer() -> None:
    torch.manual_seed(17)
    requests = []
    references = []
    query_start = 16
    for _ in range(32):
        k = torch.randn(query_start + 1, 4, 512, dtype=torch.bfloat16)
        v = torch.randn_like(k)
        q = torch.randn(1, 32, 512, dtype=torch.bfloat16)
        state = _state_for(k, v, query_start)
        reference_state = copy.deepcopy(state)
        references.append(
            activated.multiresolution_global_attention(
                "decode",
                q.clone(),
                k,
                v,
                query_start,
                summary_state=reference_state,
                commit_after_consume=True,
            )
        )
        requests.append(
            LayerRequest(
                phase="decode",
                q=q,
                exact_post_rope_k=k,
                exact_v=v,
                query_start=query_start,
                summary_state=state,
            )
        )

    telemetry = forward_layer_local_inplace(requests)

    assert telemetry == {
        "requests": 32,
        "processed_query_rows": 32,
        "peak_live_request_materializations": 1,
        "peak_compact_tokens": 10,
    }
    for request, reference in zip(requests, references, strict=True):
        torch.testing.assert_close(request.q, reference, rtol=0, atol=0.00390625)
        assert request.summary_state.committed_tokens == query_start + 1


def test_summary_boundary_matches_activated_consumer() -> None:
    torch.manual_seed(23)
    query_start = 513
    k = torch.randn(query_start + 1, 4, 512, dtype=torch.bfloat16)
    v = torch.randn_like(k)
    q = torch.randn(1, 32, 512, dtype=torch.bfloat16)
    state = _state_for(k, v, query_start)
    reference_state = copy.deepcopy(state)
    reference = activated.multiresolution_global_attention(
        "decode",
        q.clone(),
        k,
        v,
        query_start,
        summary_state=reference_state,
        commit_after_consume=True,
    )

    telemetry = forward_layer_local_inplace(
        [
            LayerRequest(
                phase="decode",
                q=q,
                exact_post_rope_k=k,
                exact_v=v,
                query_start=query_start,
                summary_state=state,
            )
        ]
    )

    torch.testing.assert_close(q, reference, rtol=0, atol=0.00390625)
    assert telemetry["peak_compact_tokens"] == 10


def test_measured_c1_compact_geometry_matches_activated_consumer() -> None:
    torch.manual_seed(29)
    query_start = 4_609
    protected_positions = tuple(range(8))
    k = torch.randn(query_start + 1, 4, 512, dtype=torch.bfloat16)
    v = torch.randn_like(k)
    q = torch.randn(1, 32, 512, dtype=torch.bfloat16)
    state = _state_for(k, v, query_start, protected_positions)
    reference_state = copy.deepcopy(state)
    reference = activated.multiresolution_global_attention(
        "decode",
        q.clone(),
        k,
        v,
        query_start,
        summary_state=reference_state,
        protected_positions=protected_positions,
        commit_after_consume=True,
    )

    telemetry = forward_layer_local_inplace(
        [
            LayerRequest(
                phase="decode",
                q=q,
                exact_post_rope_k=k,
                exact_v=v,
                query_start=query_start,
                summary_state=state,
                protected_positions=protected_positions,
            )
        ]
    )

    torch.testing.assert_close(q, reference, rtol=0, atol=0.00390625)
    assert telemetry["peak_compact_tokens"] == 26
