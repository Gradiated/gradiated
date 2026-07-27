from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


PHYSICAL_BYTES = 48_305_799_168
MEM_FRACTION_STATIC = Decimal("0.953")
STATIC_LIMIT_BYTES = int(Decimal(PHYSICAL_BYTES) * MEM_FRACTION_STATIC)
DYNAMIC_RESERVE_BYTES = PHYSICAL_BYTES - STATIC_LIMIT_BYTES

CONCURRENCY = 32
SHARED_PREFIX_TOKENS = 535
PROMPT_TOKENS = 4_214
OUTPUT_TOKENS = 358
MAX_SEQUENCE_TOKENS = PROMPT_TOKENS + OUTPUT_TOKENS - 1
WINDOW = 1_024
CHUNKED_PREFILL_TOKENS = 2_048
PHYSICAL_CAPACITY = 129_688
PEAK_LIVE_PHYSICAL_ROWS = 129_687
LOCAL_CAPACITY = CONCURRENCY * WINDOW
RECENT_CAPACITY = LOCAL_CAPACITY + CHUNKED_PREFILL_TOKENS
OLD_CAPACITY = PEAK_LIVE_PHYSICAL_ROWS - LOCAL_CAPACITY

LOCAL_LAYER_IDS = tuple(i for i in range(60) if i % 6 != 5)
GLOBAL_LAYER_IDS = tuple(i for i in range(60) if i % 6 == 5)


def exact_memory_ledger() -> dict:
    static_components = {
        "transformer_linear_e4m3": 29_396_828_160,
        "tied_embedding_lm_head_bf16": 2_818_572_288,
        "local_kv4_payload_including_page_one_sentinel": 7_549_977_600,
        "global_recent_e5m2_payload": 1_426_063_360,
        "global_old_kv4_outlier_payload": 2_295_041_920,
        "global_two_int32_physical_directories": 1_037_504,
        "global_old_and_recent_int32_free_stacks": 526_940,
    }
    static_lower = sum(static_components.values())
    static_uncertainty = {
        "all_other_checkpoint_tensors": {"lower": 0, "upper": 933_949_144},
        "fp8_weight_scales": {"lower": 0, "upper": 16_777_216},
        "global_eight_allocation_rounding": {"lower": 0, "upper": 16_777_216},
    }
    static_upper = static_lower + sum(
        row["upper"] for row in static_uncertainty.values()
    )

    context_lower = 1_184_639_222
    context_upper = 1_195_376_640
    graphs_lower = 896_574_423
    graphs_upper = 907_311_842
    workspace = 8_421_376
    assigned_dynamic_lower = context_lower + graphs_lower + workspace
    assigned_dynamic_upper = context_upper + graphs_upper + workspace
    unassigned_upper = DYNAMIC_RESERVE_BYTES - assigned_dynamic_lower
    unassigned_lower = 0

    return {
        "physical_bytes": PHYSICAL_BYTES,
        "split": {
            "mem_fraction_static": str(MEM_FRACTION_STATIC),
            "static_limit_bytes": STATIC_LIMIT_BYTES,
            "dynamic_reserve_bytes": DYNAMIC_RESERVE_BYTES,
            "identity": "static_limit_bytes + dynamic_reserve_bytes == physical_bytes",
        },
        "static": {
            "components_bytes": static_components,
            "uncertainty_bytes": static_uncertainty,
            "required_interval_bytes": {"lower": static_lower, "upper": static_upper},
            "margin_interval_bytes": {
                "lower": STATIC_LIMIT_BYTES - static_upper,
                "upper": STATIC_LIMIT_BYTES - static_lower,
            },
        },
        "dynamic": {
            "assigned_components_bytes": {
                "context_runtime_interval": {
                    "lower": context_lower,
                    "upper": context_upper,
                },
                "c32_cuda_graph_interval": {
                    "lower": graphs_lower,
                    "upper": graphs_upper,
                },
                "decode_split_workspace": {
                    "lower": workspace,
                    "upper": workspace,
                },
                "scheduler_metadata_allocator_fragmentation_and_unitemized_runtime": {
                    "lower": unassigned_lower,
                    "upper": unassigned_upper,
                },
            },
            "required_conservative_interval_bytes": {
                "lower": assigned_dynamic_lower,
                "upper": DYNAMIC_RESERVE_BYTES,
            },
            "margin_interval_bytes": {
                "lower": 0,
                "upper": DYNAMIC_RESERVE_BYTES - assigned_dynamic_lower,
            },
            "observed_assigned_only_margin_interval_bytes": {
                "lower": DYNAMIC_RESERVE_BYTES - assigned_dynamic_upper,
                "upper": DYNAMIC_RESERVE_BYTES - assigned_dynamic_lower,
            },
        },
        "complete_physical": {
            "required_interval_bytes": {
                "lower": static_lower + DYNAMIC_RESERVE_BYTES,
                "upper": static_upper + DYNAMIC_RESERVE_BYTES,
            },
            "margin_interval_bytes": {
                "lower": PHYSICAL_BYTES - static_upper - DYNAMIC_RESERVE_BYTES,
                "upper": PHYSICAL_BYTES - static_lower - DYNAMIC_RESERVE_BYTES,
            },
            "fit": static_upper <= STATIC_LIMIT_BYTES,
            "non_double_counting": (
                "dynamic context, graphs, workspace, scheduler metadata, runtime "
                "allocator fragmentation, and other transient state are partitioned "
                "inside the 0.047 reserve and never added above it"
            ),
        },
    }


