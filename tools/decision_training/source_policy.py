"""Versioned research-corpus eligibility and source-family holdouts."""

import hashlib
import re
from functools import lru_cache

from data import RESTRICTED_AUTHORS, normalized_state

VERSION = "public-decision-research-v1"
EXCLUDED = re.compile(r"wanli|prm800k|i2d2|wildguardmix", re.IGNORECASE)
EXCLUSION_EVIDENCE = {
    "wanli": "https://arxiv.org/abs/2201.05955",
    "prm800k": "https://github.com/openai/prm800k",
    "i2d2": "writer provenance not fully resolved for this release",
    "wildguardmix": "mixed writer provenance not fully resolved for this release",
}


@lru_cache(maxsize=10000)
def canonical_family(value):
    value = value.lower()
    value = re.sub(r"(?:\+(?:fmt|long|para))+$", "", value)
    for prefix in (
        "tasksource/procedural-typed-decisions/",
        "procedural-typed-decisions/",
    ):
        if value.startswith(prefix):
            return "procedural/" + value.removeprefix(prefix)
    aliases = {
        "mnli": "multi_nli",
        "social_i_qa": "siqa",
        "social_iqa": "siqa",
        "dbpedia_14/dbpedia_14": "dbpedia",
        "clinc": "clinc150",
        "case_hold": "lex_glue/case_hold",
        "go_emotions/simplified": "go_emotions",
        "snli/snli": "snli",
    }
    return aliases.get(value, value)


@lru_cache(maxsize=1000)
def allowed_license(value):
    value = value.lower()
    if re.search(r"non.?commercial|\bnc\b|custom|other|unknown|unstated", value):
        return False
    terms = [
        re.sub(r"[ _]+", "-", term.strip().replace("(dpi)", "")).strip("-")
        for term in re.split(r"[,;/]", value)
    ]
    return bool(terms) and all(
        re.fullmatch(
            r"(?:apache-2\.0|mit(?:-license)?|cc0-1\.0|cc-by(?:-sa)?-[34]\.0|afl-3\.0|bsd(?:-2-clause-license)?|(?:a?gpl)(?:-[23]\.0)?|mpl-2\.0|odc-by|oanc)",
            term,
        )
        for term in terms
    )


def rejection(row):
    source = row["source_task"]
    if RESTRICTED_AUTHORS.search(source) or EXCLUDED.search(source):
        return "excluded_or_unresolved_writer_provenance"
    if not allowed_license(row["license"]):
        return "unreviewed_or_restricted_terms"
    return None


def source_priority(row):
    return (
        0
        if row["source"] in ("stanfordnlp/snli", "tasksource/esci")
        else 1
        if row["source"] == "tasksource/procedural-typed-decisions"
        else 2
    )


def heldout_family(family):
    return (
        int(hashlib.sha256((VERSION + ":" + family).encode()).hexdigest()[:8], 16) % 20
        == 0
    )


def family_cap(family):
    if family in ("snli", "esci"):
        return 300000
    if family.startswith("procedural/"):
        return 75000
    return 60000


def near_state_key(row):
    # Split co-location only: never use this word-bag key to delete decisions.
    state = normalized_state(row["state"])
    if len(state.split()) < 8:
        return None
    operators = re.findall(r"[+\-−*/<>=!]+", str(row["state"]))
    numbers = re.findall(r"[+\-−]?(?:\d+(?:[.,]\d+)?|\.\d+)", str(row["state"]))
    return hashlib.sha256(
        (
            " ".join(sorted(state.split()))
            + "|"
            + " ".join(operators)
            + "|"
            + " ".join(sorted(numbers))
        ).encode()
    ).digest()[:16]
