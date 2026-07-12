from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache


CONTEXT_TOKENS = 90_000
PAGE_TOKENS = 64
REQUEST_BYTES = 32
SEED = 20_260_712
CLUSTER_TARGETS = (1, 2, 4, 8, 16, 32, 64)

PATTERN_SPECS = {
    "sequential_stream": {
        "role": "negative_control",
        "provenance": "synthetic",
        "real_glm_trace": False,
        "selected_set_relation": "independent_sequential_control",
    },
    "gather_score_order": {
        "role": "synthetic_current_order_surrogate",
        "provenance": "synthetic",
        "real_glm_trace": False,
        "selected_set_relation": "same_set_as_gather_address_sorted",
        "ordering": "deterministic synthetic score rank over logical token positions",
    },
    "gather_address_sorted": {
        "role": "sorting_hypothesis",
        "provenance": "synthetic",
        "real_glm_trace": False,
        "selected_set_relation": "same_set_as_gather_score_order",
        "ordering": "ascending logical token position before transaction expansion",
        "physical_hbm_address_vector_lexicographic_sort": False,
    },
    **{
        f"gather_cluster_{target}": {
            "role": "page_aware_architecture_change_hypothesis",
            "provenance": "synthetic",
            "real_glm_trace": False,
            "selected_set_relation": "different_page_clustered_set",
            "target_tokens_per_page": target,
            "feasible_for_top2048_at_90k": target != 1,
        }
        for target in CLUSTER_TARGETS
    },
}

EXECUTABLE_PATTERN_IDS = (
    "sequential_stream",
    "gather_score_order",
    "gather_address_sorted",
    *(f"gather_cluster_{target}" for target in CLUSTER_TARGETS if target != 1),
)


@dataclass(frozen=True)
class TraceRecord:
    operation: str
    address: tuple[int, int, int, int, int, int, int]
    token_position: int
    transaction_index: int

    def render(self) -> str:
        return f"{self.operation} {','.join(str(value) for value in self.address)}"


def _rank(seed: int, namespace: str, value: int) -> int:
    payload = f"{seed}:{namespace}:{value}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


@lru_cache(maxsize=None)
def _base_selected_positions(
    seed: int, request_count: int, context_tokens: int
) -> tuple[int, ...]:
    if request_count > context_tokens:
        raise ValueError("request count exceeds context tokens")
    ranked = sorted(
        range(context_tokens), key=lambda token: (_rank(seed, "select", token), token)
    )
    return tuple(ranked[:request_count])


def _clustered_positions(
    seed: int,
    request_count: int,
    context_tokens: int,
    page_tokens: int,
    target: int,
) -> list[int]:
    if request_count % target:
        raise ValueError("request count must be divisible by cluster target")
    pages_needed = request_count // target
    full_page_count = context_tokens // page_tokens
    if pages_needed > full_page_count:
        raise ValueError(
            "cluster target is infeasible for unique tokens in this context"
        )
    pages = sorted(
        range(full_page_count), key=lambda page: (_rank(seed, "page", page), page)
    )[:pages_needed]
    positions: list[int] = []
    for page in pages:
        offsets = sorted(
            range(page_tokens),
            key=lambda offset: (_rank(seed ^ page, "offset", offset), offset),
        )[:target]
        positions.extend(page * page_tokens + offset for offset in offsets)
    positions.sort(key=lambda token: (_rank(seed, "score-order", token), token))
    return positions


def _token_to_address(
    token: int,
    page_tokens: int,
    transaction_index: int,
    transactions_per_token: int,
) -> tuple[int, int, int, int, int, int, int]:
    page = token // page_tokens
    offset = token % page_tokens
    bank_slot = page % 64
    bank = bank_slot % 4
    bankgroup = (bank_slot // 4) % 4
    sid = (bank_slot // 16) % 2
    pseudochannel = (bank_slot // 32) % 2
    if transactions_per_token == 1:
        row = page // 64
        column = offset * 4
    else:
        transactions_per_page = page_tokens * transactions_per_token
        rows_per_page = (transactions_per_page + 255) // 256
        linear = offset * transactions_per_token + transaction_index
        row = (page // 64) * rows_per_page + linear // 256
        column = linear % 256
    return (0, pseudochannel, sid, bankgroup, bank, row, column)


def generate_trace(
    pattern_id: str,
    request_count: int = 2048,
    seed: int = SEED,
    context_tokens: int = CONTEXT_TOKENS,
    page_tokens: int = PAGE_TOKENS,
    transactions_per_token: int = 1,
) -> list[TraceRecord]:
    if pattern_id not in PATTERN_SPECS:
        raise ValueError(f"unknown pattern: {pattern_id}")
    if request_count <= 0:
        raise ValueError("request count must be positive")
    if transactions_per_token <= 0:
        raise ValueError("transactions per token must be positive")
    if pattern_id == "sequential_stream":
        if request_count > context_tokens:
            raise ValueError("request count exceeds context tokens")
        positions = list(range(request_count))
    elif pattern_id in {"gather_score_order", "gather_address_sorted"}:
        positions = list(_base_selected_positions(seed, request_count, context_tokens))
        if pattern_id == "gather_address_sorted":
            positions.sort()
    else:
        target = int(pattern_id.rsplit("_", 1)[1])
        positions = _clustered_positions(
            seed, request_count, context_tokens, page_tokens, target
        )
    return [
        TraceRecord(
            "R",
            _token_to_address(
                token,
                page_tokens,
                transaction_index,
                transactions_per_token,
            ),
            token,
            transaction_index,
        )
        for token in positions
        for transaction_index in range(transactions_per_token)
    ]


def summarize_trace(
    records: list[TraceRecord], request_bytes: int = REQUEST_BYTES
) -> dict[str, object]:
    rendered = "\n".join(record.render() for record in records) + "\n"
    selected = sorted({record.token_position for record in records})
    selected_bytes = ",".join(str(token) for token in selected).encode()
    pages = Counter(token // PAGE_TOKENS for token in selected)
    transactions = Counter(record.token_position for record in records)
    transaction_counts = set(transactions.values())
    if len(transaction_counts) > 1:
        raise ValueError("selected tokens have unequal transaction counts")
    transactions_per_token = next(iter(transaction_counts), 0)
    counts = list(pages.values())
    read_count = sum(record.operation == "R" for record in records)
    write_count = sum(record.operation == "W" for record in records)
    return {
        "request_count": len(records),
        "read_count": read_count,
        "write_count": write_count,
        "request_bytes": request_bytes,
        "total_bytes": len(records) * request_bytes,
        "selected_token_count": len(selected),
        "unique_token_count": len(selected),
        "transactions_per_selected_token": transactions_per_token,
        "bytes_per_selected_token": transactions_per_token * request_bytes,
        "selected_page_count": len(pages),
        "tokens_per_selected_page_minimum": min(counts) if counts else 0,
        "tokens_per_selected_page_maximum": max(counts) if counts else 0,
        "selected_positions_sha256": hashlib.sha256(selected_bytes).hexdigest(),
        "ordered_trace_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
    }
