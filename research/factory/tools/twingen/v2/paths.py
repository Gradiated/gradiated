"""All v2 data locations in one place. Environment variables select a separate build; defaults are the current one.

- TWIN_V2_TRACES: directory with the anonymized traces (searched recursively for train.jsonl, dev.jsonl and
  test_v2.jsonl, e.g. a re-anonymized copy of root_agent/data_all + eval/data). Default: the original files.
- TWIN_V2_ROOT: data root for specs, facts, projects, overrides (default /opt/posthog-sft/env-research).
- TWIN_V2_TAG: suffix that keeps a build's teams, task files and replay apart (teams_v2_<tag>.jsonl,
  runner/tasks/v2_<tag>/, org prefix "Twin2<tag> "). Default "" (the current v2 build).
"""

from __future__ import annotations

import os

ROOT = os.environ.get("TWIN_V2_ROOT", "/opt/posthog-sft/env-research")
TAG = os.environ.get("TWIN_V2_TAG", "")
SFX = f"_{TAG}" if TAG else ""
TWINS = f"{ROOT}/twins"
TWINGEN_DATA = f"{ROOT}/twingen"
SPECS = f"{TWINS}/specs"
CLUSTERS = f"{TWINS}/clusters/clusters.jsonl"
FACTS = f"{TWINS}/facts_v2"
QFACTS = f"{TWINS}/qfacts_v2"
XINDEX = f"{TWINS}/xindex_v2.json"
OVERRIDES = f"{TWINS}/overrides_v2"
PROJECTS = f"{TWINGEN_DATA}/projects_v2"
CALIB = f"{TWINGEN_DATA}/calib_v2"
TARGETS = f"{TWINGEN_DATA}/targets.jsonl"
ENV = "/opt/posthog-env"
LOADER = f"{ENV}/loader"
TEAMS = f"{LOADER}/teams_v2{SFX}.jsonl"
STATE = f"{LOADER}/state_v2{SFX}"
ORPHANS = f"{LOADER}/orphans_v2{SFX}.jsonl"
PREFIX = f"Twin2{TAG} "
TASKS_DIR = f"{ENV}/runner/tasks/v2{SFX}"
REPLAY_DIR = os.environ.get("TWIN_V2_REPLAY_DIR", f"/tmp/fid2{SFX}")
V1_REPLAY_DIR = "/tmp/fid"

DEFAULT_TRACES = {
    "train": "/opt/posthog-sft/root_agent/data_all/train.jsonl",
    "dev": "/opt/posthog-sft/root_agent/data_all/dev.jsonl",
    "test_v2": "/opt/posthog-sft/eval/data/test_v2.jsonl",
}


def trace_files() -> dict[str, str]:
    d = os.environ.get("TWIN_V2_TRACES")
    if not d:
        return dict(DEFAULT_TRACES)
    out = {}
    for base, _dirs, files in os.walk(d):
        for split in ("train", "dev", "test_v2"):
            if f"{split}.jsonl" in files and split not in out:
                out[split] = os.path.join(base, f"{split}.jsonl")
    return out
