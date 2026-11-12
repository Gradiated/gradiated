"""Convert a broad, licence-clean mix of public QA, verification, preference and safety datasets into training rows.

Run from ``research/gradiated-decide/``::

    python -m gdecide.data.broad_sources --out ../../.agents/runtime/gdecide/data/broad [--sources ...] [--limit N]

Companion to ``gdecide.data.hub_sources`` and ``gdecide.data.extra_sources``: same output line format, same target and
validation rules (``validate_row``), same pinned anonymous downloads. Sources live on the Hugging Face Hub (pinned
dataset commit; LFS files checked against their sha256), on GitHub (pinned commit; every file checked against a sha256
recorded here) or at a fixed URL (sha256 recorded here). Downloaded files are parsed as data only (JSON, JSON lines,
CSV, parquet, zip/gzip containers of those); nothing in them is executed. Output is one ``<slug>.jsonl.gz`` per source
plus ``broad-manifest.json``. Rows then go through ``gdecide.decontam`` like every other source.

Only train splits are read. Question wording is varied per row (seeded by the row id) and so is the option-key style
(answer text as the key, or letters with the answer as the description), so that the model learns the skill rather
than a template. Choice distractors are drawn from the same document (other numbers, dates, entities, spans) and never
equal the gold answer after normalisation. Unanswerable items get an explicit ``none`` option ("Cannot be determined
from the given text"); answerable items of the same sources carry that option too, some of the time, so its presence
is not a giveaway. Long documents are chunked so that a state stays under ``MAX_STATE_WORDS`` words.

Excluded on purpose (licence or contamination): anything with GPT/Claude/Gemini-written labels or text (HelpSteer2/3
multi-turn contexts, Aegis LLM-jury and synthetic-refusal labels, hh-rlhf multi-turn prompts are filtered out row by
row), NC licences, XNLI, MMMLU/Global-MMLU, PubMedQA, BioASQ, BBH, TheoremQA, SciBench, ANLI, the HF ContractNLI
mirror, Lichess and Mind2Web.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import random
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gdecide.data.extra_sources import GitFile, GitSource, fetch_git
from gdecide.data.hub_sources import (
    MAX_OPTIONS,
    Drop,
    Fetched,
    Source,
    Stats,
    _get,
    _parquet_batches,
    char_length,
    check_question,
    clean_question,
    fetch_source,
    validate_row,
)

PREFIX = "gdecide-broad"
MAX_STATE_WORDS = 6000
#: Upper bound on a row's characters (state + instructions + options), ~10k tokens; catches scripts without spaces.
MAX_ROW_CHARS = 40_000
CHUNK_WORDS = 1800
NONE_KEY = "none"
NONE_TEXT = "Cannot be determined from the given text"


# --------------------------------------------------------------------------------------------- sources


@dataclass(frozen=True)
class UrlFile:
    url: str
    path: str
    sha256: str


@dataclass(frozen=True)
class UrlSource:
    """Files at fixed URLs, each checked against a sha256 recorded here (``revision`` names the release)."""

    slug: str
    repo: str
    config: str
    revision: str
    files: tuple[UrlFile, ...]
    license: str
    license_note: str
    docs: tuple[str, ...] = ()


BroadSource = Source | GitSource | UrlSource

SOURCES: dict[str, BroadSource] = {
    s.slug: s
    for s in (
        # ------------------------------------------------------------------ numeric reasoning over tables and text
        Source(
            slug="tatqa",
            repo="next-tat/TAT-QA",
            config="train",
            revision="c96247f5077eac447f63527fd3dcfdc58bb56d6a",
            files=r"^tatqa_dataset_train\.json$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0 (Zhu et al., ACL 2021). Hybrid tables + paragraphs from real company "
                "financial reports; questions and answers written by human annotators with finance background."
            ),
            docs=("README.md",),
        ),
        GitSource(
            slug="finqa",
            repo="czyssrs/FinQA",
            config="train",
            revision="0f16e2867befa6840783e58be38c9efb9229d742",
            files=(GitFile("dataset/train.json", "49f237eb9779b569473b26b08048867d04635a7cc39ad6a7a5664c55bb428db6"),),
            license="MIT",
            license_note=(
                "GitHub LICENSE is MIT (sha256 92c0e67b...). Earnings reports of S&P 500 companies (FinTabNet); "
                "questions and programs written by finance experts (Chen et al., EMNLP 2021). The ibm-research/finqa "
                "Hub copy is a loading script only."
            ),
            docs=("LICENSE",),
        ),
        GitSource(
            slug="convfinqa",
            repo="czyssrs/ConvFinQA",
            config="train",
            revision="cf3eed2d5984960bf06bb8145bcea5e80b0222a6",
            files=(GitFile("data.zip", "d764271fae60d81b62e6d58dfc481807ebc8cfbcd633811241723c4a2101072a"),),
            license="MIT",
            license_note=(
                "GitHub LICENSE is MIT (sha256 5c7b6fe2...). Conversational extension of FinQA written by finance "
                "experts (Chen et al., EMNLP 2022); same report pages as FinQA. Read from data.zip:data/train.json."
            ),
            docs=("LICENSE",),
        ),
        Source(
            slug="drop",
            repo="ucinlp/drop",
            config="train",
            revision="95cda593fae71b60b5b19f82de3fcf3298c1239c",
            files=r"^data/train-\d+-of-\d+\.parquet$",
            license="CC-BY-SA-4.0",
            license_note=(
                "Card licence cc-by-sa-4.0 (Dua et al., NAACL 2019). Wikipedia passages, crowd-written questions."
            ),
            docs=("README.md",),
        ),
        # ------------------------------------------------------------------ temporal reasoning
        GitSource(
            slug="timeqa",
            repo="wenhuchen/Time-Sensitive-QA",
            config="train.easy+train.hard",
            revision="38b05989070c1168b2bef3d5a2656afeeba763dc",
            files=(
                GitFile("dataset/train.easy.json.gzip",
                        "f3c7564f32f1ebd491123da0f68d33aa63031af59d55d5dadd64108a2e0e4ec5"),
                GitFile("dataset/train.hard.json.gzip",
                        "5f09b4a7e51c76fe537656a6fe2b1f0996155193103224fdb924c13def2cd914"),
            ),
            license="BSD-3-Clause",
            license_note=(
                "GitHub LICENSE is BSD-3-Clause (sha256 ba5d7b48...). Wikipedia pages with time-evolving facts "
                "(Chen et al., NeurIPS 2021 datasets track); questions from Wikidata templates, human-verified."
            ),
            docs=("LICENSE",),
        ),
        Source(
            slug="tempreason",
            repo="tonytan48/TempReason",
            config="train_l2+train_l3",
            revision="1646dea364ac667dd6098646da7d6638de00cc71",
            files=r"^train_l[23]\.json$",
            license="CC-BY-SA-3.0",
            license_note=(
                "Card licence cc-by-sa-3.0 (Tan et al., ACL 2023). Wikidata-derived time-entity facts with "
                "Wikipedia context; levels 2 (time-event) and 3 (event-event) only. Template questions, no model text."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="2wikimultihopqa",
            repo="xanhho/2WikiMultihopQA",
            config="train",
            revision="612bc5039a457880d9e7d84c3b0a4cf154b70e4f",
            files=r"^train\.parquet$",
            license="Apache-2.0",
            license_note=(
                "Hub mirror by the dataset author (Xanh Ho), card licence apache-2.0; upstream "
                "Alab-NII/2wikimultihop@13800e5b LICENSE is Apache-2.0 (sha256 b8c1d775...). Wikipedia paragraphs "
                "(CC BY-SA) and Wikidata-template questions (Ho et al., COLING 2020). Only date-comparison, "
                "comparison and compositional types are used."
            ),
            docs=("README.md",),
        ),
        # ------------------------------------------------------------------ contracts
        Source(
            slug="cuad",
            repo="theatticusproject/cuad-qa",
            config="default",
            # The Hub's parquet conversion (refs/convert/parquet); main only has a loading script.
            revision="d9c4ee0250ae2eb97bdb5b50773ab14ea62d0631",
            files=r"^default/train/\d+\.parquet$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0 (Hendrycks et al., NeurIPS 2021 datasets track). Public EDGAR contracts, "
                "clause spans labelled by law students and reviewed by attorneys (The Atticus Project)."
            ),
            docs=(),
        ),
        Source(
            slug="maud",
            repo="theatticusproject/maud",
            config="MAUD_v1/train",
            revision="37d5c3b95d18dcd8404cc5ce3fd5069be062392f",
            files=r"^MAUD_v1/MAUD_train\.csv$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0 (Wang et al., EMNLP 2023). Public EDGAR merger agreements; deal-point "
                "answers labelled by lawyers (American Bar Association deal points study)."
            ),
            docs=(),
        ),
        # ------------------------------------------------------------------ conversational rules
        UrlSource(
            slug="sharc",
            repo="sharc-data.github.io",
            config="sharc1-official/train",
            revision="sharc1-official.zip@2024-02-09",
            files=(UrlFile("https://sharc-data.github.io/data/sharc1-official.zip", "sharc1-official.zip",
                           "72dca3f4f3ba73b1d796b40e952a80d53cd2011ef90b2168b8bcaa818f5edd1e"),),
            license="CC-BY-SA-3.0",
            license_note=(
                "Official ShARC v1 release zip (Saeidi et al., EMNLP 2018). Licence CC BY-SA 3.0 per the Hub "
                "`sharc` card; the project page carries the same statement but inside an HTML comment, and the zip "
                "has no licence file. Rule texts are from UK/US/CA government pages (gov.uk under OGL v3, irs.gov "
                "public domain); questions, scenarios and dialogs written by crowd workers."
            ),
        ),
        # ------------------------------------------------------------------ multi-hop QA
        Source(
            slug="hotpotqa",
            repo="hotpotqa/hotpot_qa",
            config="distractor",
            revision="1908d6afbbead072334abe2965f91bd2709910ab",
            files=r"^distractor/train-\d+-of-\d+\.parquet$",
            license="CC-BY-SA-4.0",
            license_note="Card licence cc-by-sa-4.0 (Yang et al., EMNLP 2018). Wikipedia paragraphs, crowd questions.",
            docs=("README.md",),
        ),
        Source(
            slug="musique",
            repo="bdsaglam/musique",
            config="full/train",
            revision="22873a405dd809893b22ada0b499299fb612d2df",
            files=r"^musique_full_v1\.0_train\.jsonl$",
            license="CC-BY-4.0",
            license_note=(
                "Hub mirror (no card licence) of the official MuSiQue v1.0 release files (musique_full = answerable "
                "+ unanswerable contrast pairs). Upstream StonyBrookNLP/musique@922ac98f LICENSE is CC BY 4.0 "
                "(sha256 cce5d01f...; Trivedi et al., TACL 2022). Wikipedia paragraphs, crowd-composed questions."
            ),
            docs=("README.md",),
        ),
        # ------------------------------------------------------------------ preference and rating
        Source(
            slug="helpsteer2",
            repo="nvidia/HelpSteer2",
            config="train",
            revision="990b2711a36180dd19d9c94b8627844866f8982a",
            files=r"^train\.jsonl\.gz$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0. Prompts mostly ShareGPT user turns; responses from NVIDIA in-house models "
                "('none from proprietary LLM providers such as OpenAI'); ratings by ~1000 US human annotators. "
                "Multi-turn prompts (which carry earlier assistant turns of unknown, possibly ChatGPT, origin) are "
                "dropped: single-turn rows only."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="helpsteer3",
            repo="nvidia/HelpSteer3",
            config="preference/train",
            revision="f6d145777bcbde96137596340fab89793acd1031",
            files=r"^preference/train\.jsonl\.gz$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0. Prompts from ShareGPT/WildChat-1M user turns; responses from ~20 "
                "commercially-permissive open models ('none from proprietary LLM providers'); preferences by human "
                "annotators. Multi-turn contexts (earlier assistant turns are ChatGPT/WildChat output) are dropped: "
                "single-turn rows only."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="oasst2",
            repo="OpenAssistant/oasst2",
            config="train",
            revision="179dd21fc55192153d94adb0e0ce8f69e222bf75",
            files=r"^data/train-\d+-of-\d+-[0-9a-f]+\.parquet$",
            license="Apache-2.0",
            license_note=(
                "Card licence apache-2.0. Human-written prompts and replies, human rankings (OpenAssistant crowd); "
                "no synthetic messages kept (rows flagged synthetic are dropped)."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="stack-exchange-prefs",
            repo="HuggingFaceH4/stack-exchange-preferences",
            config="sites (Stack Overflow and meta sites excluded), <=1500 pairs per site, <=200k pairs",
            revision="c7bda74048748f55749cd663c3d8d1025a841fd9",
            files=r"^data/(?![^/]*meta\.)(?!Stackoverflow\.com/)[^/]+/train-\d+-of-\d+\.parquet$",
            license="CC-BY-SA-4.0",
            license_note=(
                "Card licence cc-by-sa-4.0 (Stack Exchange data dump, user content CC BY-SA). Answer scores are "
                "community votes. Stack Overflow (13.6 GB) and meta sites are skipped; a deterministic sample of "
                "questions per site (hash of the question id) keeps at most 200k pairs."
            ),
            docs=("README.md",),
        ),
        # ------------------------------------------------------------------ verification
        Source(
            slug="fever",
            repo="copenlu/fever_gold_evidence",
            config="train",
            revision="a6b8d891d393e97a4efac791afffb2d7de5e57c6",
            files=r"^train\.jsonl$",
            license="CC-BY-SA-3.0",
            license_note=(
                "Card licences cc-by-sa-3.0 and gpl-3.0 (both copied from the fever/fever card; the data is "
                "Wikipedia text, FEVER annotations are released under CC BY-SA 3.0; GPL-3.0 is copyleft, not NC). "
                "FEVER train claims (Thorne et al., NAACL 2018) with their gold evidence sentences; NEI claims carry "
                "sentences retrieved by the Papelo system (Malon 2018), as the brief asks (Atanasova et al., "
                "EMNLP 2020 mirror)."
            ),
            docs=("README.md",),
        ),
        GitSource(
            slug="tabfact",
            repo="wenhuchen/Table-Fact-Checking",
            config="r1+r2 train statements",
            revision="2ab782ba42b5808076ac91fec846473aa5315a79",
            files=(
                GitFile("collected_data/r1_training_all.json",
                        "fd005b4d107d576d7183330a2fb70c64303c6cad8ba486516310f14d1a7ac56e"),
                GitFile("collected_data/r2_training_all.json",
                        "7b8f19b0d082171ab00a2e81fa31b3910391f5fef24a6c5bedbe8733d742d240"),
                GitFile("data/train_id.json", "8ed3f935e955e35a2ca26c2f16efc11b6299ef676a0cc2f806092fcb9c4bbded"),
            ),
            license="CC-BY-4.0",
            license_note=(
                "GitHub LICENSE is MIT (sha256 2b53353b...); the wenhu/tab_fact Hub card says cc-by-4.0. Wikipedia "
                "tables, crowd-written statements (Chen et al., ICLR 2020). Raw (not lemmatised) statements from "
                "collected_data/, restricted to data/train_id.json tables; table text from the Hub parquet "
                "conversion (wenhu/tab_fact@cecfbe87, tab_fact/train)."
            ),
            docs=("LICENSE",),
        ),
        # ------------------------------------------------------------------ reading comprehension
        Source(
            slug="squad2",
            repo="rajpurkar/squad_v2",
            config="squad_v2",
            revision="3ffb306f725f7d2ce8394bc1873b24868140c412",
            files=r"^squad_v2/train-\d+-of-\d+\.parquet$",
            license="CC-BY-SA-4.0",
            license_note="Card licence cc-by-sa-4.0 (Rajpurkar et al., ACL 2018). Wikipedia, crowd questions.",
            docs=("README.md",),
        ),
        Source(
            slug="condaqa",
            repo="lasha-nlp/CONDAQA",
            config="train",
            revision="3c9caa2f2f6960711e7f4d2e800581def2b6c183",
            files=r"^train\.json$",
            license="Apache-2.0",
            license_note=(
                "Card licence apache-2.0 (Ravichander et al., EMNLP 2022). Wikipedia passages with negation cues, "
                "crowd-written edits, questions and answers."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="tydiqa",
            repo="google-research-datasets/tydiqa",
            config="primary_task",
            revision="da78f23f9119363459acbaf46bf89426ff26c259",
            files=r"^primary_task/train-\d+-of-\d+\.parquet$",
            license="Apache-2.0",
            license_note=(
                "Card licence apache-2.0 (Clark et al., TACL 2020). Wikipedia articles in 11 languages; questions "
                "written by native speakers before seeing the article; passage/minimal/yes-no answers human."
            ),
            docs=("README.md",),
        ),
        # ------------------------------------------------------------------ safety and toxicity
        Source(
            slug="aegis2",
            repo="nvidia/Aegis-AI-Content-Safety-Dataset-2.0",
            config="train",
            revision="d86bb8bedff51d25ac834ab7838f1cc61acb7a2c",
            files=r"^train\.json$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0. Prompts from Anthropic hh-rlhf (MIT; human-written) plus responses from "
                "Mistral-7B-v0.1. Only human labels are used: prompt labels (always human) and response labels with "
                "response_label_source == 'human'; LLM-jury (Mixtral/Mistral-NeMo/Gemma) and synthetic refusal rows "
                "are dropped, as are prompts containing earlier assistant turns (hh-rlhf assistant text is model output)."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="civil-comments",
            repo="google/civil_comments",
            config="train (sample 150k)",
            revision="f2970eb3a55777454c94069077cc8d9b5866312d",
            files=r"^data/train-\d+-of-\d+\.parquet$",
            license="CC0-1.0",
            license_note=(
                "Card licence cc0-1.0 (Borkan et al. 2019; Civil Comments platform archive, Jigsaw annotations). "
                "Toxicity is the fraction of human raters who marked the comment toxic. Deterministic 150k sample."
            ),
            docs=("README.md",),
        ),
        # ------------------------------------------------------------------ if time permits
        Source(
            slug="medmcqa",
            repo="openlifescienceai/medmcqa",
            config="train",
            revision="91c6572c454088bf71b679ad90aa8dffcd0d5868",
            files=r"^data/train-\d+-of-\d+\.parquet$",
            license="Apache-2.0",
            license_note=(
                "Card licence apache-2.0 (Pal et al., CHIL 2022). AIIMS/NEET-PG entrance exam questions with "
                "expert answer keys and explanations."
            ),
            docs=("README.md",),
        ),
        Source(
            slug="lexglue",
            repo="coastalcph/lex_glue",
            config="ledgar+unfair_tos+case_hold",
            revision="c23fdff1a6bf74e0e1a71cb86f1e781d37da888c",
            files=r"^(ledgar|unfair_tos|case_hold)/train-\d+-of-\d+\.parquet$",
            license="CC-BY-4.0",
            license_note=(
                "Card licence cc-by-4.0 (Chalkidis et al., ACL 2022). LEDGAR: EDGAR contract provisions with their "
                "headings as labels; UNFAIR-ToS: terms-of-service sentences labelled by law experts; CaseHOLD: US case "
                "law holdings (Harvard Caselaw Access Project; Zheng et al. 2021, Apache-2.0)."
            ),
            docs=("README.md",),
        ),
        GitSource(
            slug="multiwoz22",
            repo="budzianowski/multiwoz",
            config="MultiWOZ_2.2/train",
            revision="fe0c8e65cfcd8462bd33c86e35f21addc84ca82b",
            files=tuple(GitFile(f"data/MultiWOZ_2.2/train/dialogues_{i:03d}.json", sha) for i, sha in enumerate((
                "895a8109bf01fa5ecf15ccdbd2dfe1628bd923f6b61dcd2e26b10ee5076a1596",
                "2f3ea771d4e01cb2780357738cff7f7496b87d34c221cc240df74501312438d3",
                "da24961d28486be2d8462ee4d86a809db819d588ba90ae1a783383d95eb85daa",
                "30c1172db1071c853b16215d1946de908d68d2b6ff8da7801de307000a179106",
                "eaf58716df5de99524b3e0e7edf477b74749512788a6a51f53f2bdd76768d39a",
                "8e75fd543b1964bc5e7118085d977f479c98fcdf6d606b971f67a45fb1745c83",
                "02323f8298439d713c6d7d226f4bd7ec246ec993ee11911b54f98cb8a598f206",
                "1129fbed480352ae304f0ae5b4915c194e9619c43f1577ccb0d450e10d24ea98",
                "87d9e43b1ba51a4a4688703da79d3a09b14d8013570545da24c597daa18e2f45",
                "e7ad0d5da2909b08197295e45fe4695b9dc2f67d458374b2aab8db5094e97b26",
                "82e2d2900a037b866a01d05974734dd419e89b329fe29ef93b35eea96d27feb8",
                "b6bf292325db67682dd7b6fafbf1051cc2262e92f7c37cab213e975888594bb2",
                "c33fe4b3952c016e1e1645f472a7097f93dfb476a19940fd9386865ef9adf685",
                "ce33dbbf93a40d0dcc671a9d6a2ed1f987914f5b5f05f6df493a5b342efda954",
                "d895c0439bc2ad89ef1689896e3be630eadebc33dae77b42a426fd16a271718e",
                "3e6bc0bca4262022ccbce0d5ce3150e536e7d21aeb9fbdef9e83cced4dfd124b",
                "b6ab2cd9b6e8983364526845b7cbec1749338209bf7ac2313c25e1e2226ebab5",
            ), start=1)) + (GitFile("data/MultiWOZ_2.2/schema.json",
                                    "ae9e2390f38fb967af64623c2f4f7e0c636fb377ad523b582a03161d3ddbdf68"),),
            license="MIT",
            license_note=(
                "GitHub LICENSE is MIT (sha256 d84d5c02...). Wizard-of-Oz dialogues written by crowd workers "
                "(Budzianowski et al. 2018); 2.2 annotation fixes and active-intent labels by Zang et al. 2020."
            ),
            docs=("LICENSE",),
        ),
        Source(
            slug="commonsenseqa",
            repo="tau/commonsense_qa",
            config="train",
            revision="94630fe30dad47192a8546eb75f094926d47e155",
            files=r"^data/train-\d+-of-\d+\.parquet$",
            license="MIT",
            license_note="Card licence mit (Talmor et al., NAACL 2019). Crowd-written questions over ConceptNet.",
            docs=("README.md",),
        ),
    )
}

#: Sources considered and not built, with the reason (kept in the manifest).
SKIPPED: dict[str, str] = {
    "feverous": (
        "fever/feverous (CC-BY-SA-3.0) only carries evidence ids into the FEVEROUS Wikipedia database (a separate "
        "multi-GB SQLite download); no Hub mirror with evidence text was found. Skipped rather than built without "
        "evidence."
    ),
    "conditionalqa": (
        "haitian-sun/ConditionalQA has no licence file or statement; README says 'should ONLY be used for NLP "
        "research purpose'. Unclear/research-only: skipped."
    ),
    "snli-annotator-votes": (
        "Annotator votes are only in snli_1.0.zip on nlp.stanford.edu, which is unreachable from the build host; "
        "the Hub copy (stanfordnlp/snli) carries the gold label only. Skipped rather than built without soft labels."
    ),
    "socialiqa": (
        "allenai/social_i_qa has no card licence (loading script only) and the upstream zip has no licence file. "
        "Unclear: skipped."
    ),
}


#: Files a converter needs from a second location (not converted on their own).
AUX_SOURCES: dict[str, Source] = {
    "tabfact-tables": Source(
        slug="tabfact-tables",
        repo="wenhu/tab_fact",
        config="tab_fact",
        revision="cecfbe87432b0e7fdcac4578f8ac6fc87d08db76",
        files=r"^tab_fact/train/\d+\.parquet$",
        license="CC-BY-4.0",
        license_note="Hub parquet conversion (refs/convert/parquet) of wenhu/tab_fact; used for table text only.",
        docs=(),
    ),
}


# --------------------------------------------------------------------------------------------- download


def fetch_url(source: UrlSource, out: Path) -> Fetched:
    raw = out / "_raw" / source.slug / re.sub(r"[^A-Za-z0-9._@-]+", "_", source.revision)
    paths, meta = [], []
    for item in source.files:
        target = raw / item.path
        if not (target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == item.sha256):
            target.parent.mkdir(parents=True, exist_ok=True)
            print(f"  fetch {item.url}", file=sys.stderr)
            with _get(item.url, timeout=300) as response:
                data = response.read()
            digest = hashlib.sha256(data).hexdigest()
            if digest != item.sha256:
                raise RuntimeError(f"{item.url}: sha256 {digest} != pinned {item.sha256}")
            target.write_bytes(data)
        paths.append(target)
        meta.append({"file": item.url, "size": target.stat().st_size, "sha256": item.sha256})
    return Fetched(source, source.revision, None, paths, meta, {}, None)  # type: ignore[arg-type]


@dataclass
class Context:
    out: Path
    latest: bool

    def fetched(self, slug: str) -> Fetched:
        source = SOURCES[slug] if slug in SOURCES else AUX_SOURCES[slug]
        if isinstance(source, GitSource):
            return fetch_git(source, self.out)
        if isinstance(source, UrlSource):
            return fetch_url(source, self.out)
        return fetch_source(source, self.out, self.latest)


# --------------------------------------------------------------------------------------------- helpers


def rng_for(*parts: Any) -> random.Random:
    return random.Random(hashlib.sha256(":".join([PREFIX, *map(str, parts)]).encode()).digest())


def unit(*parts: Any) -> float:
    """A deterministic number in [0, 1) for sampling decisions."""
    digest = hashlib.sha256(":".join([PREFIX, "unit", *map(str, parts)]).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def pick(rng: random.Random, options: list[str]) -> str:
    return options[rng.randrange(len(options))]


def norm_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def n_words(text: str) -> int:
    return len(text.split())


def question(kind: str, instructions: str, criteria: Any) -> dict[str, Any]:
    q = clean_question(kind, instructions, criteria)
    if reason := check_question(q):
        raise Drop(reason)
    return q


def answer_key(text: Any) -> str:
    """Normalisation used to compare answers and distractors (case, punctuation, a leading article)."""
    text = str(text).lower().replace("–", "-").replace("−", "-")
    text = re.sub(r"^\s*(a|an|the)\s+", " ", text)
    text = re.sub(r"[^\w\s.%-]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .")


NUMBER = re.compile(r"(?<![\w.])\(?-?\$?\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?%?(?![\w])")


def parse_number(text: Any) -> float | None:
    """A number from a short answer string ('$1,234.5', '(23)', '-4.1%', '12 million'); None if not numeric."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text) if math.isfinite(text) else None
    s = str(text).strip().lower().replace("−", "-").replace("–", "-")
    s = re.sub(r"\s*(thousand|million|billion|percent|%|usd|dollars?)\s*$", "", s).strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace(" ", "")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?|-?\.\d+", s):
        return None
    value = float(s)
    return -value if negative else value


