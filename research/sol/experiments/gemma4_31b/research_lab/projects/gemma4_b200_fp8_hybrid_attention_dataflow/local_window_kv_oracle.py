#!/usr/bin/env python3

import json
import math

PAGE_SIZE = 16
WINDOW_TOKENS = 1024
MAX_WINDOW_PAGES = math.ceil(WINDOW_TOKENS / PAGE_SIZE) + 1


def compact_page_table(seq_len: int, page_ids: list[int]) -> tuple[list[int], int]:
    first_page = max(0, (seq_len - WINDOW_TOKENS) // PAGE_SIZE)
    rebased_seq_len = seq_len - first_page * PAGE_SIZE
    num_pages = math.ceil(rebased_seq_len / PAGE_SIZE)
    compacted = page_ids[first_page : first_page + num_pages]
    compacted.extend([-1] * (MAX_WINDOW_PAGES - len(compacted)))
    return compacted, rebased_seq_len


def verify_case(seq_len: int) -> dict[str, int | bool]:
    page_ids = [10_000 + index * 7 for index in range(max(65, math.ceil(seq_len / 16)))]
    compacted, rebased_seq_len = compact_page_table(seq_len, page_ids)
    first_page = (seq_len - rebased_seq_len) // PAGE_SIZE
    visible_start = max(0, seq_len - WINDOW_TOKENS)
    for absolute_position in range(visible_start, seq_len):
        baseline = (
            page_ids[absolute_position // PAGE_SIZE],
            absolute_position % PAGE_SIZE,
        )
        rebased_position = absolute_position - first_page * PAGE_SIZE
        candidate = (
            compacted[rebased_position // PAGE_SIZE],
            rebased_position % PAGE_SIZE,
        )
        if baseline != candidate:
            raise AssertionError((seq_len, absolute_position, baseline, candidate))
    valid_pages = math.ceil(rebased_seq_len / PAGE_SIZE)
    if any(page_id != -1 for page_id in compacted[valid_pages:]):
        raise AssertionError("padding pages must be -1")
    return {
        "seq_len": seq_len,
        "first_page": first_page,
        "rebased_seq_len": rebased_seq_len,
        "valid_pages": valid_pages,
        "visible_tokens": seq_len - visible_start,
        "mapping_equal": True,
    }


def run_oracle() -> dict:
    boundary_lengths = [0, 1, 15, 16, 1023, 1024, 1025, 4214, 4224, 4571]
    boundary_cases = [verify_case(seq_len) for seq_len in boundary_lengths]
    production_cases = [verify_case(seq_len) for seq_len in range(4214, 4572)]
    page_counts = [case["valid_pages"] for case in production_cases]
    zero_case = boundary_cases[0]
    if zero_case["rebased_seq_len"] != 0 or zero_case["valid_pages"] != 0:
        raise AssertionError("zero-length padded request must remain empty")
    return {
        "schema_version": 1,
        "semantic_class": "page_table_rebase_preserves_visible_absolute_kv_slots",
        "page_size": PAGE_SIZE,
        "window_tokens": WINDOW_TOKENS,
        "max_window_pages": MAX_WINDOW_PAGES,
        "boundary_cases": boundary_cases,
        "production": {
            "steps": len(production_cases),
            "min_pages": min(page_counts),
            "max_pages": max(page_counts),
            "page_count_64": page_counts.count(64),
            "page_count_65": page_counts.count(65),
            "sum_pages": sum(page_counts),
            "all_mappings_equal": all(
                bool(case["mapping_equal"]) for case in production_cases
            ),
        },
        "cuda_graph_padding": {
            "seq_len": 0,
            "rebased_seq_len": zero_case["rebased_seq_len"],
            "valid_pages": zero_case["valid_pages"],
            "all_page_ids_negative": True,
            "append_slot_mapping_contract": "unchanged_negative_slot_no_op",
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_oracle(), indent=2, sort_keys=True))
