"""Normalize public decision data without discarding native binary targets."""

import hashlib
import json
import math
import re
from pathlib import Path


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


RESTRICTED_AUTHORS = re.compile(
    r"openai|anthropic|claude|gpt-|gemini|hh[-_]rlhf|ultrafeedback", re.IGNORECASE
)


def text(value):
    return (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False)
    )


def normalized_state(value):
    return " ".join(re.findall(r"\w+", text(value).lower()))


def grams(value, size=13):
    words = normalized_state(value).split()
    return {
        hashlib.blake2b(" ".join(words[i : i + size]).encode(), digest_size=8).digest()
        for i in range(len(words) - size + 1)
    }


def validate_row(row):
    labels, descriptions, target = row["labels"], row["descriptions"], row["target"]
    if not 2 <= len(labels) <= 26 or len(set(labels)) != len(labels):
        raise ValueError("expected 2–26 distinct options")
    if len(target) != len(labels) or len(descriptions) != len(labels):
        raise ValueError("target and description lengths must match options")
    if any(
        not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 for p in target
    ):
        raise ValueError("invalid probability target")
    if abs(sum(target) - 1) > 1e-4:
        raise ValueError("target must sum to one")
    if row["question"]["type"] not in ("noul", "choice", "score"):
        raise ValueError("unsupported question type")
    return row


def normalize_tasksource(row):
    if row.get("license_use") != "commercial" or RESTRICTED_AUTHORS.search(
        row.get("source", "")
    ):
        return None
    options, target = row["options"], row["target"]
    labels = [str(i) for i in range(len(options))]
    if row["kind"] == "noul" and not options and len(target) == 1:
        options, labels, target = (
            ["No", "Yes"],
            ["no", "yes"],
            [1 - target[0], target[0]],
        )
    repo = "tasksource/tasksource-jev-typed-decisions"
    return validate_row(
        {
            "id": row["id"],
            "source": repo,
            "source_task": row["source"],
            "license": row["license"],
            "state": row["state"],
            "question": {
                "type": row["kind"],
                "instructions": row["question"],
                "criteria": options,
            },
            "labels": labels,
            "descriptions": options,
            "target": target,
            "group": repo + ":" + str(row.get("group_id") or row["id"]),
        }
    )


def normalize_typed(row, source):
    ancestry = row.get("ancestry") or {}
    if RESTRICTED_AUTHORS.search(
        text(
            [row.get("generator"), row.get("provenance"), ancestry.get("author_family")]
        )
    ):
        return None
    q = row["question"]
    kind, criteria = q["type"], q.get("criteria")
    if kind == "noul":
        labels = ["false", "true"]
        descriptions = [
            (criteria or {}).get(k) or fallback
            for k, fallback in zip(labels, ["No", "Yes"])
        ]
    elif kind == "score":
        labels = [str(i) for i in range(len(criteria))]
        descriptions = list(map(str, criteria))
    else:
        labels = list(criteria)
        descriptions = [
            str(criteria[k]) if criteria[k] is not None else k for k in labels
        ]
    expected = str(row["expected"]).lower() if kind == "noul" else str(row["expected"])
    if kind == "noul":
        expected = {"no": "false", "yes": "true", "0": "false", "1": "true"}.get(
            expected, expected
        )
    if expected not in labels:
        raise ValueError("expected option absent")
    target = row.get("target_probs")
    if isinstance(target, dict):
        target = [target[k] for k in labels]
    elif isinstance(target, list) and row.get("labels") and row["labels"] != labels:
        by_label = dict(zip(row["labels"], target))
        target = [by_label[k] for k in labels]
    if target is None:
        target = [float(k == expected) for k in labels]
    group = (
        ancestry.get("split_key")
        or ancestry.get("cf_pair")
        or ancestry.get("translation_of")
        or ancestry.get("root")
        or row.get("state_sha256")
        or row["id"]
    )
    return validate_row(
        {
            "id": row["id"],
            "source": source,
            "source_task": source
            + "/"
            + str(row.get("family") or row.get("category") or kind),
            "license": row.get("license") or row.get("licence"),
            "state": row["state"],
            "question": q,
            "labels": labels,
            "descriptions": descriptions,
            "target": target,
            "group": source + ":" + group,
        }
    )


def split_rows(rows, dev_modulus=20):
    train, dev = [], []
    for row in rows:
        is_dev = (
            int(hashlib.sha256(row["group"].encode()).hexdigest()[:8], 16) % dev_modulus
            == 0
        )
        (dev if is_dev else train).append(
            {**row, "split": "dev" if is_dev else "train"}
        )
    states = {normalized_state(r["state"]) for r in train}
    return train, [r for r in dev if normalized_state(r["state"]) not in states]
