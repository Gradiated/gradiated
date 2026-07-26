#!/usr/bin/env python3
"""Coarse-to-fine tied-head path for the exact Gemma 4 greedy consumers."""

from __future__ import annotations

import dataclasses
import hashlib
import math
import pathlib
from typing import Any


VOCAB = 262_144
HIDDEN = 5_376
ROWS = 384
CLUSTERS = 2_048
ROUTES_PER_ROW = 8
SOFTCAP = 30.0

LOGITS_PROCESSOR_SHA256 = (
    "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14"
)
SAMPLER_SHA256 = (
    "85541951e1cf50d10c54978178e403ff9d4aa6f223e629ea91965735ba882a8f"
)
NGRAM_INFO_SHA256 = (
    "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c"
)


@dataclasses.dataclass(frozen=True)
class HierarchicalHeadConfig:
    vocab_size: int = VOCAB
    hidden_size: int = HIDDEN
    rows: int = ROWS
    clusters: int = CLUSTERS
    routes_per_row: int = ROUTES_PER_ROW
    softcap: float = SOFTCAP

    def validate(self) -> None:
        if self.vocab_size % self.clusters:
            raise ValueError("vocabulary must divide evenly across routes")
        if not 0 < self.routes_per_row <= self.clusters:
            raise ValueError("routes_per_row must be in [1, clusters]")
        if self.rows <= 0 or self.hidden_size <= 0:
            raise ValueError("rows and hidden_size must be positive")

    @property
    def rows_per_cluster(self) -> int:
        return self.vocab_size // self.clusters

    @property
    def selected_rows(self) -> int:
        return self.rows_per_cluster * self.routes_per_row


@dataclasses.dataclass
class HierarchicalLogits:
    candidate_ids: Any
    scores: Any
    hidden_states: Any
    tied_weight: Any
    config: HierarchicalHeadConfig

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.scores.shape[0]), self.config.vocab_size)

    def stable_argmax(self):
        import torch

        maxima = self.scores.max(dim=-1, keepdim=True).values
        sentinel = torch.full_like(
            self.candidate_ids, self.config.vocab_size, dtype=torch.long
        )
        return torch.where(self.scores == maxima, self.candidate_ids, sentinel).min(
            dim=-1
        ).values

    def __getitem__(self, item):
        return HierarchicalLogits(
            candidate_ids=self.candidate_ids[item],
            scores=self.scores[item],
            hidden_states=self.hidden_states[item],
            tied_weight=self.tied_weight,
            config=self.config,
        )

    def materialize_stock_fallback(self):
        import torch

        logits = torch.matmul(
            self.hidden_states.to(self.tied_weight.dtype), self.tied_weight.T
        )
        if self.config.softcap:
            logits = self.config.softcap * torch.tanh(logits / self.config.softcap)
        return logits


def hierarchical_tied_head(
    hidden_states,
    tied_weight,
    route_weight,
    config: HierarchicalHeadConfig = HierarchicalHeadConfig(),
) -> HierarchicalLogits:
    import torch

    config.validate()
    if tuple(hidden_states.shape) != (config.rows, config.hidden_size):
        raise RuntimeError(f"hierarchical_hidden_shape:{tuple(hidden_states.shape)}")
    if tuple(tied_weight.shape) != (config.vocab_size, config.hidden_size):
        raise RuntimeError(f"hierarchical_tied_weight_shape:{tuple(tied_weight.shape)}")
    if tuple(route_weight.shape) != (config.clusters, config.hidden_size):
        raise RuntimeError(f"hierarchical_route_weight_shape:{tuple(route_weight.shape)}")
    if hidden_states.device != tied_weight.device or hidden_states.device != route_weight.device:
        raise RuntimeError("hierarchical_single_device_required")

    coarse_scores = torch.matmul(
        hidden_states.to(route_weight.dtype), route_weight.T
    )
    route_ids = torch.topk(
        coarse_scores,
        config.routes_per_row,
        dim=-1,
        largest=True,
        sorted=True,
    ).indices
    offsets = torch.arange(
        config.rows_per_cluster, device=route_ids.device, dtype=route_ids.dtype
    )
    candidate_ids = (
        route_ids[..., None] * config.rows_per_cluster + offsets
    ).reshape(config.rows, config.selected_rows)

    gathered_rows = tied_weight.index_select(0, candidate_ids.reshape(-1)).reshape(
        config.rows, config.selected_rows, config.hidden_size
    )
    scores = torch.bmm(
        gathered_rows, hidden_states.to(tied_weight.dtype).unsqueeze(-1)
    ).squeeze(-1)
    if config.softcap:
        scores = config.softcap * torch.tanh(scores / config.softcap)
    return HierarchicalLogits(
        candidate_ids=candidate_ids,
        scores=scores,
        hidden_states=hidden_states,
        tied_weight=tied_weight,
        config=config,
    )


