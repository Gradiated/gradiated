"""Deterministic prompt sets built from real code and prose.

AgentX traces publish only token lengths and hash ids, so we keep their shape
(long agentic-coding contexts, short outputs) and fill the contexts with real
text: Python source files and Wikipedia prose. A random-token control is kept
for the measurement-fidelity experiment.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

PREAMBLE = (
    "You are a coding agent working in a large Python repository. The user has "
    "opened the following files and notes. Read them carefully, then answer the "
    "question at the end with a concrete, step-by-step plan and code.\n\n"
)
QUESTIONS = (
    "Explain how the scheduler decides which requests run in the next step and propose a fix for starvation.",
    "Find the bug that makes the cache eviction order nondeterministic and write a patch.",
    "Summarize the data flow from the HTTP request to the model forward pass.",
    "Write unit tests that cover the error paths of the configuration parser.",
    "Refactor the attention metadata builder so prefill and decode share one code path.",
    "Describe how tensor parallel ranks exchange activations and where the all-reduces happen.",
    "Propose a faster implementation of the top-k selection and show the code.",
    "List every place where the code assumes a fixed batch size and explain the risk.",
)


@dataclass(frozen=True)
class Corpus:
    documents: tuple[str, ...]

    @classmethod
    def from_paths(cls, code_files: Iterable[Path], prose_files: Iterable[Path], seed: int) -> "Corpus":
        docs: list[str] = []
        for path in sorted(code_files):
            text = path.read_text(errors="ignore")
            if len(text) > 2000:
                docs.append(f"### File: {path.name}\n```python\n{text}\n```\n")
        for path in sorted(prose_files):
            for block in path.read_text(errors="ignore").split("\n = "):
                if len(block) > 3000:
                    docs.append(f"### Note\n{block.strip()}\n")
        random.Random(seed).shuffle(docs)
        return cls(tuple(docs))


def build_prompt_token_ids(
    corpus: Corpus,
    encode,
    count: int,
    input_len: int,
    seed: int,
) -> list[list[int]]:
    """Return ``count`` distinct prompts of exactly ``input_len`` tokens."""
    if not corpus.documents:
        raise ValueError("corpus is empty")
    rng = random.Random(seed)
    prompts: list[list[int]] = []
    preamble = encode(PREAMBLE)
    for index in range(count):
        question = encode("\n\nQuestion: " + QUESTIONS[index % len(QUESTIONS)] + "\nAnswer:")
        budget = input_len - len(preamble) - len(question)
        if budget <= 0:
            raise ValueError("input_len is shorter than the prompt scaffolding")
        body: list[int] = []
        start = rng.randrange(len(corpus.documents))
        offset = 0
        while len(body) < budget:
            doc = corpus.documents[(start + offset) % len(corpus.documents)]
            body.extend(encode(doc))
            offset += 1
            if offset > len(corpus.documents) * 4:
                raise ValueError("corpus too small for requested input length")
        prompts.append(preamble + body[:budget] + question)
    return prompts


def random_token_ids(count: int, input_len: int, vocab_size: int, seed: int, reserved: Sequence[int] = ()) -> list[list[int]]:
    rng = random.Random(seed)
    banned = set(reserved)
    prompts = []
    for _ in range(count):
        ids = []
        while len(ids) < input_len:
            token = rng.randrange(vocab_size)
            if token not in banned:
                ids.append(token)
        prompts.append(ids)
    return prompts


def save(path: Path, prompts: list[list[int]], meta: dict) -> None:
    path.write_text(json.dumps({"meta": meta, "prompts": prompts}))


def load(path: Path) -> tuple[list[list[int]], dict]:
    data = json.loads(path.read_text())
    return data["prompts"], data["meta"]