def same_number(a: float, b: float) -> bool:
    """Equal after normalisation: within 0.5% (rounding), or off by a percent/fraction factor of 100."""
    for x in (b, b * 100, b / 100):
        if abs(a - x) <= max(1e-9, 0.005 * max(abs(a), abs(x))):
            return True
    return False


def fmt_like(value: float, like: str) -> str:
    """Format ``value`` the way ``like`` (a gold answer string) is written: decimals, $, %, thousands separators."""
    like = str(like).strip()
    decimals = len(like.split(".")[1].rstrip("%) ").split()[0]) if re.search(r"\d\.\d", like) else 0
    decimals = min(decimals, 4)
    text = f"{abs(value):,.{decimals}f}" if "," in like else f"{abs(value):.{decimals}f}"
    if "$" in like:
        text = "$" + text
    if value < 0:
        text = f"({text})" if like.startswith("(") else "-" + text
    if like.endswith("%"):
        text += "%"
    return text


def fmt_num(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    if abs(value) >= 100:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.4g}"


def numbers_in(text: str) -> list[str]:
    out = []
    for match in NUMBER.finditer(text):
        token = match.group(0).strip()
        if token.startswith("(") != token.endswith(")"):
            token = token.strip("()")
        if parse_number(token) is not None:
            out.append(token)
    return out


MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
          "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
DATE = re.compile(
    rf"\b(?:\d{{1,2}} (?:{MONTHS})\.? \d{{3,4}}|(?:{MONTHS})\.? \d{{1,2}},? \d{{3,4}}|(?:{MONTHS})\.?,? \d{{3,4}})\b"
)
YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_WORD = r"(?:[A-Z]\.\s?)*[A-Z][\w'\u2019]*(?:-[\w'\u2019]+)*"
ENTITY = re.compile(rf"\b{_WORD}(?:\s+(?:(?:of|the|de|von|van|for|da|di|du|la|le)\s+)?{_WORD})*")


FUNCTION_WORDS = set("""a an the as at by for from in into of on to with and but or nor so yet it its he she they we you i
his her their our your this that these those there here when while after before during since until although though
however because if then also both each either neither all any some many most other such only one two three after
following despite according meanwhile later earlier today yesterday""".split())


def kind_of(gold: str) -> str:
    g = gold.strip()
    if YEAR.fullmatch(g):
        return "year"
    if DATE.fullmatch(g):
        return "date"
    if parse_number(g) is not None:
        return "number"
    if answer_key(g) in ("yes", "no"):
        return "yesno"
    return "entity"


def typed_candidates(gold: str, text: str, extra: Iterable[str] = ()) -> list[str]:
    """Candidates from ``text`` of the same kind as ``gold`` (numbers, years, dates, capitalised entity-like spans,
    or lower-case phrases of the same length for a lower-case gold)."""
    kind = kind_of(gold)
    if kind == "number":
        pool = numbers_in(text)
    elif kind == "year":
        pool = YEAR.findall(text)
    elif kind == "date":
        pool = DATE.findall(text)
    elif gold[:1].islower():
        size = n_words(gold)
        tokens = re.findall(r"\b\w[\w'-]*", text)
        pool = [" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]
        pool = [p for p in pool if p[:1].islower() and p.split()[0] not in FUNCTION_WORDS
                and p.split()[-1].lower() not in FUNCTION_WORDS and len(p) >= 4]
    else:
        size = n_words(gold)
        found = [re.sub(r"['\u2019]s$", "", e) for e in ENTITY.findall(text)]
        found = [e for e in found if len(e) >= 3 and not (n_words(e) == 1 and e.lower() in FUNCTION_WORDS)
                 and e.split()[0].lower() not in ("the", "a", "an", "in", "on", "at", "after", "as", "by")]
        pool = [e.strip(" .,'") for e in (*extra, *found)]
        pool = [e for e in pool if e and abs(n_words(e) - size) <= max(1, size // 2) and len(e) <= 120]
        if not pool:
            pool = [e.strip() for e in extra]
    return list(dict.fromkeys(p for p in pool if p))


def same_kind_fill(gold: str) -> list[str]:
    """Synthetic same-kind candidates for numeric, year and date golds (used when the text has too few)."""
    kind = kind_of(gold)
    if kind == "year":
        year = int(gold.strip())
        return [str(year + d) for d in (-10, -5, -3, -2, -1, 1, 2, 3, 5, 10)]
    if kind == "number":
        value = parse_number(gold)
        assert value is not None
        steps = (-3, -2, -1, 1, 2, 3, 5) if value == int(value) and abs(value) < 100 else ()
        return [fmt_like(value + d, gold) for d in steps] + [fmt_like(value * f, gold)
                                                             for f in (0.5, 0.75, 1.25, 1.5, 2)]
    if kind == "date":
        match = YEAR.search(gold)
        if match:
            year = int(match.group(0))
            return [gold.replace(match.group(0), str(year + d)) for d in (-3, -2, -1, 1, 2, 3)]
    return []


def distinct_distractors(gold: list[str], pool: Iterable[str], rng: random.Random, n: int) -> list[str]:
    """Up to ``n`` distractors from ``pool``: no duplicates, none equal to (or containing / contained in) a gold
    answer after normalisation, none numerically equal to a numeric gold."""
    gold_keys = [answer_key(g) for g in gold]
    gold_nums = [x for x in (parse_number(g) for g in gold) if x is not None]
    seen: set[str] = set()
    out = []
    candidates = list(dict.fromkeys(p for p in pool if isinstance(p, str) and p.strip()))
    rng.shuffle(candidates)
    for cand in candidates:
        key = answer_key(cand)
        if not key or key in seen:
            continue
        if any(key == g or (len(g) > 3 and (g in key or key in g)) for g in gold_keys):
            continue
        number = parse_number(cand)
        if number is not None and any(same_number(number, g) for g in gold_nums):
            continue
        if number is not None and any(n2 is not None and same_number(number, n2)
                                      for n2 in (parse_number(s) for s in out)):
            continue
        seen.add(key)
        out.append(cand.strip())
        if len(out) >= n:
            break
    return out


def passage_distractors(golds: list[str], text: str, rng: random.Random, n: int, extra: Iterable[str] = (),
                        first: Iterable[str] = ()) -> list[str]:
    """Up to ``n`` same-kind distractors: ``first`` (e.g. bridge answers), then candidates from ``text``, then
    synthetic same-kind values (years, numbers, dates) if the text has too few."""
    gold = golds[0]
    picked = distinct_distractors(golds, list(first), rng, max(0, min(2, n - 2)))
    picked += distinct_distractors(golds + picked, typed_candidates(gold, text, extra), rng, n - len(picked))
    if len(picked) < n:
        picked += distinct_distractors(golds + picked, same_kind_fill(gold), rng, n - len(picked))
    return picked


def numeric_derivations(gold: float, numbers: list[float], rng: random.Random, like: str) -> list[str]:
    """Plausible wrong results: nearby scalings of the gold and simple arithmetic over numbers in the document."""
    out = [gold * f for f in (1.1, 0.9, 1.25, 0.75, 2, 0.5)] + [-gold]
    nums = [x for x in numbers if x != 0][:40]
    for _ in range(12):
        if len(nums) < 2:
            break
        a, b = rng.sample(nums, 2)
        out += [a - b, a + b, (a - b) / b * (100 if like.endswith("%") else 1)]
    return [fmt_like(x, like) for x in out if math.isfinite(x)]


def choice_from(rng: random.Random, gold: list[str], distractors: list[str], instructions: str, *,
                none: str = "absent", letters: float = 0.4) -> tuple[dict[str, Any], Any]:
    """A ``choice`` question over gold + distractors (shuffled). ``none``: 'absent' (no none option), 'option' (a
    none option, gold is a listed answer) or 'gold' (unanswerable: the none option is the target). Keys are the answer
    texts themselves or letters with the answer as the description (``letters`` = probability of letters)."""
    gold = [] if none == "gold" else list(dict.fromkeys(g.strip() for g in gold if g.strip()))
    texts = gold + [d for d in distractors if d.strip()]
    if len(texts) < 2 and none == "absent":
        raise Drop("too_few_options")
    if not texts:
        raise Drop("no_options")
    rng.shuffle(texts)
    if len(texts) + (none != "absent") > MAX_OPTIONS:
        raise Drop("too_many_options")
    use_letters = rng.random() < letters or any(len(t) > 80 for t in texts) or len({t for t in texts}) != len(texts)
    use_letters = use_letters or any(t.lower() == NONE_KEY for t in texts)
    if use_letters:
        labels = [chr(ord("A") + i) if i < 26 else f"option_{i + 1}" for i in range(len(texts))]
        criteria: dict[str, Any] = dict(zip(labels, texts, strict=True))
        key_of = dict(zip(texts, labels, strict=True))
    else:
        criteria = {t: None for t in texts}
        key_of = {t: t for t in texts}
    if none != "absent":
        criteria[NONE_KEY] = NONE_TEXT
    q = question("choice", instructions, criteria)
    if none == "gold":
        return q, NONE_KEY
    if len(gold) == 1:
        return q, key_of[gold[0]]
    return q, {key_of[g]: round(1 / len(gold), 6) for g in gold}


def table_text(rows: list[list[Any]], rng: random.Random) -> str:
    rows = [[norm_space(c) for c in row] for row in rows if any(norm_space(c) for c in row)]
    if not rows:
        return ""
    style = rng.randrange(3)
    if style == 0:
        lines = ["| " + " | ".join(r) + " |" for r in rows]
        lines.insert(1, "|" + "---|" * len(rows[0]))
        return "\n".join(lines)
    if style == 1:
        return "\n".join("\t".join(r) for r in rows)
    header = rows[0]
    out = []
    for r in rows[1:]:
        cells = [f"{h or 'value'}: {c}" for h, c in zip(header[1:], r[1:], strict=False) if c]
        out.append(f"{r[0]} - " + "; ".join(cells) if r[0] else "; ".join(cells))
    return " | ".join(header) + "\n" + "\n".join(out)


def table_comparisons(rows: list[list[Any]], rng: random.Random, n: int) -> list[tuple[str, bool]]:
    """'Is <row> in <col A> greater than in <col B>?' over rows with two numeric cells that differ."""
    if len(rows) < 2:
        return []
    header = [norm_space(c) for c in rows[0]]
    out = []
    body = list(rows[1:])
    rng.shuffle(body)
    for row in body:
        label = norm_space(row[0]) if row else ""
        cells = [(header[i] if i < len(header) else "", parse_number(norm_space(c))) for i, c in enumerate(row)][1:]
        cells = [(h, v) for h, v in cells if h and v is not None]
        if not label or len(cells) < 2 or len(label) > 120:
            continue
        (ha, va), (hb, vb) = rng.sample(cells, 2)
        if va == vb or ha == hb:
            continue
        out.append((f"According to the table, is the value of '{label}' for {ha} greater than for {hb}?", va > vb))
        if len(out) >= n:
            break
    return out


def fit_paragraphs(paragraphs: list[str], keep: Iterable[str], budget: int = MAX_STATE_WORDS) -> list[str]:
    """Paragraphs within ``budget`` words: all if they fit, else the ones mentioning a ``keep`` string first,
    then their neighbours, in document order."""
    sizes = [n_words(p) for p in paragraphs]
    if sum(sizes) <= budget:
        return paragraphs
    keys = [k.lower() for k in keep if k and len(k) > 1]
    chosen: set[int] = {i for i, p in enumerate(paragraphs) if any(k in p.lower() for k in keys)}
    total = sum(sizes[i] for i in chosen)
    if total > budget:
        chosen, total = set(), 0
        for i in sorted({i for i, p in enumerate(paragraphs) if any(k in p.lower() for k in keys)}):
            if total + sizes[i] <= budget:
                chosen.add(i)
                total += sizes[i]
    for radius in range(1, len(paragraphs)):
        grew = False
        for i in sorted(chosen):
            for j in (i - radius, i + radius):
                if 0 <= j < len(paragraphs) and j not in chosen and total + sizes[j] <= budget:
                    chosen.add(j)
                    total += sizes[j]
                    grew = True
        if not grew and chosen:
            break
    if not chosen:
        for i, size in enumerate(sizes):
            if total + size > budget:
                break
            chosen.add(i)
            total += size
    return [paragraphs[i] for i in sorted(chosen)]


def chunk_words(text: str, size: int | None = None) -> list[tuple[int, int]]:
    """Character spans of ~``size``-word chunks covering ``text``, cut at a blank line or line break in the second
    half of the window when there is one."""
    size = size or CHUNK_WORDS
    tokens = [m.start() for m in re.finditer(r"\S+", text)]
    spans, i = [], 0
    while i < len(tokens):
        j = min(len(tokens), i + size)
        if j < len(tokens):
            window = text[tokens[i]:tokens[j]]
            cut = window.rfind("\n\n")
            if cut < len(window) // 2:
                cut = window.rfind("\n")
            if cut > len(window) // 2:
                j = max(i + 1, bisect.bisect_left(tokens, tokens[i] + cut, i + 1, j))
        spans.append((tokens[i], tokens[j] if j < len(tokens) else len(text)))
        i = j
    return spans


def qa_wording(rng: random.Random, qtext: str, state: dict[str, Any], templates: list[str],
               generic: list[str]) -> str:
    """Put the question either into the instructions (one of ``templates`` with {q}) or into the state with a
    generic instruction."""
    if rng.random() < 0.5:
        return pick(rng, templates).format(q=qtext)
    state["question"] = qtext
    return pick(rng, generic)


QA_TEMPLATES = [
    "{q}",
    "Answer the question using the text: {q}",
    "Based only on the given text, {q}",
    "Question: {q} Which option is the correct answer?",
]
QA_GENERIC = [
    "Which option answers the question?",
    "Pick the correct answer to the question from the options.",
    "Using the given context, choose the answer to the question.",
]
NUM_TEMPLATES = [
    "{q}",
    "Using the table and the report text, answer: {q}",
    "Compute the answer from the financial report: {q}",
]
NUM_GENERIC = [
    "Which option is the correct answer to the question about the report?",
    "Using the table and text, which value answers the question?",
    "Select the correct result.",
]


def none_mode(rng: random.Random, answerable: bool, p_option: float = 0.3) -> str:
    if not answerable:
        return "gold"
    return "option" if rng.random() < p_option else "absent"


def row(fetched: Fetched, rid: str, state: Any, questions: dict[str, Any], expected: dict[str, Any], task: str,
        source: str | None = None, **meta: Any) -> dict[str, Any]:
    return {
        "state": state,
        "questions": questions,
        "expected": expected,
        "source": source or f"{fetched.source.repo}/{fetched.source.config}",
        "license": fetched.source.license,
        "id": rid,
        "meta": {"task": task, **{k: v for k, v in meta.items() if v is not None}},
    }


def load_json(path: Path) -> Any:
    opener = gzip.open if path.suffix in (".gz", ".gzip") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def json_lines(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix in (".gz", ".gzip") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def numeric_choice(rng: random.Random, gold_text: str, doc_text: str, instructions: str, suffix: str = "",
                   n: int | None = None) -> tuple[dict[str, Any], Any]:
    """Choice over a numeric gold plus 3-5 distractors: numbers from the document and plausible derivations, kept
    within a factor of 20 of the gold when there are enough such candidates (years only for year-like golds)."""
    gold = parse_number(gold_text)
    if gold is None:
        raise Drop("gold_not_numeric")
    like = gold_text.strip()
    yearish = like.isdigit() and 1900 <= gold <= 2100
    values = [v for v in (parse_number(x) for x in numbers_in(doc_text)) if v is not None]
    if not yearish:
        values = [v for v in values if not (v == int(v) and 1900 <= v <= 2100)]

    def near(xs: list[float]) -> list[float]:
        if gold == 0:
            return xs
        close = [x for x in xs if x != 0 and 0.05 <= abs(x / gold) <= 20]
        return close if len(close) >= 3 else xs

    n = n or rng.randint(3, 5)
    from_doc = distinct_distractors([like], [fmt_like(v, like) for v in near(values)], rng, n)
    derived_values = [v for v in (parse_number(x) for x in numeric_derivations(gold, values, rng, like)) if v is not None]
    derived = distinct_distractors([like, *from_doc], [fmt_like(v, like) for v in near(derived_values)], rng, n)
    pool = from_doc[: max(1, n - 2)] + derived
    distractors = distinct_distractors([like], pool, rng, n)
    if len(distractors) < 2:
        raise Drop("too_few_distractors")
    return choice_from(rng, [like + suffix], [d + suffix for d in distractors], instructions)


def sentences_of(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 4]


# --------------------------------------------------------------------------------------------- 1. numeric QA


TATQA_SCALE = {"thousand": " thousand", "million": " million", "billion": " billion", "": "", "percent": ""}


def convert_tatqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for doc in load_json(fetched.files[0]):
        table = (doc.get("table") or {}).get("table") or []
        paragraphs = [norm_space(p.get("text")) for p in sorted(doc.get("paragraphs") or [],
                                                                  key=lambda p: p.get("order", 0))]
        doc_uid = (doc.get("table") or {}).get("uid") or hashlib.sha1(json.dumps(table).encode()).hexdigest()[:16]
        flat_table = " ".join(" ".join(map(str, r)) for r in table)
        doc_text = flat_table + " " + " ".join(paragraphs)
        cells = [norm_space(c) for r in table for c in r if norm_space(c) and parse_number(norm_space(c)) is None]
        spans = [a for q in doc.get("questions") or [] if q.get("answer_type") == "span"
                 for a in (q["answer"] if isinstance(q.get("answer"), list) else [q.get("answer")]) if a]
        for qd in doc.get("questions") or []:
            stats.input_rows += 1
            rid = f"tatqa:{qd['uid']}"
            rng = rng_for(rid)
            state: dict[str, Any] = {"table": table_text(table, rng), "paragraphs": "\n\n".join(paragraphs)}
            kind, answer, scale = qd.get("answer_type"), qd.get("answer"), qd.get("scale") or ""
            try:
                if kind == "multi-span" or (isinstance(answer, list) and len(answer) != 1):
                    raise Drop("multi_span")
                text = str(answer[0] if isinstance(answer, list) else answer).strip()
                instructions = qa_wording(rng, norm_space(qd["question"]), state, NUM_TEMPLATES, NUM_GENERIC)
                if parse_number(text) is not None:
                    number = parse_number(text)
                    like = (fmt_num(number) if kind == "arithmetic" else text)
                    if scale == "percent" and not like.endswith("%"):
                        like += "%"
                    if kind == "count":
                        distractors = [str(int(number) + d) for d in (-2, -1, 1, 2, 3) if int(number) + d >= 0]
                        rng.shuffle(distractors)
                        q, target = choice_from(rng, [like], distractors[: rng.randint(3, 4)], instructions)
                    else:
                        q, target = numeric_choice(rng, like, doc_text, instructions, TATQA_SCALE.get(scale, ""))
                    variant = f"numeric/{kind}"
                elif n_words(text) > 6:
                    pool = [x for x in sentences_of(" ".join(paragraphs)) if abs(n_words(x) - n_words(text)) <= 15]
                    distractors = distinct_distractors([text], pool, rng, rng.randint(3, 4))
                    if len(distractors) < 2:
                        raise Drop("too_few_distractors")
                    q, target = choice_from(rng, [text], distractors, instructions)
                    variant = "span_long"
                else:
                    pool = cells + spans + typed_candidates(text, " ".join(paragraphs))
                    distractors = distinct_distractors([text], pool, rng, rng.randint(3, 5))
                    if len(distractors) < 2:
                        raise Drop("too_few_distractors")
                    q, target = choice_from(rng, [text], distractors, instructions)
                    variant = "span"
            except Drop as error:
                stats.dropped[error.reason] += 1
                continue
            stats.count("variant", variant)
            yield row(fetched, rid, state, {"answer": q}, {"answer": target}, f"tatqa/{variant}",
                      answer_from=qd.get("answer_from"))
        # Table comparisons: one row per document with up to two yes/no questions.
        rng = rng_for("tatqa-compare", doc_uid)
        comparisons = table_comparisons(table, rng, 2)
        if comparisons:
            state = {"table": table_text(table, rng), "paragraphs": "\n\n".join(paragraphs)}
            questions = {f"compare_{i}": question("noul", text, None) for i, (text, _) in enumerate(comparisons)}
            expected = {f"compare_{i}": 1.0 if truth else 0.0 for i, (_, truth) in enumerate(comparisons)}
            stats.count("variant", "compare")
            yield row(fetched, f"tatqa-compare:{doc_uid}", state, questions, expected, "tatqa/compare")


def finqa_state(doc: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    return {
        "text_before_table": norm_space(" ".join(doc.get("pre_text") or [])),
        "table": table_text(doc.get("table_ori") or doc.get("table") or [], rng),
        "text_after_table": norm_space(" ".join(doc.get("post_text") or [])),
    }


def doc_numbers_text(doc: dict[str, Any]) -> str:
    table = doc.get("table_ori") or doc.get("table") or []
    return " ".join(" ".join(map(str, r)) for r in table) + " " + " ".join(doc.get("pre_text") or []) + " " + \
        " ".join(doc.get("post_text") or [])


def convert_finqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for doc in load_json(fetched.files[0]):
        stats.input_rows += 1
        qa = doc.get("qa") or {}
        rid = f"finqa:{doc['id']}"
        rng = rng_for(rid)
        state = finqa_state(doc, rng)
        questions, expected = {}, {}
        answer = str(qa.get("answer") or "").strip()
        exe = qa.get("exe_ans")
        try:
            instructions = qa_wording(rng, norm_space(qa.get("question")), state, NUM_TEMPLATES, NUM_GENERIC)
            if answer.lower() in ("yes", "no") or exe in ("yes", "no"):
                questions["answer"] = question("noul", instructions, None)
                expected["answer"] = 1.0 if (answer.lower() or exe) == "yes" else 0.0
                variant = "yesno"
            else:
                number = parse_number(answer)
                if number is None or (isinstance(exe, (int, float)) and not same_number(number, float(exe))):
                    if not isinstance(exe, (int, float)):
                        raise Drop("no_numeric_answer")
                    stats.count("answer_text_disagrees_with_exe_ans", number is not None)
                    answer = fmt_num(float(exe))
                questions["answer"], expected["answer"] = numeric_choice(rng, answer, doc_numbers_text(doc),
                                                                         instructions)
                variant = "numeric"
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        for i, (text, truth) in enumerate(table_comparisons(doc.get("table_ori") or [], rng, 1)):
            questions[f"compare_{i}"] = question("noul", text, None)
            expected[f"compare_{i}"] = 1.0 if truth else 0.0
            stats.count("comparisons", 1)
        stats.count("variant", variant)
        yield row(fetched, rid, state, questions, expected, f"finqa/{variant}")


def convert_convfinqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    with zipfile.ZipFile(fetched.files[0]) as archive:
        docs = json.loads(archive.read("data/train.json"))
    for doc in docs:
        stats.input_rows += 1
        ann = doc.get("annotation") or {}
        turns, answers = ann.get("dialogue_break") or [], ann.get("exe_ans_list") or []
        if not turns or len(turns) != len(answers):
            stats.dropped["bad_dialogue"] += 1
            continue
        rid = f"convfinqa:{doc['id']}"
        rng = rng_for(rid)
        k = rng.randrange(len(turns))
        if not isinstance(answers[k], (int, float)):
            stats.dropped["non_numeric_turn"] += 1
            continue
        state: dict[str, Any] = finqa_state(doc, rng)
        state["conversation"] = [{"question": norm_space(turns[i]), "answer": fmt_num(float(answers[i]))
                                  if isinstance(answers[i], (int, float)) else str(answers[i])} for i in range(k)]
        instructions = pick(rng, [
            "Continue the conversation about the report: {q}",
            "Given the earlier questions and answers, what is the answer to the next question: {q}",
            "{q}",
        ]).format(q=norm_space(turns[k]))
        try:
            q, target = numeric_choice(rng, fmt_num(float(answers[k])), doc_numbers_text(doc), instructions)
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        stats.count("turn", k)
        yield row(fetched, rid, state, {"answer": q}, {"answer": target}, "convfinqa/turn", turn=k)


def convert_drop(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for record in _parquet_batches(fetched.files, ["section_id", "query_id", "passage", "question", "answers_spans"]):
        stats.input_rows += 1
        spans = (record["answers_spans"] or {}).get("spans") or []
        types = (record["answers_spans"] or {}).get("types") or []
        if len(set(spans)) != 1:
            stats.dropped["multi_or_no_span"] += 1
            continue
        gold, kind = spans[0].strip(), (types[0] if types else "span")
        passage = norm_space(record["passage"])
        rid = f"drop:{record['query_id']}"
        rng = rng_for(rid)
        state: dict[str, Any] = {"passage": passage}
        instructions = qa_wording(rng, norm_space(record["question"]), state, QA_TEMPLATES, QA_GENERIC)
        pool = typed_candidates(gold, passage) + same_kind_fill(gold)
        number = parse_number(gold)
        if number is not None:
            pool += [fmt_num(number + d) for d in (-3, -2, -1, 1, 2, 3, 5, 7) if number + d >= 0]
            values = [v for v in (parse_number(x) for x in numbers_in(passage)) if v is not None]
            pool += [fmt_num(abs(a - b)) for a in values[:8] for b in values[:8] if a != b]
        distractors = distinct_distractors([gold], pool, rng, rng.randint(3, 5))
        if number is not None:
            # Prefer passage numbers, then derivations, but keep the passage-first order deterministic.
            distractors = distractors[:5]
        try:
            q, target = choice_from(rng, [gold], distractors, instructions)
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        stats.count("answer_type", kind)
        yield row(fetched, rid, state, {"answer": q}, {"answer": target}, f"drop/{kind}",
                  section=record["section_id"])


# --------------------------------------------------------------------------------------------- 3. temporal reasoning

TIME_GENERIC = [
    "Which option answers the time-sensitive question?",
    "Using the dates in the text, choose the correct answer.",
    "Pick the answer that holds at the time the question asks about.",
]
TIME_TEMPLATES = [
    "{q}",
    "Pay attention to the time constraint. {q}",
    "Based on the document, {q}",
]


def convert_timeqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Choice among the values the same entity/relation takes at other times (from the question group), plus
    ``none`` when the question has no answer in the document."""
    records = []
    for path in fetched.files:
        level = "easy" if ".easy." in path.name else "hard"
        records += [(level, r) for r in json_lines(path)]
    values: dict[str, set[str]] = defaultdict(set)
    for _, record in records:
        group = record["idx"].rsplit("#", 1)[0]
        values[group].update(t.strip() for t in record.get("targets") or [] if t and t.strip())
    for level, record in records:
        stats.input_rows += 1
        golds = [t.strip() for t in record.get("targets") or [] if t and t.strip()]
        group = record["idx"].rsplit("#", 1)[0]
        rid = f"timeqa:{level}:{record['idx']}"
        rng = rng_for(rid)
        mode = none_mode(rng, bool(golds), 0.3)
        others = sorted(values[group] - set(golds))
        distractors = distinct_distractors(golds, others, rng, rng.randint(3, 5))
        if len(distractors) + len(golds) < 2:
            stats.dropped["too_few_values_in_group"] += 1
            continue
        paragraphs = [norm_space(f"{p.get('title', '')}: {p.get('text', '')}") for p in record.get("paragraphs") or []]
        paragraphs = fit_paragraphs(paragraphs, golds + distractors)
        state: dict[str, Any] = {"document": "\n\n".join(paragraphs)}
        instructions = qa_wording(rng, norm_space(record["question"]), state, TIME_TEMPLATES, TIME_GENERIC)
        try:
            q, target = choice_from(rng, golds, distractors, instructions, none=mode)
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        stats.count("answerable", bool(golds))
        yield row(fetched, rid, state, {"answer": q}, {"answer": target}, f"timeqa/{level}",
                  answerable=bool(golds))


def convert_tempreason(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """L2 (time-event) and L3 (event-event): choice among the entity values of the same subject and relation
    (``neg_answers``); the context is either the structured fact list or the Wikipedia page."""
    for path in fetched.files:
        level = "L2" if "l2" in path.name else "L3"
        for record in json_lines(path):
            stats.input_rows += 1
            golds = [t.strip() for t in (record.get("text_answers") or {}).get("text") or [] if t.strip()]
            rid = f"tempreason:{record['id']}"
            rng = rng_for(rid)
            distractors = distinct_distractors(golds, record.get("neg_answers") or [], rng, rng.randint(3, 5))
            if not golds or len(distractors) < 2:
                stats.dropped["too_few_values"] += 1
                continue
            facts = [norm_space(x) for x in (record.get("fact_context") or "").split("\n") if x.strip()]
            if rng.random() < 0.5 and facts:
                rng.shuffle(facts)
                state: dict[str, Any] = {"facts": facts}
                setting = "facts"
            else:
                text = norm_space(record.get("context") or "")
                if not text:
                    stats.dropped["no_context"] += 1
                    continue
                if n_words(text) > MAX_STATE_WORDS:
                    sentences = re.split(r"(?<=[.!?])\s+", text)
                    text = " ".join(fit_paragraphs(sentences, golds + distractors))
                state = {"document": text}
                setting = "wikipedia"
            instructions = qa_wording(rng, norm_space(record["question"]), state, TIME_TEMPLATES, TIME_GENERIC)
            try:
                q, target = choice_from(rng, golds[:1], distractors, instructions)
            except Drop as error:
                stats.dropped[error.reason] += 1
                continue
            stats.count("setting", f"{level}/{setting}")
            yield row(fetched, rid, state, {"answer": q}, {"answer": target}, f"tempreason/{level}/{setting}")


def multihop_state(rng: random.Random, paragraphs: list[tuple[str, str]], keep: list[str]) -> dict[str, Any]:
    texts = [f"{title}: {text}" for title, text in paragraphs]
    texts = fit_paragraphs(texts, keep)
    if rng.random() < 0.5:
        return {"paragraphs": texts}
    return {"context": "\n\n".join(texts)}


COMPARE_YESNO = {
    "true": "Yes.",
    "false": "No.",
}


def convert_2wiki(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Date comparisons (comparison / bridge_comparison questions whose evidence is a date) and compositional
    questions. Yes/no answers become ``noul``; 'which of A or B' answers a choice between the two entities;
    compositional answers a choice with distractors of the same kind from the paragraphs."""
    for record in _parquet_batches(fetched.files, ["_id", "type", "question", "context", "evidences", "answer"]):
        stats.input_rows += 1
        kind = record["type"]
        if kind not in ("comparison", "bridge_comparison", "compositional"):
            stats.dropped[f"type_{kind}"] += 1
            continue
        try:
            context = json.loads(record["context"])
            evidences = json.loads(record["evidences"] or "[]")
        except ValueError:
            stats.dropped["unparseable"] += 1
            continue
        relations = " ".join(str(e[1]) for e in evidences if len(e) == 3)
        if kind != "compositional" and "date" not in relations and "dob" not in relations:
            stats.dropped["comparison_not_date"] += 1
            continue
        paragraphs = [(norm_space(t), norm_space(" ".join(s))) for t, s in context]
        gold = norm_space(record["answer"])
        rid = f"2wiki:{record['_id']}"
        rng = rng_for(rid)
        state = multihop_state(rng, paragraphs, [gold])
        qtext = norm_space(record["question"])
        try:
            if answer_key(gold) in ("yes", "no"):
                q = question("noul", pick(rng, ["{q}", "Answer yes or no: {q}", "Based on the paragraphs, {q}"])
                             .format(q=qtext), dict(COMPARE_YESNO) if rng.random() < 0.3 else None)
                target: Any = 1.0 if answer_key(gold) == "yes" else 0.0
                variant = f"{kind}/yesno"
            elif kind != "compositional":
                subjects = list(dict.fromkeys(norm_space(e[0]) for e in evidences if len(e) == 3))
                pair = re.search(r",\s*(.+?)\s+or\s+(.+?)\s*\??$", qtext)
                named = [pair.group(1), pair.group(2)] if pair else []
                if not any(answer_key(x) == answer_key(gold) for x in named):
                    named = subjects
                other = distinct_distractors([gold], named, rng, 1)
                if not other:
                    raise Drop("no_second_entity")
                instructions = qa_wording(rng, qtext, state, QA_TEMPLATES, QA_GENERIC)
                q, target = choice_from(rng, [gold], other, instructions, letters=0.2)
                variant = f"{kind}/which"
            else:
                text = " ".join(t for _, t in paragraphs)
                bridges = [b for b in (norm_space(e[2]) for e in evidences if len(e) == 3) if kind_of(b) == kind_of(gold)]
                distractors = passage_distractors([gold], text, rng, rng.randint(3, 5), [t for t, _ in paragraphs],
                                                  bridges)
                instructions = qa_wording(rng, qtext, state, QA_TEMPLATES, QA_GENERIC)
                q, target = choice_from(rng, [gold], distractors, instructions)
                variant = "compositional"
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        stats.count("variant", variant)
        yield row(fetched, rid, state, {"answer": q}, {"answer": target}, f"2wikimultihopqa/{variant}")


# --------------------------------------------------------------------------------------------- 4. contracts

CUAD_QUESTION = re.compile(r'related to "(.+?)" that should be reviewed by a lawyer\. Details: (.+)$', re.DOTALL)
CUAD_TEMPLATES = [
    "Does this contract excerpt contain a '{c}' clause? ({d})",
    "Is there a provision about {c} in this part of the contract? Definition: {d}",
    "Would a lawyer reviewing this excerpt flag a '{c}' clause in it? {d}",
    "Clause type: {c} - {d} Does the excerpt include a clause of this type?",
]


def convert_cuad(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Contracts are cut into ~1,800-word chunks. A chunk asks one yes/no question per clause type it contains
    (at least half of an annotated span falls inside the chunk) and as many about clause types with no annotated
    span touching the chunk; one chunk in four with no clause gets two negative questions."""
    contracts: dict[str, dict[str, Any]] = {}
    for record in _parquet_batches(fetched.files, ["title", "context", "question", "answers"]):
        stats.input_rows += 1
        match = CUAD_QUESTION.search(record["question"] or "")
        if not match:
            stats.dropped["question_unparsed"] += 1
            continue
        contract = contracts.setdefault(record["title"], {"context": record["context"], "spans": defaultdict(list)})
        category, details = match.group(1), norm_space(match.group(2))
        contract.setdefault("details", {})[category] = details
        answers = record["answers"] or {}
        for text, start in zip(answers.get("text") or [], answers.get("answer_start") or [], strict=False):
            contract["spans"][category].append((start, start + len(text)))
        contract["spans"].setdefault(category, [])
    for title, contract in sorted(contracts.items()):
        text, spans, details = contract["context"], contract["spans"], contract["details"]
        for n, (start, end) in enumerate(chunk_words(text)):
            positive, touched = [], set()
            for category, ranges in spans.items():
                for a, b in ranges:
                    overlap = max(0, min(b, end) - max(a, start))
                    if overlap > 0:
                        touched.add(category)
                    if overlap >= 0.5 * max(1, b - a):
                        positive.append(category)
                        break
            positive = sorted(set(positive))
            negative = sorted(c for c in spans if c not in touched)
            rid = f"cuad:{title}#{n}"
            rng = rng_for(rid)
            rng.shuffle(negative)
            if positive:
                negative = negative[: len(positive)]
            elif rng.random() < 0.25:
                negative = negative[:2]
            else:
                stats.dropped["chunk_without_clause_skipped"] += 1
                continue
            chunk = text[start:end].strip()
            if n_words(chunk) < 40:
                stats.dropped["chunk_too_short"] += 1
                continue
            template = pick(rng, CUAD_TEMPLATES)
            questions, expected = {}, {}
            for category in sorted(positive + negative):
                key = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")
                questions[key] = question("noul", template.format(c=category, d=details.get(category, "")), None)
                expected[key] = 1.0 if category in positive else 0.0
                stats.count("label", "positive" if category in positive else "negative")
            state = {"contract": title.replace("_", " "), "excerpt": chunk} if rng.random() < 0.5 else chunk
            yield row(fetched, rid, state, questions, expected, "cuad/clause_presence", chunk=n)


def convert_maud(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Merger-agreement excerpts. Single-answer deal points become a choice among the answers seen for that deal
    point; multi-answer deal points (sub-questions) become yes/no per sub-question. The 'abridged' copies of the
    main rows are skipped (near duplicates)."""
    import csv

    path = fetched.files[0]
    with path.open(encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    names: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        if record["subquestion"] == "<NONE>":
            names[record["question"]][(record["label"], record["answer"])] += 1
    options: dict[str, dict[str, str]] = {}
    for q, counter in names.items():
        by_label: dict[str, str] = {}
        for (label, answer), _ in counter.most_common():
            by_label.setdefault(label, answer)
        if len(set(by_label.values())) == len(by_label) >= 2:
            options[q] = by_label
    for n, record in enumerate(records):
        stats.input_rows += 1
        if record["data_type"] == "abridged":
            stats.dropped["abridged_duplicate"] += 1
            continue
        text = (record["text"] or "").strip()
        topic = record["question"].removesuffix("-Answer").strip()
        rid = f"maud:{n}:{record['contract_name']}:{record['id']}"
        rng = rng_for(rid)
        try:
            if record["subquestion"] == "<NONE>":
                if record["question"] not in options:
                    raise Drop("no_answer_inventory")
                by_label = options[record["question"]]
                gold = by_label.get(record["label"])
                if gold is None:
                    raise Drop("label_not_in_inventory")
                instructions = pick(rng, [
                    "Deal point: {t}. Which answer describes this merger agreement excerpt?",
                    "For the deal point '{t}', which option applies to the excerpt?",
                    "Classify the excerpt for the deal point '{t}'.",
                ]).format(t=topic)
                q, target = choice_from(rng, [gold], [a for a in by_label.values() if a != gold], instructions,
                                        letters=0.3)
                variant = "choice"
            else:
                if record["label"] not in ("0", "1"):
                    raise Drop("subquestion_label")
                q = question("noul", pick(rng, [
                    "Deal point: {t}. Does the answer for this excerpt include '{s}'?",
                    "For '{t}', does '{s}' apply to this excerpt?",
                ]).format(t=topic, s=record["subquestion"]), None)
                target = float(record["label"] == "1")
                variant = "subquestion"
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        if n_words(text) > MAX_STATE_WORDS:
            stats.dropped["too_long"] += 1
            continue
        stats.count("variant", variant)
        yield row(fetched, rid, {"category": record["category"], "excerpt": text}, {"answer": q},
                  {"answer": target}, f"maud/{variant}", data_type=record["data_type"])


# --------------------------------------------------------------------------------------------- 5. conversational rules

SHARC_OPTIONS = {
    "Yes": "The answer to the user's question is yes.",
    "No": "The answer to the user's question is no.",
    "Irrelevant": "The rule text does not address the user's question.",
    "Inquire": "More information is needed: ask the user a follow-up question.",
}


def convert_sharc(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    with zipfile.ZipFile(fetched.files[0]) as archive:
        records = json.loads(archive.read("sharc1-official/json/sharc_train.json"))
    for record in records:
        stats.input_rows += 1
        answer = (record.get("answer") or "").strip()
        label = answer if answer in ("Yes", "No", "Irrelevant") else "Inquire"
        rid = f"sharc:{record['utterance_id']}"
        rng = rng_for(rid)
        state: dict[str, Any] = {
            "rule_text": (record.get("snippet") or "").strip(),
            "user_scenario": norm_space(record.get("scenario")),
            "user_question": norm_space(record.get("question")),
            "follow_ups_so_far": [{"question": norm_space(h["follow_up_question"]),
                                   "answer": norm_space(h["follow_up_answer"])} for h in record.get("history") or []],
        }
        if not state["user_scenario"]:
            del state["user_scenario"]
        q = question("choice", pick(rng, [
            "Given the rule text, the user's scenario and the dialog so far, how should the system respond?",
            "Can the user's question be answered from the rules and what the user has said? Choose the response.",
            "Decide the next move: answer yes, answer no, say the rules are irrelevant, or ask a follow-up question.",
        ]), dict(SHARC_OPTIONS))
        stats.count("label", label)
        yield row(fetched, rid, state, {"response": q}, {"response": label}, "sharc/decision",
                  tree_id=record.get("tree_id"))


# --------------------------------------------------------------------------------------------- 6. multi-hop QA


def convert_hotpotqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for record in _parquet_batches(fetched.files, ["id", "question", "answer", "type", "level", "context"]):
        stats.input_rows += 1
        context = record["context"] or {}
        paragraphs = [(norm_space(t), norm_space(" ".join(s))) for t, s in
                      zip(context.get("title") or [], context.get("sentences") or [], strict=False)]
        gold = norm_space(record["answer"])
        qtext = norm_space(record["question"])
        rid = f"hotpotqa:{record['id']}"
        rng = rng_for(rid)
        state = multihop_state(rng, paragraphs, [gold])
        try:
            if answer_key(gold) in ("yes", "no"):
                q = question("noul", pick(rng, ["{q}", "Answer yes or no: {q}", "Based on the paragraphs, {q}"])
                             .format(q=qtext), None)
                target: Any = 1.0 if answer_key(gold) == "yes" else 0.0
                variant = f"{record['type']}/yesno"
            else:
                text = " ".join(t for _, t in paragraphs)
                pair = re.search(r",\s*(.+?)\s+or\s+(.+?)\s*\??$", qtext)
                named = [pair.group(1), pair.group(2)] if record["type"] == "comparison" and pair else []
                if named and any(answer_key(x) == answer_key(gold) for x in named):
                    distractors = distinct_distractors([gold], named, rng, 1)
                    variant = "comparison/which"
                else:
                    distractors = passage_distractors([gold], text, rng, rng.randint(3, 5), [t for t, _ in paragraphs])
                    variant = f"{record['type']}/answer"
                instructions = qa_wording(rng, qtext, state, QA_TEMPLATES, QA_GENERIC)
                q, target = choice_from(rng, [gold], distractors, instructions)
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        stats.count("variant", variant)
        yield row(fetched, rid, state, {"answer": q}, {"answer": target}, f"hotpotqa/{variant}",
                  level=record["level"])


def convert_musique(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Answerable and unanswerable (supporting paragraph removed) questions. Distractors include the intermediate
    (bridge) answers of the decomposition; unanswerable questions keep the original answer as a distractor and
    target ``none``."""
    for record in json_lines(fetched.files[0]):
        stats.input_rows += 1
        gold = norm_space(record["answer"])
        aliases = [norm_space(a) for a in record.get("answer_aliases") or []]
        answerable = bool(record.get("answerable"))
        rid = f"musique:{record['id']}:{'ans' if answerable else 'unans'}"
        rng = rng_for(rid)
        paragraphs = [(norm_space(p["title"]), norm_space(p["paragraph_text"])) for p in record["paragraphs"]]
        state = multihop_state(rng, paragraphs, [gold])
        text = " ".join(t for _, t in paragraphs)
        bridges = [b for b in (norm_space(d.get("answer")) for d in record.get("question_decomposition") or [])
                   if kind_of(b) == kind_of(gold)]
        n = rng.randint(3, 5)
        titles = [t for t, _ in paragraphs]
        distractors = passage_distractors([gold, *aliases], text, rng, n, titles, bridges)
        if not answerable:
            distractors = [gold] + passage_distractors([gold, *aliases], text, rng, n - 1, titles, bridges)
        instructions = qa_wording(rng, norm_space(record["question"]), state, QA_TEMPLATES, QA_GENERIC)
        try:
            q, target = choice_from(rng, [gold], distractors, instructions, none=none_mode(rng, answerable, 0.4))
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        hops = record["id"].split("hop")[0]
        stats.count("answerable", answerable)
        yield row(fetched, rid, state, {"answer": q}, {"answer": target},
                  f"musique/{hops}hop/{'answerable' if answerable else 'unanswerable'}", answerable=answerable)


# --------------------------------------------------------------------------------------------- 7. preference and rating

HELPSTEER_LEVELS = {
    "helpfulness": ("How helpful is the response overall to the prompt?",
                    ["0: not helpful at all", "1: slightly helpful", "2: partially helpful", "3: mostly helpful",
                     "4: perfectly helpful"]),
    "correctness": ("Does the response include all pertinent facts without errors?",
                    ["0: completely incorrect", "1: mostly incorrect", "2: partially correct", "3: mostly correct",
                     "4: perfectly correct and complete"]),
    "coherence": ("How consistent and clear is the expression of the response?",
                  ["0: completely incoherent", "1: mostly incoherent", "2: somewhat clear, with issues",
                   "3: mostly clear and coherent", "4: perfectly clear and coherent"]),
    "complexity": ("How much intellectual depth would it take to write this response?",
                   ["0: basic, anyone could write it", "1: simple, needs basic schooling",
                    "2: intermediate, needs some education", "3: advanced, needs relevant expertise",
                    "4: expert, needs deep domain expertise"]),
    "verbosity": ("How much detail does the response give relative to what the prompt asks for?",
                  ["0: very succinct", "1: rather short", "2: intermediate length", "3: rather long",
                   "4: very verbose"]),
}


def convert_helpsteer2(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """One row per single-turn (prompt, response) with a 0-4 ``score`` question per attribute."""
    for record in json_lines(fetched.files[0]):
        stats.input_rows += 1
        prompt, response = record["prompt"], record["response"]
        if "<extra_id_1>" in prompt:
            stats.dropped["multi_turn"] += 1
            continue
        if n_words(prompt) + n_words(response) > MAX_STATE_WORDS:
            stats.dropped["too_long"] += 1
            continue
        rid = "helpsteer2:" + hashlib.sha1(f"{prompt}\n\n{response}".encode()).hexdigest()[:16]
        rng = rng_for(rid)
        questions, expected = {}, {}
        for attribute, (text, levels) in HELPSTEER_LEVELS.items():
            value = record.get(attribute)
            if not isinstance(value, int) or not 0 <= value <= 4:
                continue
            instructions = text if rng.random() < 0.5 else f"Rate the response's {attribute}. {text}"
            questions[attribute] = question("score", instructions, list(levels))
            expected[attribute] = str(value)
        if not questions:
            stats.dropped["no_ratings"] += 1
            continue
        yield row(fetched, rid, {"prompt": prompt, "response": response}, questions, expected, "helpsteer2/ratings")


STRENGTH = {1: 0.65, 2: 0.8, 3: 0.95}


def preference_probability(scores: list[int]) -> float | None:
    """P(response 1 is better) from HelpSteer3 preference scores (-3..3, negative favours response 1)."""
    values = [0.5 + math.copysign(STRENGTH[abs(s)] - 0.5, -s) if s else 0.5 for s in scores if abs(s) <= 3]
    return sum(values) / len(values) if values else None


def convert_helpsteer3(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Which of two responses is better; soft target from the annotators' preference strengths. Order randomised."""
    for record in json_lines(fetched.files[0]):
        stats.input_rows += 1
        context = record.get("context") or []
        if len(context) != 1 or context[0].get("role") != "user":
            stats.dropped["multi_turn_context"] += 1
            continue
        individual = [p.get("score") for p in record.get("individual_preference") or []
                      if isinstance(p.get("score"), int)]
        p1 = preference_probability(individual or [record["overall_preference"]])
        if p1 is None or p1 == 0.5:
            stats.dropped["no_preference"] += 1
            continue
        prompt, r1, r2 = context[0]["content"], record["response1"], record["response2"]
        if n_words(prompt) + n_words(r1) + n_words(r2) > MAX_STATE_WORDS:
            stats.dropped["too_long"] += 1
            continue
        rid = "helpsteer3:" + hashlib.sha1(f"{prompt}\n\n{r1}\n\n{r2}".encode()).hexdigest()[:16]
        rng = rng_for(rid)
        swap = rng.random() < 0.5
        first, second, p_first = (r2, r1, 1 - p1) if swap else (r1, r2, p1)
        q = question("choice", pick(rng, [
            "Which response is more helpful for the user's prompt?",
            "Which of the two responses better answers the prompt?",
            "Pick the better response.",
        ]), {"response_1": first, "response_2": second})
        stats.count("domain", record.get("domain"))
        yield row(fetched, rid, {"prompt": prompt}, {"preferred": q},
                  {"preferred": {"response_1": round(p_first, 6), "response_2": round(1 - p_first, 6)}},
                  f"helpsteer3/{record.get('domain')}", language=record.get("language"))


def convert_oasst2(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Choice of the best-ranked assistant reply among up to four ranked human-written siblings."""
    columns = ["message_id", "parent_id", "text", "role", "lang", "review_result", "deleted", "rank", "synthetic"]
    messages = {m["message_id"]: m for m in _parquet_batches(fetched.files, columns)}
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in messages.values():
        if m["parent_id"]:
            children[m["parent_id"]].append(m)
    for parent_id in sorted(children):
        stats.input_rows += 1
        replies = [m for m in children[parent_id] if m["role"] == "assistant" and m["rank"] is not None
                   and not m["deleted"] and m["review_result"] and not m["synthetic"]]
        if len(replies) < 2 or not any(m["rank"] == 0 for m in replies):
            stats.dropped["fewer_than_two_ranked_replies"] += 1
            continue
        chain, node = [], messages.get(parent_id)
        while node is not None:
            if node["synthetic"] or node["deleted"]:
                chain = None
                break
            chain.append({"role": "user" if node["role"] == "prompter" else "assistant", "text": node["text"]})
            node = messages.get(node["parent_id"]) if node["parent_id"] else None
        if not chain:
            stats.dropped["bad_thread"] += 1
            continue
        chain.reverse()
        rid = f"oasst2:{parent_id}"
        rng = rng_for(rid)
        best = next(m for m in replies if m["rank"] == 0)
        others = sorted((m for m in replies if m is not best), key=lambda m: m["rank"])[: rng.randint(1, 3)]
        options = [best, *others]
        rng.shuffle(options)
        if sum(n_words(m["text"]) for m in options) + sum(n_words(t["text"]) for t in chain) > MAX_STATE_WORDS:
            stats.dropped["too_long"] += 1
            continue
        keys = [f"reply_{i + 1}" for i in range(len(options))]
        q = question("choice", pick(rng, [
            "Which assistant reply is the best continuation of the conversation?",
            "Human raters ranked these replies. Which one did they rank highest?",
            "Choose the most helpful and appropriate reply to the last user message.",
        ]), {k: m["text"] for k, m in zip(keys, options, strict=True)})
        state: Any = {"conversation": chain} if len(chain) > 1 or rng.random() < 0.5 else chain[0]["text"]
        stats.count("lang", best["lang"])
        yield row(fetched, rid, state, {"best_reply": q}, {"best_reply": keys[options.index(best)]},
                  "oasst2/best_reply", lang=best["lang"], n_options=len(options))


def html_text(value: str) -> str:
    import html

    value = re.sub(r"<pre[^>]*>\s*<code[^>]*>", "\n```\n", value)
    value = re.sub(r"</code>\s*</pre>", "\n```\n", value)
    value = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", value)
    value = re.sub(r"<li[^>]*>", "- ", value)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(value)).strip()


SE_PER_SITE = 1000
SE_TOTAL = 200_000


def convert_stack_exchange(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Per site, the questions with the lowest hash (at most ``SE_PER_SITE``) give one pair each: the top-voted
    answer against a random answer with a lower score. Stops at ``SE_TOTAL`` pairs."""
    import heapq

    by_site: dict[str, list[Path]] = defaultdict(list)
    for path in fetched.files:
        by_site[path.parent.name].append(path)
    made = 0
    for site in sorted(by_site):
        heap: list[tuple[float, int, dict[str, Any]]] = []
        for record in _parquet_batches(sorted(by_site[site]), ["qid", "question", "answers"], batch_size=512):
            stats.input_rows += 1
            answers = record["answers"] or []
            if len(answers) < 2 or len({a["pm_score"] for a in answers}) < 2:
                continue
            key = -unit("se", site, record["qid"])
            item = (key, record["qid"], record)
            if len(heap) < SE_PER_SITE:
                heapq.heappush(heap, item)
            elif key > heap[0][0]:
                heapq.heapreplace(heap, item)
        for _, qid, record in sorted(heap, key=lambda x: x[1]):
            rid = f"se:{site}:{qid}"
            rng = rng_for(rid)
            answers = sorted(record["answers"], key=lambda a: (-a["pm_score"], a["answer_id"]))
            best = answers[0]
            worse = [a for a in answers if a["pm_score"] < best["pm_score"]]
            other = worse[rng.randrange(len(worse))]
            q_text, a_text, b_text = (html_text(record["question"]), html_text(best["text"]),
                                      html_text(other["text"]))
            if n_words(q_text) + n_words(a_text) + n_words(b_text) > MAX_STATE_WORDS // 2:
                stats.dropped["too_long"] += 1
                continue
            first, second = (best, other) if rng.random() < 0.5 else (other, best)
            texts = {id(best): a_text, id(other): b_text}
            q = question("choice", pick(rng, [
                "Which answer did the community vote higher?",
                "Which of the two answers is better for this question?",
                "Pick the more useful answer to the question.",
            ]), {"answer_1": texts[id(first)], "answer_2": texts[id(second)]})
            stats.count("site", site)
            yield row(fetched, rid, {"site": site, "question": q_text}, {"better_answer": q},
                      {"better_answer": "answer_1" if first is best else "answer_2"}, "stack-exchange/pair",
                      score_gap=best["pm_score"] - other["pm_score"])
            made += 1
            if made >= SE_TOTAL:
                return


# --------------------------------------------------------------------------------------------- 8. verification

FEVER_OPTIONS = {
    "SUPPORTS": "The evidence supports the claim.",
    "REFUTES": "The evidence refutes the claim.",
    "NOT ENOUGH INFO": "The evidence is not enough to decide.",
}
PTB = {"-LRB-": "(", "-RRB-": ")", "-LSB-": "[", "-RSB-": "]", "-LCB-": "{", "-RCB-": "}", "--": "–",
       "``": '"', "''": '"'}


def detok(text: str) -> str:
    for a, b in PTB.items():
        text = text.replace(a, b)
    text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return norm_space(text)


def convert_fever(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for record in json_lines(fetched.files[0]):
        stats.input_rows += 1
        label = record.get("label")
        evidence = [f"{detok(str(e[0]).replace('_', ' '))}: {detok(str(e[2]))}" for e in record.get("evidence") or []
                    if len(e) >= 3 and str(e[2]).strip()]
        if label not in FEVER_OPTIONS or not evidence:
            stats.dropped["bad_fields"] += 1
            continue
        rid = f"fever:{record['id']}"
        rng = rng_for(rid)
        evidence = list(dict.fromkeys(evidence))
        if rng.random() < 0.3:
            q = question("noul", pick(rng, ["Does the evidence support the claim?",
                                            "Is the claim supported by the evidence sentences?"]), {
                "true": "The evidence supports the claim.",
                "false": "The evidence refutes the claim or is not enough to decide."})
            target: Any = 1.0 if label == "SUPPORTS" else 0.0
            variant = "noul"
        else:
            q = question("choice", pick(rng, [
                "Does the evidence support or refute the claim, or is it not enough to tell?",
                "What does the evidence say about the claim?",
                "Verify the claim against the evidence.",
            ]), dict(FEVER_OPTIONS))
            target = label
            variant = "choice"
        stats.count("label", label)
        yield row(fetched, rid, {"claim": norm_space(record["claim"]), "evidence": evidence}, {"verdict": q},
                  {"verdict": target}, f"fever/{variant}", label=label)


def convert_tabfact(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    tables = {}
    for record in _parquet_batches(ctx.fetched("tabfact-tables").files, ["table_id", "table_text", "table_caption"]):
        tables.setdefault(record["table_id"], (record["table_text"], record["table_caption"]))
    train = set(load_json(next(p for p in fetched.files if p.name == "train_id.json")))
    for path in sorted(p for p in fetched.files if p.name.endswith("_training_all.json")):
        for table_id, (statements, labels, caption) in sorted(load_json(path).items()):
            if table_id not in train or table_id not in tables:
                stats.input_rows += len(statements)
                stats.dropped["table_not_in_train" if table_id not in train else "table_missing"] += len(statements)
                continue
            rows = [line.split("#") for line in tables[table_id][0].strip().split("\n")]
            for n, (statement, label) in enumerate(zip(statements, labels, strict=True)):
                stats.input_rows += 1
                rid = f"tabfact:{path.name[:2]}:{table_id}:{n}"
                rng = rng_for(rid)
                q = question("noul", pick(rng, [
                    "Is the statement entailed by the table?",
                    "According to the table, is the statement true?",
                    "Does the table support the statement?",
                ]), {"true": "The table entails the statement.", "false": "The table refutes the statement."}
                    if rng.random() < 0.3 else None)
                state = {"caption": caption, "table": table_text(rows, rng), "statement": norm_space(statement)}
                stats.count("label", label)
                yield row(fetched, rid, state, {"entailed": q}, {"entailed": float(label == 1)}, "tabfact/entailed")


# --------------------------------------------------------------------------------------------- 9. reading comprehension


def question_kind(qtext: str) -> str:
    q = qtext.lower()
    if re.search(r"\bhow (many|much|long|old|far|tall|big|large)\b|\bwhat (percent|percentage|number)\b", q):
        return "1"
    if re.search(r"\bwhat year\b|\bwhich year\b|\bin what century\b", q):
        return "1999"
    if re.search(r"\bwhen\b|\bwhat date\b|\bwhich date\b", q):
        return "1 January 1999"
    return "Entity Name"


def convert_squad2(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Choice over the gold span and same-kind spans from the passage; unanswerable questions list same-kind spans
    and target ``none`` (the none option also appears on 30% of answerable questions)."""
    for record in _parquet_batches(fetched.files, ["id", "title", "context", "question", "answers"]):
        stats.input_rows += 1
        golds = list(dict.fromkeys(t.strip() for t in (record["answers"] or {}).get("text") or [] if t.strip()))
        context, qtext = record["context"].strip(), norm_space(record["question"])
        rid = f"squad2:{record['id']}"
        rng = rng_for(rid)
        if golds:
            distractors = passage_distractors(golds, context, rng, rng.randint(3, 5))
        else:
            # Unanswerable: no gold to imitate; candidates of the kind the question asks for, else entities.
            pool = typed_candidates(question_kind(qtext), context)
            if len(pool) < 3:
                pool += typed_candidates("Entity Name", context)
            distractors = distinct_distractors([], pool, rng, rng.randint(3, 5))
        state: dict[str, Any] = {"title": record["title"].replace("_", " "), "passage": context}
        instructions = qa_wording(rng, qtext, state, QA_TEMPLATES, QA_GENERIC)
        try:
            q, target = choice_from(rng, golds[:1], distractors, instructions, none=none_mode(rng, bool(golds)))
        except Drop as error:
            stats.dropped[error.reason] += 1
            continue
        stats.count("answerable", bool(golds))
        yield row(fetched, rid, state, {"answer": q}, {"answer": target},
                  f"squad2/{'answerable' if golds else 'unanswerable'}")


CONDAQA = {"YES": "yes", "NO": "no", "DON'T KNOW": "dont_know", "DONT KNOW": "dont_know"}


def convert_condaqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for record in json_lines(fetched.files[0]):
        stats.input_rows += 1
        label = CONDAQA.get(str(record.get("label")).strip().upper())
        if label is None:
            stats.dropped[f"label_{record.get('label')}"] += 1
            continue
        rid = f"condaqa:{record['PassageID']}:{record['PassageEditID']}:{record['QuestionID']}:{record['SampleID']}"
        rng = rng_for(rid)
        q = question("choice", pick(rng, [
            "{q}", "Based on the passage, {q}", "Answer from the passage (yes, no, or cannot tell): {q}",
        ]).format(q=norm_space(record["sentence2"])), {
            "yes": "Yes.", "no": "No.", "dont_know": "Cannot be determined from the passage."})
        stats.count("label", label)
        yield row(fetched, rid, {"passage": norm_space(record["sentence1"])}, {"answer": q}, {"answer": label},
                  "condaqa/yes_no_dontknow")


TYDI_MAX_PASSAGE_WORDS = 400
TYDI_MAX_PASSAGE_CHARS = 2500  # word counts do not bound Japanese, Thai or Chinese text
#: Share of no-answer questions kept (about half of TyDi QA train has no answer passage).
TYDI_NULL_KEEP = 0.4


def convert_tydiqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Primary task: choose the passage that answers the question among the gold and up to five other candidate
    passages of the article (``none`` when no passage answers; ``TYDI_NULL_KEEP`` of those are kept); YES/NO answers
    also give a yes/no row over the gold passage. Every language."""
    columns = ["passage_answer_candidates", "question_text", "document_title", "language", "annotations",
               "document_plaintext", "document_url"]
    for record in _parquet_batches(fetched.files, columns, batch_size=256):
        stats.input_rows += 1
        data = record["document_plaintext"].encode("utf-8")
        cand = record["passage_answer_candidates"] or {}
        passages = [norm_space(data[a:b].decode("utf-8", "replace"))
                    for a, b in zip(cand.get("plaintext_start_byte") or [], cand.get("plaintext_end_byte") or [],
                                    strict=False)]
        ann = record["annotations"] or {}
        gold_idx = (ann.get("passage_answer_candidate_index") or [-1])[0]
        yes_no = (ann.get("yes_no_answer") or ["NONE"])[0]
        qtext, lang = norm_space(record["question_text"]), record["language"]
        rid = "tydiqa:" + hashlib.sha1(f"{record['document_url']}\n{qtext}".encode()).hexdigest()[:16]
        rng = rng_for(rid)
        if gold_idx < 0 and unit("tydiqa-null", rid) >= TYDI_NULL_KEEP:
            stats.dropped["null_subsampled"] += 1
            continue
        usable = [i for i, p in enumerate(passages) if 5 <= n_words(p) <= TYDI_MAX_PASSAGE_WORDS and
                  20 <= len(p) <= TYDI_MAX_PASSAGE_CHARS and i != gold_idx]
        if gold_idx >= 0 and not (1 <= n_words(passages[gold_idx]) <= TYDI_MAX_PASSAGE_WORDS * 2 and
                                  len(passages[gold_idx]) <= TYDI_MAX_PASSAGE_CHARS * 2):
            stats.dropped["gold_passage_too_long"] += 1
            continue
        near = sorted(usable, key=lambda i: (abs(i - gold_idx) if gold_idx >= 0 else i, i))[:8]
        rng.shuffle(near)
        others = near[: rng.randint(3, 5)]
        if len(others) < 2:
            stats.dropped["too_few_passages"] += 1
            continue
        options = ([gold_idx] if gold_idx >= 0 else []) + others
        rng.shuffle(options)
        keys = [f"passage_{n + 1}" for n in range(len(options))]
        criteria: dict[str, Any] = {k: passages[i] for k, i in zip(keys, options, strict=True)}
        answerable = gold_idx >= 0
        if not answerable or rng.random() < 0.3:
            criteria[NONE_KEY] = NONE_TEXT
        q = question("choice", pick(rng, [
            "Which passage of the article answers the question: {q}",
            "Question: {q} Which passage contains the answer?",
            "{q} (Choose the passage that answers this question.)",
        ]).format(q=qtext), criteria)
        target = keys[options.index(gold_idx)] if answerable else NONE_KEY
        stats.count("language", lang)
        stats.count("answerable", answerable)
        yield row(fetched, rid, {"article_title": norm_space(record["document_title"])}, {"passage": q},
                  {"passage": target}, f"tydiqa/passage/{lang}", language=lang, answerable=answerable)
        if yes_no in ("YES", "NO"):
            q2 = question("noul", pick(rng, ["{q}", "Based on the passage: {q}"]).format(q=qtext), None)
            stats.count("yes_no", yes_no)
            yield row(fetched, rid + ":yesno", {"article_title": norm_space(record["document_title"]),
                                                "passage": passages[gold_idx]}, {"answer": q2},
                      {"answer": float(yes_no == "YES")}, f"tydiqa/yesno/{lang}", language=lang)


# --------------------------------------------------------------------------------------------- 10. safety and toxicity


def convert_aegis2(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """Prompt-only rows: is the user prompt unsafe (+ hazard category). Rows with a human-labelled response: is the
    response unsafe (+ hazard category of the exchange). LLM-jury response labels are not used (the prompt label,
    always human, is still used without the response)."""
    records = load_json(fetched.files[0])
    categories = sorted({c.strip() for r in records for c in (r.get("violated_categories") or "").split(",")
                         if c.strip()})
    for record in records:
        stats.input_rows += 1
        prompt = (record.get("prompt") or "").strip()
        if not prompt or prompt == "REDACTED":
            stats.dropped["redacted"] += 1
            continue
        if re.search(r"(^|\n)\s*(assistant|Assistant)\s*:", prompt):
            stats.dropped["multi_turn_prompt"] += 1
            continue
        if record.get("prompt_label_source") != "human":
            stats.dropped["prompt_label_not_human"] += 1
            continue
        response = (record.get("response") or "").strip()
        human_response = bool(response) and record.get("response_label_source") == "human"
        if response and not human_response:
            stats.count("llm_jury_response_dropped", 1)
        rid = f"aegis2:{record['id']}"
        rng = rng_for(rid)
        violated = [c.strip() for c in (record.get("violated_categories") or "").split(",") if c.strip()]
        if human_response:
            label = record.get("response_label")
            state: Any = {"user": prompt, "assistant": response}
            subject = "the assistant's response"
            category_scope = human_response
        else:
            label = record.get("prompt_label")
            state = prompt if rng.random() < 0.5 else {"user": prompt}
            subject = "the user's message"
            category_scope = not response
        if label not in ("safe", "unsafe"):
            stats.dropped["no_label"] += 1
            continue
        questions = {"unsafe": question("noul", pick(rng, [
            f"Is {subject} unsafe under a content-safety policy?",
            f"Does {subject} violate content-safety guidelines?",
            f"Should {subject} be flagged as unsafe?",
        ]), None)}
        expected: dict[str, Any] = {"unsafe": float(label == "unsafe")}
        if label == "unsafe" and violated and category_scope and all(c in categories for c in violated):
            questions["category"] = question("choice", pick(rng, [
                "Which hazard category does the content fall under?",
                "Classify the safety violation into a hazard category.",
            ]), {c: None for c in categories})
            expected["category"] = violated[0] if len(violated) == 1 else {
                c: round(1 / len(violated), 6) for c in violated}
        stats.count("label", f"{'response' if human_response else 'prompt'}:{label}")
        yield row(fetched, rid, state, questions, expected,
                  f"aegis2/{'response' if human_response else 'prompt'}")


CIVIL_TOTAL = 150_000


def convert_civil_comments(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """A deterministic sample (hash of the text): comments rated toxic by at least 20% of raters are sampled at a
    higher rate. The target is the fraction of raters who found the comment toxic."""
    made = 0
    for record in _parquet_batches(fetched.files, ["text", "toxicity", "insult", "threat", "identity_attack",
                                                   "obscene"]):
        stats.input_rows += 1
        text = (record["text"] or "").strip()
        tox = record["toxicity"]
        if not text or tox is None or not 0 <= tox <= 1:
            stats.dropped["bad_fields"] += 1
            continue
        h = hashlib.sha1(text.encode()).hexdigest()[:16]
        rate = 0.25 if tox >= 0.2 else 0.06
        if unit("civil", h) >= rate:
            continue
        rng = rng_for("civil", h)
        questions = {"toxic": question("noul", pick(rng, [
            "Is this comment toxic (rude, disrespectful or unreasonable enough to make someone leave a discussion)?",
            "Would a typical reader find this comment toxic?",
            "Is the comment toxic?",
        ]), None)}
        expected: dict[str, Any] = {"toxic": round(float(tox), 6)}
        if rng.random() < 0.3:
            for attr, text_q in (("insult", "Is the comment insulting?"), ("threat", "Does the comment contain a threat?"),
                                 ("identity_attack", "Does the comment attack someone for their identity?"),
                                 ("obscene", "Is the comment obscene?")):
                if record[attr] is not None and 0 <= record[attr] <= 1:
                    questions[attr] = question("noul", text_q, None)
                    expected[attr] = round(float(record[attr]), 6)
        stats.count("toxic_ge_0.5", tox >= 0.5)
        yield row(fetched, f"civil:{h}", text, questions, expected, "civil_comments/toxicity")
        made += 1
        if made >= CIVIL_TOTAL:
            return


# --------------------------------------------------------------------------------------------- optional sources


def convert_medmcqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for record in _parquet_batches(fetched.files, ["id", "question", "opa", "opb", "opc", "opd", "cop",
                                                   "choice_type", "subject_name"]):
        stats.input_rows += 1
        options = [norm_space(record[k]) for k in ("opa", "opb", "opc", "opd")]
        if record["choice_type"] != "single" or record["cop"] not in range(4) or not all(options) \
                or len({answer_key(o) for o in options}) != 4:
            stats.dropped["not_single_or_bad_options"] += 1
            continue
        rid = f"medmcqa:{record['id']}"
        rng = rng_for(rid)
        q = question("choice", pick(rng, ["Which option is correct?", "Choose the correct answer.",
                                          "Answer the medical exam question."]),
                     {k: o for k, o in zip("ABCD", options, strict=True)})
        stats.count("subject", record["subject_name"])
        yield row(fetched, rid, norm_space(record["question"]), {"answer": q}, {"answer": "ABCD"[record["cop"]]},
                  "medmcqa", subject=record["subject_name"])


UNFAIR_TOS = ["Limitation of liability", "Unilateral termination", "Unilateral change", "Content removal",
              "Contract by using", "Choice of law", "Jurisdiction", "Arbitration"]


def convert_lexglue(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    from gdecide.data.extra_sources import class_names

    for path in sorted(fetched.files):
        subset = path.parent.name
        if subset == "ledgar":
            names = class_names(path)["label"]
            for n, record in enumerate(_parquet_batches([path], ["text", "label"])):
                stats.input_rows += 1
                rid = f"ledgar:{n}"
                rng = rng_for(rid)
                q = question("choice", pick(rng, ["Which heading best fits this contract provision?",
                                                  "Classify the contract provision by its type."]),
                             {name: None for name in names})
                yield row(fetched, rid, norm_space(record["text"]), {"type": q}, {"type": names[record["label"]]},
                          "lexglue/ledgar", source=f"{fetched.source.repo}/ledgar")
        elif subset == "unfair_tos":
            for n, record in enumerate(_parquet_batches([path], ["text", "labels"])):
                stats.input_rows += 1
                rid = f"unfair_tos:{n}"
                rng = rng_for(rid)
                labels = set(record["labels"] or [])
                template = pick(rng, ["Is this terms-of-service sentence a potentially unfair '{c}' clause?",
                                      "Does the sentence contain an unfair term of type: {c}?"])
                questions = {re.sub(r"\W+", "_", c.lower()): question("noul", template.format(c=c), None)
                             for c in UNFAIR_TOS}
                expected = {re.sub(r"\W+", "_", c.lower()): float(i in labels) for i, c in enumerate(UNFAIR_TOS)}
                yield row(fetched, rid, norm_space(record["text"]), questions, expected, "lexglue/unfair_tos",
                          source=f"{fetched.source.repo}/unfair_tos")
        elif subset == "case_hold":
            for n, record in enumerate(_parquet_batches([path], ["context", "endings", "label"])):
                stats.input_rows += 1
                rid = f"case_hold:{n}"
                rng = rng_for(rid)
                endings = [norm_space(e) for e in record["endings"] or []]
                if len(endings) != 5 or len(set(endings)) != 5 or record["label"] not in range(5):
                    stats.dropped["bad_endings"] += 1
                    continue
                q = question("choice", pick(rng, [
                    "Which holding statement belongs at the <HOLDING> mask in the citing text?",
                    "Choose the holding that the cited case stands for.",
                ]), {k: e for k, e in zip("ABCDE", endings, strict=True)})
                yield row(fetched, rid, norm_space(record["context"]), {"holding": q},
                          {"holding": "ABCDE"[record["label"]]}, "lexglue/case_hold",
                          source=f"{fetched.source.repo}/case_hold")


def convert_multiwoz(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    """One user turn per dialogue: the active intent of every service the dialogue uses (choice among the service's
    intents and NONE)."""
    schema = load_json(next(p for p in fetched.files if p.name == "schema.json"))
    intents = {s["service_name"]: {i["name"]: i["description"] for i in s["intents"]} for s in schema}
    for path in sorted(p for p in fetched.files if p.name.startswith("dialogues_")):
        for dialogue in load_json(path):
            stats.input_rows += 1
            turns = dialogue["turns"]
            rid = f"multiwoz22:{dialogue['dialogue_id']}"
            rng = rng_for(rid)
            user_turns = [i for i, t in enumerate(turns) if t["speaker"] == "USER"]
            k = user_turns[rng.randrange(len(user_turns))] if user_turns else None
            if k is None:
                stats.dropped["no_user_turn"] += 1
                continue
            questions, expected = {}, {}
            in_dialogue = set(dialogue.get("services") or [])
            for frame in turns[k].get("frames") or []:
                service = frame.get("service")
                active = (frame.get("state") or {}).get("active_intent")
                if service not in intents or service not in in_dialogue or not active:
                    continue
                options = {**intents[service], "NONE": "The user has no active request in this domain."}
                if active not in options:
                    continue
                questions[service] = question("choice", pick(rng, [
                    "What is the user's active intent in the {s} domain at their latest turn?",
                    "Which {s} intent is the user pursuing right now?",
                ]).format(s=service), options)
                expected[service] = active
            if not questions:
                stats.dropped["no_frames"] += 1
                continue
            history = [f"{'User' if t['speaker'] == 'USER' else 'System'}: {norm_space(t['utterance'])}"
                       for t in turns[: k + 1]]
            stats.count("services", len(questions))
            yield row(fetched, rid, {"dialogue": history}, questions, expected, "multiwoz22/active_intent", turn=k)


def convert_commonsenseqa(fetched: Fetched, stats: Stats, ctx: Context) -> Iterator[dict[str, Any]]:
    for record in _parquet_batches(fetched.files, ["id", "question", "choices", "answerKey"]):
        stats.input_rows += 1
        choices = record["choices"] or {}
        options = dict(zip(choices.get("label") or [], [norm_space(t) for t in choices.get("text") or []],
                           strict=False))
        if record["answerKey"] not in options:
            stats.dropped["bad_answer_key"] += 1
            continue
        rng = rng_for(f"csqa:{record['id']}")
        q = question("choice", pick(rng, ["Which option is the most sensible answer?", "Choose the best answer.",
                                          "Use common sense to pick the answer."]), options)
        yield row(fetched, f"csqa:{record['id']}", norm_space(record["question"]), {"answer": q},
                  {"answer": record["answerKey"]}, "commonsenseqa")


# --------------------------------------------------------------------------------------------- registry and main

Converter = Callable[[Fetched, Stats, Context], Iterator[dict[str, Any]]]

CONVERTERS: dict[str, Converter] = {
    "tatqa": convert_tatqa,
    "finqa": convert_finqa,
    "convfinqa": convert_convfinqa,
    "drop": convert_drop,
    "timeqa": convert_timeqa,
    "tempreason": convert_tempreason,
    "2wikimultihopqa": convert_2wiki,
    "cuad": convert_cuad,
    "maud": convert_maud,
    "sharc": convert_sharc,
    "hotpotqa": convert_hotpotqa,
    "musique": convert_musique,
    "helpsteer2": convert_helpsteer2,
    "helpsteer3": convert_helpsteer3,
    "oasst2": convert_oasst2,
    "stack-exchange-prefs": convert_stack_exchange,
    "fever": convert_fever,
    "tabfact": convert_tabfact,
    "squad2": convert_squad2,
    "condaqa": convert_condaqa,
    "tydiqa": convert_tydiqa,
    "aegis2": convert_aegis2,
    "civil-comments": convert_civil_comments,
    "medmcqa": convert_medmcqa,
    "lexglue": convert_lexglue,
    "multiwoz22": convert_multiwoz,
    "commonsenseqa": convert_commonsenseqa,
}
assert set(CONVERTERS) == set(SOURCES), set(CONVERTERS) ^ set(SOURCES)


def state_words(state: Any) -> int:
    if isinstance(state, str):
        return n_words(state)
    return n_words(json.dumps(state, ensure_ascii=False))


def accept(row_: dict[str, Any], stats: Stats, seen: set[str]) -> bool:
    """``validate_row`` plus the broad-mix limits (state size, unique ids)."""
    if reason := validate_row(row_):
        stats.dropped[f"invalid:{reason}"] += 1
        return False
    if state_words(row_["state"]) > MAX_STATE_WORDS * 1.1:
        stats.dropped["state_too_long"] += 1
        return False
    if char_length(row_) > MAX_ROW_CHARS:
        stats.dropped["row_too_long_chars"] += 1
        return False
    if row_["id"] in seen:
        stats.dropped["duplicate_id"] += 1
        return False
    seen.add(row_["id"])
    return True


def run_source(slug: str, ctx: Context, limit: int | None) -> dict[str, Any]:
    fetched = ctx.fetched(slug)
    stats = Stats()
    target = ctx.out / f"{slug}.jsonl.gz"
    part = target.with_name(target.name + ".part")
    seen: set[str] = set()
    started = time.time()
    with gzip.open(part, "wt", encoding="utf-8", compresslevel=6) as handle:
        for item in CONVERTERS[slug](fetched, stats, ctx):
            if not accept(item, stats, seen):
                continue
            stats.add(item)
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            if limit and stats.rows >= limit:
                break
            if stats.rows % 100_000 == 0:
                print(f"  {slug}: {stats.rows} rows ({stats.input_rows} read)", file=sys.stderr)
    part.rename(target)
    source = fetched.source
    host = "github" if isinstance(source, GitSource) else "url" if isinstance(source, UrlSource) else "huggingface"
    return {
        "dataset": source.repo,
        "host": host,
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
    manifest_path = args.out / "broad-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("sources", {})
    manifest["skipped"] = SKIPPED
    ctx = Context(args.out, args.latest)
    for slug in args.sources:
        print(f"== {slug}", file=sys.stderr)
        manifest["sources"][slug] = run_source(slug, ctx, args.limit)
        manifest["generated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest["converter"] = "research/gradiated-decide/gdecide/data/broad_sources.py"
        tmp = manifest_path.with_name(manifest_path.name + ".part")
        tmp.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
        tmp.rename(manifest_path)
        summary = manifest["sources"][slug]
        print(f"  {slug}: {summary['rows']} rows, dropped {summary['dropped_rows']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