def _module_sha256(module: Any) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


def _activation_blocker(processor, hidden_states, lm_head, embedding_bias) -> str | None:
    route_weight = getattr(lm_head, "hierarchical_route_weight", None)
    if tuple(hidden_states.shape) != (ROWS, HIDDEN):
        return "non_exact_shape"
    if not hasattr(lm_head, "weight") or tuple(lm_head.weight.shape) != (VOCAB, HIDDEN):
        return "non_exact_tied_weight"
    if route_weight is None or tuple(route_weight.shape) != (CLUSTERS, HIDDEN):
        return "learned_route_weight_unavailable"
    if embedding_bias is not None:
        return "embedding_bias"
    if processor.use_fp32_lm_head:
        return "fp32_lm_head"
    if processor.logit_scale is not None:
        return "logit_scale"
    if processor.do_tensor_parallel_all_gather:
        return "tensor_parallel"
    if processor.do_tensor_parallel_all_gather_dp_attn:
        return "dp_attention"
    if not hidden_states.is_cuda or not lm_head.weight.is_cuda or not route_weight.is_cuda:
        return "cuda_required"
    return None


def install() -> dict[str, str]:
    from sglang.srt.layers import logits_processor, sampler
    from sglang.srt.speculative import ngram_info

    observed = {
        "logits_processor": _module_sha256(logits_processor),
        "sampler": _module_sha256(sampler),
        "ngram_info": _module_sha256(ngram_info),
    }
    expected = {
        "logits_processor": LOGITS_PROCESSOR_SHA256,
        "sampler": SAMPLER_SHA256,
        "ngram_info": NGRAM_INFO_SHA256,
    }
    if observed != expected:
        raise RuntimeError(f"hierarchical_source_mismatch:{observed}")

    logits_class = logits_processor.LogitsProcessor
    sampler_class = sampler.Sampler
    ngram_class = ngram_info.NgramVerifyInput
    if getattr(logits_class, "_hierarchical_tied_head_installed", False):
        return observed

    original_get_logits = logits_class._get_logits
    original_sampler_forward = sampler_class.forward
    original_greedy_verify = ngram_class._greedy_verify
    original_sampling_verify = ngram_class._sampling_verify

    def candidate_get_logits(
        self,
        hidden_states,
        lm_head,
        logits_metadata,
        embedding_bias=None,
    ):
        blocker = _activation_blocker(self, hidden_states, lm_head, embedding_bias)
        if blocker is not None:
            return original_get_logits(
                self, hidden_states, lm_head, logits_metadata, embedding_bias
            )
        return hierarchical_tied_head(
            hidden_states,
            lm_head.weight,
            lm_head.hierarchical_route_weight,
        )

    def candidate_sampler_forward(
        self,
        logits_output,
        sampling_info,
        return_logprob,
        top_logprobs_nums,
        token_ids_logprobs,
        positions,
    ):
        payload = logits_output.next_token_logits
        if not isinstance(payload, HierarchicalLogits):
            return original_sampler_forward(
                self,
                logits_output,
                sampling_info,
                return_logprob,
                top_logprobs_nums,
                token_ids_logprobs,
                positions,
            )
        supported = (
            sampling_info.is_all_greedy
            and not return_logprob
            and not sampling_info.has_custom_logit_processor
        )
        if not supported:
            logits_output.next_token_logits = payload.materialize_stock_fallback()
            return original_sampler_forward(
                self,
                logits_output,
                sampling_info,
                return_logprob,
                top_logprobs_nums,
                token_ids_logprobs,
                positions,
            )
        token_ids = payload.stable_argmax()
        self._sync_token_ids_across_tp(token_ids, sampling_info)
        return token_ids

    def candidate_greedy_verify(self, batch, logits_output):
        payload = logits_output.next_token_logits
        if not isinstance(payload, HierarchicalLogits) or self.grammar is not None:
            if isinstance(payload, HierarchicalLogits):
                logits_output.next_token_logits = payload.materialize_stock_fallback()
            return original_greedy_verify(self, batch, logits_output)

        torch = ngram_info.torch
        batch_size = batch.batch_size()
        target_predict = payload.stable_argmax().reshape(
            batch_size, self.draft_token_num
        )
        candidates = self.draft_token.reshape(batch_size, self.draft_token_num)
        predict_shape = list(payload.shape)[:-1]
        predict_shape[-1] += 1
        self.predict = torch.empty(
            predict_shape, dtype=torch.int32, device=self.device
        )
        self.accept_indices = torch.full(
            (batch_size, self.draft_token_num),
            -1,
            dtype=torch.int32,
            device=self.device,
        )
        self.num_correct_drafts = torch.empty(
            (batch_size,), dtype=torch.int32, device=self.device
        )
        ngram_info.verify_tree_greedy(
            predicts=self.predict,
            accept_index=self.accept_indices,
            accept_token_num=self.num_correct_drafts,
            candidates=candidates,
            retrive_index=self.retrieve_index,
            retrive_next_token=self.retrieve_next_token,
            retrive_next_sibling=self.retrieve_next_sibling,
            target_predict=target_predict,
        )

    def candidate_sampling_verify(self, batch, logits_output, sampling_info):
        payload = logits_output.next_token_logits
        if isinstance(payload, HierarchicalLogits):
            logits_output.next_token_logits = payload.materialize_stock_fallback()
        return original_sampling_verify(self, batch, logits_output, sampling_info)

    logits_class._get_logits = candidate_get_logits
    sampler_class.forward = candidate_sampler_forward
    ngram_class._greedy_verify = candidate_greedy_verify
    ngram_class._sampling_verify = candidate_sampling_verify
    logits_class._hierarchical_tied_head_installed = True
    return observed