def physical_rows(concurrency: int, sequence_tokens: int) -> int:
    if concurrency < 1 or concurrency > CONCURRENCY:
        raise ValueError("concurrency must be in [1, 32]")
    if sequence_tokens < SHARED_PREFIX_TOKENS:
        raise ValueError("sequence shorter than the frozen shared prefix")
    return SHARED_PREFIX_TOKENS + concurrency * (
        sequence_tokens - SHARED_PREFIX_TOKENS
    )


def validate_layer_schedule(layer_types: Iterable[str]) -> None:
    values = tuple(layer_types)
    if len(values) != 60:
        raise ValueError("Gemma 4 composition requires exactly 60 layers")
    for layer_id, layer_type in enumerate(values):
        expected = "full_attention" if layer_id in GLOBAL_LAYER_IDS else "sliding_attention"
        if layer_type != expected:
            raise ValueError(
                f"layer {layer_id} must be {expected}, got {layer_type}"
            )


@dataclass(frozen=True)
class Transition:
    physical: int
    recent: int
    old: int


class CanonicalTierDirectory:
    def __init__(
        self,
        physical_capacity: int = PHYSICAL_CAPACITY,
        recent_capacity: int = RECENT_CAPACITY,
        old_capacity: int = OLD_CAPACITY,
    ):
        self.physical_capacity = physical_capacity
        self.recent_locations = [-1] * physical_capacity
        self.old_locations = [-1] * physical_capacity
        self.generations = [0] * physical_capacity
        self._free_recent = list(range(recent_capacity - 1, -1, -1))
        self._free_old = list(range(old_capacity - 1, -1, -1))
        self._pending: tuple[Transition, ...] = ()

    @property
    def available_recent(self) -> int:
        return len(self._free_recent)

    @property
    def available_old(self) -> int:
        return len(self._free_old)

    def _valid(self, physical: int) -> bool:
        if physical < 0:
            return False
        if physical >= self.physical_capacity:
            raise IndexError(f"physical page {physical} outside directory")
        return True

    def _allocate_recent(self, physical: int) -> int:
        if self.recent_locations[physical] >= 0:
            return self.recent_locations[physical]
        if self.old_locations[physical] >= 0:
            raise RuntimeError("an old page cannot be rewritten as recent")
        if not self._free_recent:
            raise RuntimeError("recent compact arena exhausted")
        location = self._free_recent.pop()
        self.recent_locations[physical] = location
        return location

    def _allocate_old(self, physical: int) -> int:
        if self.old_locations[physical] >= 0:
            return self.old_locations[physical]
        if not self._free_old:
            raise RuntimeError("old compact arena exhausted")
        location = self._free_old.pop()
        self.old_locations[physical] = location
        return location

    def route_new(
        self, recent_physical: Iterable[int], old_physical: Iterable[int]
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        recent = tuple(
            (physical, self._allocate_recent(physical))
            for physical in recent_physical
            if self._valid(physical)
        )
        old = tuple(
            (physical, self._allocate_old(physical))
            for physical in old_physical
            if self._valid(physical)
        )
        return recent, old

    def begin_transition(self, physical_pages: Iterable[int]) -> tuple[Transition, ...]:
        if self._pending:
            raise RuntimeError("the prior ten-global-layer transition is incomplete")
        transitions = []
        for physical in physical_pages:
            if not self._valid(physical):
                continue
            recent = self.recent_locations[physical]
            if recent < 0:
                if self.old_locations[physical] >= 0:
                    continue
                raise RuntimeError("transition source has no recent owner")
            old = self._allocate_old(physical)
            transitions.append(Transition(physical, recent, old))
        self._pending = tuple(transitions)
        return self._pending

    def pending_transition(self) -> tuple[Transition, ...]:
        return self._pending

    def finish_transition(self) -> None:
        for transition in self._pending:
            if self.recent_locations[transition.physical] != transition.recent:
                raise RuntimeError("recent ownership changed during layer epoch")
            self.recent_locations[transition.physical] = -1
            self._free_recent.append(transition.recent)
        self._pending = ()

    def release(self, physical_pages: Iterable[int]) -> None:
        pending = {row.physical for row in self._pending}
        for physical in physical_pages:
            if not self._valid(physical):
                continue
            if physical in pending:
                raise RuntimeError("cannot release a page during a layer epoch")
            recent = self.recent_locations[physical]
            old = self.old_locations[physical]
            if recent >= 0:
                self._free_recent.append(recent)
            if old >= 0:
                self._free_old.append(old)
            self.recent_locations[physical] = -1
            self.old_locations[physical] = -1
            self.generations[physical] += 1

    def move(self, target: int, source: int) -> None:
        if not self._valid(target) or not self._valid(source):
            return
        if self._pending:
            raise RuntimeError("canonical move during global layer epoch")
        self.release((target,))
        self.recent_locations[target] = self.recent_locations[source]
        self.old_locations[target] = self.old_locations[source]
        self.recent_locations[source] = -1
        self.old_locations[source] = -1
        self.generations[target] += 1
        self.generations[source] += 1

