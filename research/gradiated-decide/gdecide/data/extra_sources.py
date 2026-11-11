"""Convert extra commercially-licensed decision datasets (stance, aspect sentiment, ...) into training rows.

Run from ``research/gradiated-decide/``::

    python -m gdecide.data.extra_sources --out ../../.agents/runtime/gdecide/data/extra [--sources ...] [--limit N]

Companion to ``gdecide.data.hub_sources``: same output line format, same target and validation rules
(``validate_row``), same pinned anonymous downloads. Sources live on the Hugging Face Hub (pinned dataset commit,
LFS files checked against their sha256) or on GitHub (pinned commit, every file checked against a sha256 recorded
here). Downloaded files are parsed as data only (CSV/TSV, JSON lines, parquet, XML without DTDs, Python literals
through ``ast.literal_eval``); nothing in them is executed. Output is one ``<slug>.jsonl.gz`` per source plus
``extra-manifest.json``. Rows then go through ``gdecide.decontam`` like every hub source.

Every source here was chosen for a skill the v1 mix had no licence-clean data for (stance, aspect sentiment,
argument quality / pairwise preference, ...). Each source records its licence chain in ``license_note``; only train
splits are read. Question wording is varied per row (seeded by the row id) so that the model learns the skill, not
one template.
"""

from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import json
import random
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gdecide.data.hub_sources import (
    Drop,
    Fetched,
    Source,
    Stats,
    _get,
    _parquet_batches,
    check_question,
    clean_question,
    fetch_source,
    validate_row,
)

PREFIX = "gdecide-extra"
csv.field_size_limit(1 << 30)


# --------------------------------------------------------------------------------------------- sources


@dataclass(frozen=True)
class GitFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class GitSource:
    """A GitHub repository pinned at a commit; every file is checked against its recorded sha256."""

    slug: str
    repo: str
    config: str
    revision: str
    files: tuple[GitFile, ...]
    license: str
    license_note: str
    docs: tuple[str, ...] = ()


ExtraSource = Source | GitSource

