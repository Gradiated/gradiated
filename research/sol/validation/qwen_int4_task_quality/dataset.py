from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PiqaExample:
    index: int
    goal: str
    choices: tuple[str, str]
    label: int

    @property
    def identifier(self) -> str:
        return f"piqa-validation-{self.index:04d}"


def hash_ranked_indices(row_count: int, example_count: int, seed: int) -> list[int]:
    if row_count <= 0:
        raise ValueError("row_count must be positive")
    if example_count <= 0 or example_count > row_count:
        raise ValueError("example_count must be between one and row_count")
    return sorted(
        range(row_count),
        key=lambda index: hashlib.sha256(f"{seed}:{index}".encode()).digest(),
    )[:example_count]


def selected_indices_sha256(indices: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(indices, separators=(",", ":")).encode()
    ).hexdigest()


def canonical_rows_sha256(rows: list[PiqaExample]) -> str:
    document = [asdict(row) for row in rows]
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_piqa_validation(jsonl_path: Path, labels_path: Path) -> list[PiqaExample]:
    try:
        raw_rows = jsonl_path.read_text(encoding="utf-8").splitlines()
        raw_labels = labels_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"PIQA input is missing: {error.filename}") from error
    if len(raw_rows) != len(raw_labels):
        raise ValueError("PIQA rows and labels have different lengths")
    examples: list[PiqaExample] = []
    for index, (raw_row, raw_label) in enumerate(
        zip(raw_rows, raw_labels, strict=True)
    ):
        try:
            row = json.loads(raw_row)
            label = int(raw_label)
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"invalid PIQA row or label at index {index}") from error
        if not isinstance(row, dict):
            raise ValueError(f"invalid PIQA object at index {index}")
        goal = str(row.get("goal", ""))
        sol1 = str(row.get("sol1", ""))
        sol2 = str(row.get("sol2", ""))
        if (
            not goal.strip()
            or not sol1.strip()
            or not sol2.strip()
            or label not in {0, 1}
        ):
            raise ValueError(f"invalid PIQA content at index {index}")
        examples.append(PiqaExample(index, goal, (sol1, sol2), label))
    return examples
