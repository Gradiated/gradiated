"""KnowLine (Gemma 4) encoding for ``gdecide.prepare --family gemma``.

KnowLine answers each question from its own causal prompt (KnowLine's release front end: chat template, read twice
for short requests, the question header for long ones), reading the next-token logits of the option labels after
``Answer:``. So a training row becomes one example per scored question: ``ids`` is that question's prompt, its single
marker is the prompt's last token and its target is in KnowLine's option order (noul: true, false; choice: criteria
order; score: levels). The shard format is the one ``gdecide.train_full`` reads, so the same trainer runs with
``--family gemma``.
"""

from __future__ import annotations

import json
import random

_RENDERER = None


def init(checkpoint: str) -> None:
    global _RENDERER
    from gdecide.backends.knowline import Renderer

    _RENDERER = Renderer(checkpoint)


def target(keys: list[str], question: dict, expected) -> list[float] | None:
    """The target distribution over ``keys`` (the semantics of ``gdecide.train.target_distribution``)."""
    if expected is None:
        return None
    if question["type"] == "noul" and isinstance(expected, (int, float)) and not isinstance(expected, bool):
        p = float(expected)
        values = {"true": p, "false": 1 - p}
        return [values[k] for k in keys]
    if isinstance(expected, bool):
        expected = "true" if expected else "false"
    if isinstance(expected, dict):
        total = sum(float(expected.get(k, 0)) for k in keys)
        return [float(expected.get(k, 0)) / total for k in keys] if total > 0 else None
    expected = str(expected)
    if expected not in keys:
        return None
    return [1.0 if k == expected else 0.0 for k in keys]


def encode(job: tuple[list[str], int, float, float]):
    from gdecide.backends.knowline import Unsupported
    from gdecide.prepare import augmented

    lines, max_length, shuffle_p, weight, *rest = job
    aug = rest[0] if rest else {}
    out, dropped = [], {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for line in lines:
        row = json.loads(line)
        rng = random.Random(str(row.get("id")) + row.get("source", ""))
        row = augmented(row, rng, shuffle_p, aug)
        request = {"state": row["state"], "questions": row["questions"]}
        try:
            prompts = _RENDERER.prompts(request)
        except (Unsupported, ValueError) as exc:
            drop(type(exc).__name__)
            continue
        expected = row.get("expected", {})
        kept = 0
        for p in prompts:
            t = target(p.keys, row["questions"][p.qid], expected.get(p.qid))
            if t is None:
                continue
            if len(p.ids) > max_length:
                drop("too_long")
                continue
            kept += 1
            out.append({"ids": p.ids, "markers": [len(p.ids) - 1], "counts": [len(p.keys)], "targets": [t],
                        "source": row.get("source", "?"), "weight": weight * float(row.get("weight", 1.0))})
        if not kept:
            drop("no_target")
    return out, dropped
