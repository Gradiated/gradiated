#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


STATE_WIDTH = 24
STATE_FRAC = 18
VECTOR_FRAC = 6
GATE_FRAC = 8


def saturate(value: int, width: int) -> int:
    minimum = -(1 << (width - 1))
    maximum = (1 << (width - 1)) - 1
    return min(maximum, max(minimum, value))


@dataclass(frozen=True)
class TokenInputs:
    q: list[int]
    k: list[int]
    v: list[int]
    alpha: list[int]
    beta: int


class KDAReference:
    def __init__(self, head_dim: int) -> None:
        self.head_dim = head_dim
        self.state = [[0 for _ in range(head_dim)] for _ in range(head_dim)]

    def clear(self) -> None:
        for row in self.state:
            row[:] = [0] * self.head_dim

    def step(self, token: TokenInputs) -> list[int]:
        if not all(
            len(values) == self.head_dim
            for values in (token.q, token.k, token.v, token.alpha)
        ):
            raise ValueError("all input vectors must match head_dim")
        if not 0 <= token.beta <= 255:
            raise ValueError("beta must fit unsigned 8-bit Q0.8")

        output = []
        for column in range(self.head_dim):
            scaled = [
                saturate((self.state[row][column] * token.alpha[row]) >> GATE_FRAC, STATE_WIDTH)
                for row in range(self.head_dim)
            ]
            projection = sum(token.k[row] * scaled[row] for row in range(self.head_dim)) >> VECTOR_FRAC
            delta = (token.v[column] << (STATE_FRAC - VECTOR_FRAC)) - projection
            next_column = []
            for row in range(self.head_dim):
                update = (token.beta * token.k[row] * delta) >> (GATE_FRAC + VECTOR_FRAC)
                next_column.append(saturate(scaled[row] + update, STATE_WIDTH))
            for row, value in enumerate(next_column):
                self.state[row][column] = value
            projected = sum(token.q[row] * next_column[row] for row in range(self.head_dim)) >> VECTOR_FRAC
            output.append(saturate(projected, 32))
        return output


def lcg_step(state: int) -> int:
    return (state * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF


def generate_tokens(head_dim: int, token_count: int, seed: int) -> list[TokenInputs]:
    state = seed & 0xFFFFFFFF
    tokens = []
    for _ in range(token_count):
        vectors: list[list[int]] = []
        for _ in range(3):
            vector = []
            for _ in range(head_dim):
                state = lcg_step(state)
                vector.append(((state >> 28) & 0xF) - 8)
            vectors.append(vector)
        alpha = []
        for _ in range(head_dim):
            state = lcg_step(state)
            alpha.append(224 + ((state >> 27) & 0x1F))
        state = lcg_step(state)
        beta = 1 + ((state >> 28) & 0xF)
        tokens.append(TokenInputs(vectors[0], vectors[1], vectors[2], alpha, beta))
    return tokens


def unsigned_hex(value: int, width_bits: int) -> str:
    return f"{value & ((1 << width_bits) - 1):0{width_bits // 4}x}"


def write_memh(path: Path, values: list[int], width_bits: int) -> None:
    path.write_text("\n".join(unsigned_hex(value, width_bits) for value in values) + "\n")


def generate_fixture(output_dir: Path, head_dim: int, token_count: int, seed: int) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tokens = generate_tokens(head_dim, token_count, seed)
    stress_count = min(2, token_count)
    for index in range(token_count - stress_count, token_count):
        tokens[index] = TokenInputs(
            q=[127] * head_dim,
            k=[127] * head_dim,
            v=[127] * head_dim,
            alpha=[255] * head_dim,
            beta=255,
        )
    reference = KDAReference(head_dim)
    outputs = [reference.step(token) for token in tokens]
    saturated_state_values = sum(
        value in (-(1 << (STATE_WIDTH - 1)), (1 << (STATE_WIDTH - 1)) - 1)
        for row in reference.state
        for value in row
    )
    if stress_count and saturated_state_values == 0:
        raise RuntimeError("stress fixture did not exercise state saturation")

    for name in ("q", "k", "v", "alpha"):
        write_memh(output_dir / f"{name}.memh", [value for token in tokens for value in getattr(token, name)], 8)
    write_memh(output_dir / "beta.memh", [token.beta for token in tokens], 8)
    write_memh(output_dir / "expected.memh", [value for token in outputs for value in token], 32)

    manifest = {
        "evidence_class": "software_reference",
        "equation": "S=(I-beta*k*kT)*Diag(alpha)*S+beta*k*vT; o=ST*q",
        "head_dim": head_dim,
        "token_count": token_count,
        "seed": seed,
        "stress_token_count": stress_count,
        "saturated_state_values_after_final_token": saturated_state_values,
        "state_width": STATE_WIDTH,
        "state_fraction_bits": STATE_FRAC,
        "vector_fraction_bits": VECTOR_FRAC,
        "gate_fraction_bits": GATE_FRAC,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--head-dim", type=int, default=16)
    parser.add_argument("--tokens", type=int, default=3)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0x4B444131)
    args = parser.parse_args()
    print(json.dumps(generate_fixture(args.output_dir, args.head_dim, args.tokens, args.seed), indent=2))


if __name__ == "__main__":
    main()