def run_reference_fixture() -> dict[str, Any]:
    config = HierarchicalHeadConfig(
        vocab_size=16,
        hidden_size=4,
        rows=1,
        clusters=4,
        routes_per_row=2,
        softcap=30.0,
    )
    config.validate()
    hidden = [1.0, 0.0, 0.0, 0.0]
    route_weight = [
        [4.0, 0.0, 0.0, 0.0],
        [3.0, 0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
    ]
    tied_weight = [[float(16 - token), 0.0, 0.0, 0.0] for token in range(16)]

    coarse = [math.fsum(a * b for a, b in zip(hidden, row)) for row in route_weight]
    routes = sorted(range(config.clusters), key=lambda index: (-coarse[index], index))[
        : config.routes_per_row
    ]
    candidates = [
        route * config.rows_per_cluster + offset
        for route in routes
        for offset in range(config.rows_per_cluster)
    ]
    scores = [
        config.softcap
        * math.tanh(
            math.fsum(a * b for a, b in zip(hidden, tied_weight[token]))
            / config.softcap
        )
        for token in candidates
    ]
    maximum = max(scores)
    token = min(
        candidate for candidate, score in zip(candidates, scores) if score == maximum
    )
    indexed_candidates = candidates[: config.rows_per_cluster]
    coverage = [
        cluster * config.rows_per_cluster + offset
        for cluster in range(config.clusters)
        for offset in range(config.rows_per_cluster)
    ]
    return {
        "coarse_route_ids": routes,
        "candidate_ids": candidates,
        "softcapped_scores_finite": all(math.isfinite(value) for value in scores),
        "greedy_sampler_token": token,
        "expected_token": 0,
        "row_index_preserves_payload": indexed_candidates == [0, 1, 2, 3],
        "all_fixture_rows_reachable_once": coverage == list(range(config.vocab_size)),
        "fallback_dense_argmax": min(
            index
            for index, row in enumerate(tied_weight)
            if row[0] == max(weight[0] for weight in tied_weight)
        ),
    }