SOURCES: dict[str, ExtraSource] = {
    s.slug: s
    for s in (
        Source(
            slug="ibm-argq-30k",
            repo="ibm-research/argument_quality_ranking_30k",
            config="argument_quality_ranking",
            revision="590726b3765b1b90c5e53a17e3b1f77d92d3aa8a",
            files=r"^train\.csv$",
            license="CC-BY-SA-3.0",
            license_note=(
                "Card tag cc-by-3.0; card text: '(c) Copyright IBM 2014. Released under CC-BY-SA 3.0' (attribution, "
                "share-alike). 30,497 arguments written by paid crowd contributors for 71 debate topics; quality and "
                "stance labelled by 10 human annotators each (Gretz et al., AAAI 2020). No model-written text."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="ibm-claim-stance",
            repo="ibm-research/claim_stance",
            config="claim_stance",
            revision="ec4e2c2ec3e0c70087c67a28a7bce58b682b8109",
            files=r"^train\.csv$",
            license="CC-BY-SA-3.0",
            license_note=(
                "Card tag cc-by-3.0; card text: Wikipedia copyright plus '(c) Copyright IBM 2014. Released under "
                "CC-BY-SA 3.0'. Claims are Wikipedia sentences, stance labelled by human annotators (Bar-Haim et al., "
                "EACL 2017). Train split = 25 topics."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="wiki-stance-en",
            repo="copenlu/wiki-stance",
            config="en",
            revision="a2f4d1bf5237fb53b1a817e8e593f52b5a91f336",
            files=r"^(en-train|pol_en)\.tsv$",
            license="CC-BY-SA-4.0",
            license_note=(
                "Card licence cc-by-sa-4.0. English Wikipedia Articles-for-Deletion comments (Wikipedia text, "
                "CC BY-SA); the stance (keep/delete/merge/comment) and the cited policy are the editors' own "
                "(Kaffee et al., EMNLP 2023). Usernames and timestamps are not copied into rows (card asks not to "
                "identify editors)."
            ),
            docs=("README.md",),
        ),
        GitSource(
            slug="mams-acsa",
            repo="siat-nlp/MAMS-for-ABSA",
            config="MAMS-ACSA",
            revision="cddcdb0f423b3fdb2c76b70744737abed3a00d17",
            files=(GitFile("data/MAMS-ACSA/raw/train.xml",
                           "24c6a1a9f769ec5a9a1fc9a63077001339cec65317e3e72cf053d8055ec5f1ac"),),
            license="Apache-2.0",
            license_note=(
                "Repository licence Apache-2.0 (GitHub LICENSE, covers the released data). Sentences are restaurant "
                "reviews from the Citysearch corpus of Ganu et al. (2009), the same corpus as SemEval-2014 "
                "restaurants; aspect-category sentiment labelled by the authors (Jiang et al., EMNLP 2019). The "
                "review text itself has no separate licence statement: needs legal sign-off before commercial use."
            ),
            docs=("LICENSE", "README.md"),
        ),
        Source(
            slug="m-absa-en",
            repo="Multilingual-NLP/M-ABSA",
            config="en/coursera,hotel,food,phone,sight",
            revision="521ab96c3fc0acb4f844205d0e05382734fc89f2",
            files=r"^(coursera|hotel|food|phone|sight)/en/train\.txt$",
            license="Apache-2.0",
            license_note=(
                "Card licence apache-2.0. English originals only (other languages are Google-Translate output). "
                "laptop and restaurant domains excluded: laptop is the ACOS laptop corpus (Cai et al. 2021) and "
                "restaurant is SemEval-2016, both Decision Index ACOS test sources. Kept domains: hotel "
                "(TripAdvisor, Yin et al. 2017), food (Amazon fine food, Kaggle), coursera (Kaggle), phone "
                "(e-commerce reviews, Zhou et al. 2023), sight (MIT OCW YouTube comments, Wang et al. 2023), all "
                "human-annotated triplets. Underlying review sites' terms are not stated by the card: needs legal "
                "sign-off before commercial use."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="massive-intents",
            repo="AmazonScience/massive",
            config="en-US,de-DE,fr-FR,es-ES,zh-CN,ja-JP,ar-SA,hi-IN",
            # The Hub's parquet conversion (refs/convert/parquet) of v1.1; main only has a loading script.
            revision="ed58ac423a2f4121720918bf5301577edce4ffd3",
            files=r"^(en-US|de-DE|fr-FR|es-ES|zh-CN|ja-JP|ar-SA|hi-IN)/train/\d+\.parquet$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0 (MASSIVE 1.1, FitzGerald et al. 2022). English utterances are SLURP "
                "(crowd-written voice-assistant commands, CC BY 4.0); other locales were localised by professional "
                "human translators. Intent/scenario/slot labels are human. No model-written text."
            ),
            docs=(),
        ),
        Source(
            slug="sarcasm-headlines",
            repo="Heschmat/news-headlines-dataset-sarcasm-detection",
            config="v1",
            revision="2ba33705c88084e808bc73ead1c30251080e41b7",
            files=r"^data/train-\d+-of-\d+\.parquet$",
            license="CC-BY-4.0",
            license_note=(
                "Hub mirror (tag bsd-3-clause-clear, set by the uploader) of Misra & Arora's News Headlines Dataset "
                "for Sarcasm Detection v1 (26,709 headlines, 11,724 sarcastic: identical counts). The author's "
                "Kaggle release rmisra/news-headlines-dataset-for-sarcasm-detection is CC BY 4.0; credit Misra & "
                "Arora (2019/2023). Labels come from the source site (TheOnion = sarcastic/satirical, HuffPost = "
                "not), no model involvement. Headlines are short excerpts of the two news sites."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="vitaminc",
            repo="tals/vitaminc",
            config="train",
            revision="be6febb761b0b2807687e61e0b5282e459df2fa0",
            files=r"^train\.jsonl$",
            license="CC-BY-SA-3.0",
            license_note=(
                "Card licence cc-by-sa-3.0 (Wikipedia revisions); code MIT (GitHub TalSchuster/VitaminC). Claims "
                "written by crowd workers against real Wikipedia revisions, plus synthetic contrastive revisions "
                "written by the same workers; labels SUPPORTS/REFUTES/NOT ENOUGH INFO are human (Schuster et al., "
                "NAACL 2021). Rows carry a BIG-bench canary GUID added by the release; this is the official train "
                "split, but drop the source if the canary is treated as a do-not-train marker."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="go-emotions",
            repo="google-research-datasets/go_emotions",
            config="simplified",
            revision="add492243ff905527e67aeb8b80c082af02207c3",
            files=r"^simplified/train-\d+-of-\d+\.parquet$",
            license="Apache-2.0",
            license_note=(
                "Card licence apache-2.0. 58k Reddit comments (2005-2019) labelled with 27 emotions + neutral by "
                "human raters (Demszky et al., ACL 2020); simplified config keeps labels with rater agreement. "
                "Reddit comment text: Reddit's own terms apply to the text."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="qasc",
            repo="allenai/qasc",
            config="default",
            revision="a34ba204eb9a33b919c10cc08f4f1c8dae5ec070",
            files=r"^data/train-\d+-of-\d+\.parquet$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0. 8-way grade-school science questions composed by crowd workers from two "
                "science facts (Khot et al., AAAI 2020). AllenAI, like ARC, but a separate question set."
            ),
            docs=("README.md",),
        ),
    )
}


# --------------------------------------------------------------------------------------------- download


def fetch_git(source: GitSource, out: Path) -> Fetched:
    raw = out / "_raw" / source.slug / source.revision
    paths, meta, docs = [], [], {}

    def get(path: str, want: str | None) -> Path:
        target = raw / path
        if target.exists() and (want is None or hashlib.sha256(target.read_bytes()).hexdigest() == want):
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://raw.githubusercontent.com/{source.repo}/{source.revision}/{urllib.parse.quote(path)}"
        print(f"  fetch {source.repo}@{source.revision[:8]}/{path}", file=sys.stderr)
        with _get(url, timeout=300) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if want and digest != want:
            raise RuntimeError(f"{source.repo}/{path}: sha256 {digest} != pinned {want}")
        target.write_bytes(data)
        return target

    for name in source.docs:
        docs[name] = hashlib.sha256(get(name, None).read_bytes()).hexdigest()
    for item in source.files:
        paths.append(get(item.path, item.sha256))
        meta.append({"file": item.path, "size": paths[-1].stat().st_size, "sha256": item.sha256})
    return Fetched(source, source.revision, None, paths, meta, docs, None)  # type: ignore[arg-type]


@dataclass
class Context:
    out: Path
    latest: bool

    def fetched(self, slug: str) -> Fetched:
        source = SOURCES[slug]
        if isinstance(source, GitSource):
            return fetch_git(source, self.out)
        return fetch_source(source, self.out, self.latest)


# --------------------------------------------------------------------------------------------- helpers


def rng_for(*parts: Any) -> random.Random:
    return random.Random(hashlib.sha256(":".join([PREFIX, *map(str, parts)]).encode()).digest())


def pick(rng: random.Random, options: list[str]) -> str:
    return options[rng.randrange(len(options))]


def norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def question(kind: str, instructions: str, criteria: Any) -> dict[str, Any]:
    q = clean_question(kind, instructions, criteria)
    if reason := check_question(q):
        raise Drop(reason)
    return q


def read_csv(path: Path, delimiter: str = ",") -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle, delimiter=delimiter)


def file_by_name(fetched: Fetched, name: str) -> Path:
    for path in fetched.files:
        if path.name == name:
            return path
    raise RuntimeError(f"{fetched.source.repo}: {name} not fetched")


POLARITY = {"positive": "positive", "pos": "positive", "negative": "negative", "neg": "negative",
            "neutral": "neutral", "neu": "neutral", "conflict": "conflict", "mixed": "conflict"}


# --------------------------------------------------------------------------------------------- stance and argument quality

STANCE_INSTRUCTIONS = [
    "What is the stance of the argument toward the topic?",
    "Does the argument support or oppose the topic?",
    "Classify the argument's position on the debate topic.",
]
QUALITY_INSTRUCTIONS = [
    "Would you recommend a friend to use this argument as is in a speech {side} the topic, regardless of your own "
    "opinion?",
    "Is this a high-quality argument that a speaker {side} the topic would likely use as is?",
]
PAIR_INSTRUCTIONS = [
    "Both arguments take the same side on the topic. Which one would a speaker preparing a speech on the topic "
    "more likely use as is?",
    "Which of the two arguments is the stronger one to use in a debate speech?",
]


def convert_argq(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """One row per argument (stance + quality), plus pairwise quality comparisons within a topic and side."""
    source = f"{fetched.source.repo}/{fetched.source.config}"
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for n, record in enumerate(read_csv(fetched.files[0])):
        stats.input_rows += 1
        if record.get("set") != "train":
            stats.dropped["not_train_split"] += 1
            continue
        try:
            argument, topic = norm_space(record["argument"]), norm_space(record["topic"])
            quality = float(record["WA"])
            stance = int(record["stance_WA"])
            conf = float(record["stance_WA_conf"])
        except (KeyError, ValueError):
            stats.dropped["unparseable"] += 1
            continue
        if not argument or not topic or not 0 <= quality <= 1:
            stats.dropped["bad_fields"] += 1
            continue
        rid = hashlib.sha1(f"{topic}\n{argument}".encode()).hexdigest()[:16]
        rng = rng_for("argq", rid)
        questions, expected = {}, {}
        if stance in (1, -1) and 0.5 <= conf <= 1:
            win, lose = ("pro", "con") if stance == 1 else ("con", "pro")
            questions["stance"] = question("choice", pick(rng, STANCE_INSTRUCTIONS), {
                "pro": "The argument supports the topic.", "con": "The argument contests the topic."})
            expected["stance"] = win if conf >= 1 - 1e-9 else {win: round(conf, 6), lose: round(1 - conf, 6)}
        side = "supporting" if stance == 1 else "contesting" if stance == -1 else "on"
        questions["quality"] = question("noul", pick(rng, QUALITY_INSTRUCTIONS).format(side=side), None)
        expected["quality"] = round(quality, 6)
        stats.count("stance", stance)
        yield {
            "state": {"topic": topic, "argument": argument},
            "questions": questions,
            "expected": expected,
            "source": source,
            "license": fetched.source.license,
            "id": f"argq:{rid}",
            "meta": {"task": "argq/stance+quality", "stance_conf": conf},
        }
        if stance in (1, -1):
            by_group[(topic, side)].append({"argument": argument, "quality": quality, "rid": rid})
    # Pairwise preference: each argument is paired once with a same-topic, same-side argument whose quality differs
    # by at least 0.3 (WA scale); the target is the better one. Labels stay human (the WA scores).
    for (topic, side), items in sorted(by_group.items()):
        items.sort(key=lambda x: x["rid"])
        for i, a in enumerate(items):
            rng = rng_for("argq-pair", a["rid"])
            partners = [b for b in items if abs(b["quality"] - a["quality"]) >= 0.3 and b["rid"] > a["rid"]]
            if not partners:
                continue
            b = partners[rng.randrange(len(partners))]
            first, second = (a, b) if rng.random() < 0.5 else (b, a)
            best = "argument_1" if first["quality"] > second["quality"] else "argument_2"
            stats.count("pairs", "made")
            yield {
                "state": {"topic": topic, "side": side},
                "questions": {"preferred": question("choice", pick(rng, PAIR_INSTRUCTIONS), {
                    "argument_1": first["argument"], "argument_2": second["argument"]})},
                "expected": {"preferred": best},
                "source": source,
                "license": fetched.source.license,
                "id": f"argq-pair:{first['rid']}:{second['rid']}",
                "meta": {"task": "argq/pairwise-quality", "gap": round(abs(a["quality"] - b["quality"]), 4)},
            }


CLAIM_INSTRUCTIONS = [
    "Does the claim support (PRO) or contest (CON) the debate motion?",
    "What is the stance of the claim toward the motion?",
]


def convert_claim_stance(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    source = f"{fetched.source.repo}/{fetched.source.config}"
    for record in read_csv(fetched.files[0]):
        stats.input_rows += 1
        if record.get("split") != "train":
            stats.dropped["not_train_split"] += 1
            continue
        stance = (record.get("claims.stance") or "").upper()
        claim = norm_space(record.get("claims.claimCorrectedText") or "")
        topic = norm_space(record.get("topicText") or "")
        if stance not in ("PRO", "CON") or not claim or not topic:
            stats.dropped["bad_fields"] += 1
            continue
        rng = rng_for("claim-stance", record["claims.claimId"])
        yield {
            "state": {"motion": topic, "claim": claim},
            "questions": {"stance": question("choice", pick(rng, CLAIM_INSTRUCTIONS), {
                "PRO": "The claim supports the motion.", "CON": "The claim contests the motion."})},
            "expected": {"stance": stance},
            "source": source,
            "license": fetched.source.license,
            "id": f"claim-stance:{record['claims.claimId']}",
            "meta": {"task": "claim_stance", "topic_id": record.get("topicId")},
        }


WIKI_STANCE = {
    "keep": "Keep the article.",
    "delete": "Delete the article.",
    "merge": "Merge the article into another article.",
    "comment": "A comment that does not vote keep, delete or merge.",
}


def convert_wiki_stance(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    source = f"{fetched.source.repo}/{fetched.source.config}"
    policies = [norm_space(r["policy_title"]) for r in read_csv(file_by_name(fetched, "pol_en.tsv"), "\t")]
    policies = sorted({p for p in policies if p})
    policy_set = set(policies)
    for record in read_csv(file_by_name(fetched, "en-train.tsv"), "\t"):
        stats.input_rows += 1
        decision = (record.get("decision") or "").strip().lower()
        comment = norm_space(record.get("comment") or "")
        title = norm_space(record.get("title") or "").removeprefix("Wikipedia:Articles for deletion/")
        policy = norm_space(record.get("policy_title") or "")
        if decision not in WIKI_STANCE or len(comment) < 20 or not title:
            stats.dropped["bad_fields"] += 1
            continue
        rid = hashlib.sha1(f"{record.get('title')}\n{record.get('timestamp')}\n{comment}".encode()).hexdigest()[:16]
        rng = rng_for("wiki-stance", rid)
        questions = {"stance": question("choice", pick(rng, [
            "Which outcome does this editor argue for in the deletion discussion?",
            "What is the editor's stance on deleting the article?",
        ]), dict(WIKI_STANCE))}
        expected: dict[str, Any] = {"stance": decision}
        if policy in policy_set:
            questions["policy"] = question("choice", pick(rng, [
                "Which Wikipedia policy or guideline is the comment's argument based on? (Explicit policy mentions "
                "were removed from the comment.)",
                "Which policy page does the editor most likely cite for this argument?",
            ]), {p: None for p in policies})
            expected["policy"] = policy
        else:
            stats.count("policy_not_in_list", policy or "none")
        stats.count("decision", decision)
        yield {
            "state": {"discussion": f"Articles for deletion: {title}", "comment": comment},
            "questions": questions,
            "expected": expected,
            "source": source,
            "license": fetched.source.license,
            "id": f"wiki-stance-en:{rid}",
            "meta": {"task": "wiki-stance/en"},
        }


# --------------------------------------------------------------------------------------------- aspect sentiment

SENTIMENTS = ("positive", "negative", "neutral")
ASPECT_CHOICE = {
    "not_mentioned": "The review does not discuss this aspect.",
    "positive": "The review is positive about this aspect.",
    "negative": "The review is negative about this aspect.",
    "neutral": "The review mentions this aspect without a positive or negative opinion.",
}


def pair_questions(rng: random.Random, categories: list[str], present: set[tuple[str, str]],
                   noun: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """One yes/no question per (category, sentiment): a select-all view of aspect sentiment."""
    template = pick(rng, [
        "Does the {noun} express {s} sentiment about the aspect category '{c}'? Answer yes only for that exact "
        "category and sentiment.",
        "Is there {s} sentiment toward '{c}' in the {noun}?",
    ])
    questions, expected = {}, {}
    for c in categories:
        for s in SENTIMENTS:
            key = f"{re.sub(r'[^A-Za-z0-9]+', '_', c).strip('_').lower()}__{s}"
            questions[key] = question("noul", template.format(noun=noun, s=s, c=c), None)
            expected[key] = 1.0 if (c, s) in present else 0.0
    return questions, expected


def mams_sentences(path: Path) -> Iterator[tuple[str, list[tuple[str, str]]]]:
    data = path.read_bytes()
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise RuntimeError(f"{path}: XML with a DTD is not parsed")
    for sentence in ET.fromstring(data).iter("sentence"):
        text = norm_space(sentence.findtext("text") or "")
        aspects = [(a.get("category", ""), a.get("polarity", "")) for a in sentence.iter("aspectCategory")]
        yield text, aspects


MAMS_CATEGORIES = ["food", "service", "staff", "price", "ambience", "menu", "place", "miscellaneous"]


def convert_mams(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Restaurant review sentences; either a 4-way choice per category or yes/no per (category, sentiment)."""
    source = f"{fetched.source.repo}/{fetched.source.config}"
    for text, aspects in mams_sentences(fetched.files[0]):
        stats.input_rows += 1
        present = {(c, POLARITY.get(p.lower(), "")) for c, p in aspects}
        if not text or not present or any(c not in MAMS_CATEGORIES or s not in SENTIMENTS for c, s in present):
            stats.dropped["bad_aspects"] += 1
            continue
        if len({c for c, _ in present}) != len(present):
            stats.dropped["category_with_two_polarities"] += 1
            continue
        rid = hashlib.sha1(text.encode()).hexdigest()[:16]
        rng = rng_for("mams", rid)
        if rng.random() < 0.5:
            polarity = dict(present)
            template = pick(rng, ["What sentiment does the review express about {c}?",
                                  "How does the reviewer feel about the {c}, if it is discussed at all?"])
            questions = {c: question("choice", template.format(c=c), dict(ASPECT_CHOICE)) for c in MAMS_CATEGORIES}
            expected = {c: polarity.get(c, "not_mentioned") for c in MAMS_CATEGORIES}
            variant = "category_choice"
        else:
            questions, expected = pair_questions(rng, MAMS_CATEGORIES, present, "review")
            variant = "category_sentiment_pairs"
        stats.count("variant", variant)
        yield {
            "state": {"review": text, "domain": "restaurant"},
            "questions": questions,
            "expected": expected,
            "source": source,
            "license": fetched.source.license,
            "id": f"mams-acsa:{rid}",
            "meta": {"task": f"mams-acsa/{variant}"},
        }


def m_absa_lines(path: Path) -> Iterator[tuple[str, list[tuple[str, str, str]]]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "####" not in line:
            continue
        text, _, label = line.rpartition("####")
        try:
            triplets = ast.literal_eval(label.strip())
        except (ValueError, SyntaxError):
            yield text, None  # type: ignore[misc]
            continue
        yield text, [tuple(map(str, t)) for t in triplets if isinstance(t, (list, tuple)) and len(t) == 3]


def convert_m_absa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Category x sentiment yes/no questions (present categories plus up to 3 absent ones from the domain's own
    inventory) and an entity-given sentiment question per explicit aspect term."""
    for path in fetched.files:
        domain = path.parts[-3]
        parsed = list(m_absa_lines(path))
        inventory = sorted({c for _, ts in parsed if ts for _, c, _ in ts})
        stats.count("domain_categories", f"{domain}:{len(inventory)}")
        for text, triplets in parsed:
            stats.input_rows += 1
            text = norm_space(text)
            if triplets is None or not text:
                stats.dropped["unparseable"] += 1
                continue
            norm = [(term, cat, POLARITY.get(pol.lower(), "")) for term, cat, pol in triplets]
            if any(s not in SENTIMENTS for _, _, s in norm):
                stats.dropped["unknown_polarity"] += 1
                continue
            rid = hashlib.sha1(f"{domain}\n{text}".encode()).hexdigest()[:16]
            rng = rng_for("m-absa", rid)
            present = {(c, s) for _, c, s in norm}
            cats = sorted({c for c, _ in present})
            absent = [c for c in inventory if c not in cats]
            rng.shuffle(absent)
            chosen = sorted(cats + absent[: min(3, len(absent))])
            if not chosen:
                stats.dropped["no_categories"] += 1
                continue
            questions, expected = pair_questions(rng, chosen, present, "text")
            terms: dict[str, set[str]] = defaultdict(set)
            for term, _, s in norm:
                if term and term.upper() != "NULL" and term in text:
                    terms[term].add(s)
            for i, (term, sentiments) in enumerate(sorted(terms.items())):
                if len(sentiments) != 1:
                    continue
                key = f"term_{i}"
                questions[key] = question("choice", f"What sentiment does the text express toward '{term}'?",
                                          {s: None for s in SENTIMENTS})
                expected[key] = next(iter(sentiments))
            stats.count("domain", domain)
            yield {
                "state": {"text": text, "domain": domain},
                "questions": questions,
                "expected": expected,
                "source": f"{fetched.source.repo}/{domain}/en",
                "license": fetched.source.license,
                "id": f"m-absa:{domain}:{rid}",
                "meta": {"task": f"m-absa/{domain}", "triplets": len(norm)},
            }


# --------------------------------------------------------------------------------------------- sarcasm

SARCASM_SINGLE = [
    ("noul", "Is this headline sarcastic, i.e. a satirical joke headline rather than a real news headline?", None),
    ("choice", "Is this news headline genuine or satirical?", {
        "genuine": "A real news headline written straight.",
        "satirical": "A sarcastic or satirical headline written as a joke."}),
]


def convert_sarcasm_headlines(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """70% single headlines (yes/no or genuine/satirical), 30% pairs: which of a sarcastic and a genuine headline
    is the sarcastic one."""
    source = f"{fetched.source.repo}/{fetched.source.config}"
    items, seen = [], set()
    for record in _parquet_batches(fetched.files, ["headline", "is_sarcastic"]):
        stats.input_rows += 1
        text = norm_space(record["headline"] or "")
        if not text or record["is_sarcastic"] not in (0, 1) or text in seen:
            stats.dropped["empty_or_duplicate"] += 1
            continue
        seen.add(text)
        items.append((hashlib.sha1(text.encode()).hexdigest()[:16], text, bool(record["is_sarcastic"])))
    genuine = [x for x in items if not x[2]]
    for rid, text, sarcastic in items:
        rng = rng_for("sarcasm-headlines", rid)
        if sarcastic and rng.random() < 0.3:
            other = genuine[rng.randrange(len(genuine))]
            first, second = ((rid, text), other[:2]) if rng.random() < 0.5 else (other[:2], (rid, text))
            yield {
                "state": "Two news headlines are given as the options; one of them is sarcastic.",
                "questions": {"answer": question("choice", "Which of these two news headlines is the sarcastic one?",
                                                 {"headline_1": first[1], "headline_2": second[1]})},
                "expected": {"answer": "headline_1" if first[0] == rid else "headline_2"},
                "source": source, "license": fetched.source.license,
                "id": f"sarcasm-headlines-pair:{first[0]}:{second[0]}",
                "meta": {"task": "sarcasm-headlines/pair"},
            }
            stats.count("variant", "pair")
            continue
        kind, instructions, criteria = SARCASM_SINGLE[rng.randrange(2)]
        target: Any = float(sarcastic) if kind == "noul" else ("satirical" if sarcastic else "genuine")
        stats.count("variant", kind)
        yield {
            "state": text,
            "questions": {"sarcastic": question(kind, instructions, criteria)},
            "expected": {"sarcastic": target},
            "source": source, "license": fetched.source.license,
            "id": f"sarcasm-headlines:{rid}",
            "meta": {"task": f"sarcasm-headlines/{kind}"},
        }


# --------------------------------------------------------------------------------------------- intents and slots

SLOT = re.compile(r"\[\s*([a-z_]+)\s*:\s*([^\]]+?)\s*\]")


def class_names(path: Path) -> dict[str, list[str]]:
    import pyarrow.parquet as pq

    meta = json.loads(pq.ParquetFile(path).schema_arrow.metadata[b"huggingface"])
    return {k: v["names"] for k, v in meta["info"]["features"].items() if v.get("_type") == "ClassLabel"}


def convert_massive(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Voice-assistant commands: intent (60-way), scenario (18-way) and which slot types the command fills."""
    names = class_names(fetched.files[0])
    intents, scenarios = names["intent"], names["scenario"]
    slot_types: set[str] = set()
    for record in _parquet_batches(fetched.files, ["annot_utt"]):
        slot_types.update(m.group(1) for m in SLOT.finditer(record["annot_utt"] or ""))
    slot_list = sorted(slot_types)
    stats.count("slot_types", len(slot_list))
    for record in _parquet_batches(fetched.files, ["id", "locale", "partition", "scenario", "intent", "utt",
                                                   "annot_utt"]):
        stats.input_rows += 1
        if record["partition"] != "train":
            stats.dropped["not_train_split"] += 1
            continue
        utt = norm_space(record["utt"] or "")
        if not utt:
            stats.dropped["empty"] += 1
            continue
        rid = f"{record['locale']}:{record['id']}"
        rng = rng_for("massive", rid)
        questions = {
            "intent": question("choice", pick(rng, [
                "Which intent does the user's request to the voice assistant express?",
                "Classify the command into one of the assistant's supported intents.",
            ]), {i: None for i in intents}),
        }
        expected: dict[str, Any] = {"intent": intents[record["intent"]]}
        if rng.random() < 0.5:
            questions["scenario"] = question("choice", "Which assistant domain (scenario) handles this request?",
                                             {s: None for s in scenarios})
            expected["scenario"] = scenarios[record["scenario"]]
        filled = {m.group(1) for m in SLOT.finditer(record["annot_utt"] or "")}
        absent = [s for s in slot_list if s not in filled]
        rng.shuffle(absent)
        for slot in sorted(filled) + absent[: max(2, len(filled))]:
            key = f"has_{slot}"
            questions[key] = question("noul", f"Does the command specify a value for the slot '{slot}' "
                                              f"({slot.replace('_', ' ')})?", None)
            expected[key] = 1.0 if slot in filled else 0.0
        stats.count("locale", record["locale"])
        yield {
            "state": utt,
            "questions": questions,
            "expected": expected,
            "source": f"{fetched.source.repo}/{record['locale']}",
            "license": fetched.source.license,
            "id": f"massive:{rid}",
            "meta": {"task": "massive/intent+slots", "locale": record["locale"]},
        }


# --------------------------------------------------------------------------------------------- fact verification, emotions, science

VITAMINC = {
    "SUPPORTS": "The evidence supports the claim.",
    "REFUTES": "The evidence contradicts the claim.",
    "NOT ENOUGH INFO": "The evidence neither supports nor contradicts the claim.",
}


def convert_vitaminc(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Claim + Wikipedia evidence sentence: 3-way verdict, or (one row in three) yes/no 'supported'."""
    source = f"{fetched.source.repo}/{fetched.source.config}"
    with fetched.files[0].open(encoding="utf-8") as handle:
        for line in handle:
            stats.input_rows += 1
            try:
                record = json.loads(line)
                claim, evidence, label = norm_space(record["claim"]), norm_space(record["evidence"]), record["label"]
            except (ValueError, KeyError, TypeError):
                stats.dropped["unparseable"] += 1
                continue
            if label not in VITAMINC or not claim or not evidence:
                stats.dropped["bad_fields"] += 1
                continue
            rid = str(record.get("unique_id") or hashlib.sha1(f"{claim}\n{evidence}".encode()).hexdigest()[:16])
            rng = rng_for("vitaminc", rid)
            if rng.random() < 1 / 3:
                q = question("noul", pick(rng, ["Is the claim fully supported by the evidence?",
                                                "Does the evidence support the claim?"]), {
                    "true": "The evidence supports the claim.",
                    "false": "The evidence contradicts the claim or does not settle it."})
                target: Any = 1.0 if label == "SUPPORTS" else 0.0
            else:
                q = question("choice", pick(rng, ["Does the evidence support or refute the claim?",
                                                  "What does the evidence say about the claim?"]), dict(VITAMINC))
                target = label
            stats.count("revision_type", record.get("revision_type"))
            yield {
                "state": {"evidence": evidence, "claim": claim, "page": norm_space(record.get("page") or "")},
                "questions": {"verdict": q},
                "expected": {"verdict": target},
                "source": source, "license": fetched.source.license,
                "id": f"vitaminc:{rid}",
                "meta": {"task": f"vitaminc/{record.get('revision_type')}"},
            }


def convert_go_emotions(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Select-all-that-apply: one yes/no per emotion (all 28), or (one row in four, single-label rows only) a
    28-way choice."""
    source = f"{fetched.source.repo}/{fetched.source.config}"
    import pyarrow.parquet as pq

    meta = json.loads(pq.ParquetFile(fetched.files[0]).schema_arrow.metadata[b"huggingface"])
    names = meta["info"]["features"]["labels"]["feature"]["names"]
    for record in _parquet_batches(fetched.files, ["id", "text", "labels"]):
        stats.input_rows += 1
        text = norm_space(record["text"] or "")
        labels = {names[i] for i in record["labels"] or [] if 0 <= i < len(names)}
        if not text or not labels:
            stats.dropped["bad_fields"] += 1
            continue
        rng = rng_for("go-emotions", record["id"])
        if len(labels) == 1 and rng.random() < 0.25:
            questions = {"emotion": question("choice", "Which emotion does the comment mainly express?",
                                             {n: None for n in names})}
            expected: dict[str, Any] = {"emotion": next(iter(labels))}
            variant = "choice"
        else:
            template = pick(rng, ["Does the comment express {e}? Judge this emotion independently of the others.",
                                  "Select every emotion the comment expresses: is {e} one of them?"])
            questions = {n: question("noul", template.format(e=n if n != "neutral" else "no particular emotion "
                                                              "(neutral)"), None) for n in names}
            expected = {n: 1.0 if n in labels else 0.0 for n in names}
            variant = "select_all"
        stats.count("variant", variant)
        yield {
            "state": text,
            "questions": questions,
            "expected": expected,
            "source": source, "license": fetched.source.license,
            "id": f"go-emotions:{record['id']}",
            "meta": {"task": f"go_emotions/{variant}", "n_labels": len(labels)},
        }


def convert_qasc(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """8-way science multiple choice; the two supporting facts are given in one row in three."""
    source = f"{fetched.source.repo}/{fetched.source.config}"
    for record in _parquet_batches(fetched.files, ["id", "question", "choices", "answerKey", "fact1", "fact2"]):
        stats.input_rows += 1
        choices = record["choices"] or {}
        options = dict(zip(choices.get("label") or [], [norm_space(t) for t in choices.get("text") or []]))
        if record["answerKey"] not in options or len(options) < 2:
            stats.dropped["bad_fields"] += 1
            continue
        rng = rng_for("qasc", record["id"])
        state: Any = norm_space(record["question"])
        if rng.random() < 1 / 3 and record["fact1"] and record["fact2"]:
            state = {"facts": [norm_space(record["fact1"]), norm_space(record["fact2"])], "question": state}
        yield {
            "state": state,
            "questions": {"answer": question("choice", "Which option correctly answers the science question?",
                                             options)},
            "expected": {"answer": record["answerKey"]},
            "source": source, "license": fetched.source.license,
            "id": f"qasc:{record['id']}",
            "meta": {"task": "qasc/with_facts" if isinstance(state, dict) else "qasc"},
        }


# --------------------------------------------------------------------------------------------- registry and main

Converter = Callable[[Fetched, Stats, Context], Iterator[dict[str, Any]]]

CONVERTERS: dict[str, Converter] = {
    "ibm-argq-30k": convert_argq,
    "ibm-claim-stance": convert_claim_stance,
    "wiki-stance-en": convert_wiki_stance,
    "mams-acsa": convert_mams,
    "m-absa-en": convert_m_absa,
    "massive-intents": convert_massive,
    "sarcasm-headlines": convert_sarcasm_headlines,
    "vitaminc": convert_vitaminc,
    "go-emotions": convert_go_emotions,
    "qasc": convert_qasc,
}


def run_source(slug: str, ctx: Context, limit: int | None) -> dict[str, Any]:
    fetched = ctx.fetched(slug)
    stats = Stats()
    target = ctx.out / f"{slug}.jsonl.gz"
    part = target.with_name(target.name + ".part")
    seen: set[str] = set()
    started = time.time()
    with gzip.open(part, "wt", encoding="utf-8", compresslevel=6) as handle:
        for row in CONVERTERS[slug](fetched, stats, ctx):
            if reason := validate_row(row):
                stats.dropped[f"invalid:{reason}"] += 1
                continue
            if row["id"] in seen:
                stats.dropped["duplicate_id"] += 1
                continue
            seen.add(row["id"])
            stats.add(row)
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            if limit and stats.rows >= limit:
                break
    part.rename(target)
    source = fetched.source
    return {
        "dataset": source.repo,
        "host": "github" if isinstance(source, GitSource) else "huggingface",
        "config": source.config,
        "revision": fetched.revision,
        "upstream_head_at_build": fetched.head,
        "files": fetched.file_meta,
        "docs_sha256": fetched.docs,
        "card_license": fetched.card_license,
        "license": source.license,
        "license_note": source.license_note,
        "output": target.name,
        "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "limit": limit,
        "seconds": round(time.time() - started, 1),
        **stats.summary(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sources", nargs="+", choices=sorted(CONVERTERS), default=list(CONVERTERS))
    parser.add_argument("--limit", type=int, default=None, help="stop each source after N output rows")
    parser.add_argument("--latest", action="store_true", help="use the current Hub head instead of the pinned sha")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "extra-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("sources", {})
    ctx = Context(args.out, args.latest)
    for slug in args.sources:
        print(f"== {slug}", file=sys.stderr)
        manifest["sources"][slug] = run_source(slug, ctx, args.limit)
        manifest["generated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest["converter"] = "research/gradiated-decide/gdecide/data/extra_sources.py"
        tmp = manifest_path.with_name(manifest_path.name + ".part")
        tmp.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
        tmp.rename(manifest_path)
        summary = manifest["sources"][slug]
        print(f"  {slug}: {summary['rows']} rows, dropped {summary['dropped_rows']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
