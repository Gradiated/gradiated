"""Predict cycle changes from pinned, independent per-position attention counts."""

from itertools import accumulate
import json
from pathlib import Path
import tarfile

ROOT = Path(".agents/runtime/hardware/inference/outputs")
CACHE_RUN = "attention-cache-pipeline-rtl-20261117T105443Z"
PROFILE_RUN = "attention-profile-rtl-20261117T104256Z"


def read_pin(repo, run, path):
    record = json.loads((repo / "hardware/research/inference/results" / run / "run.json").read_bytes())
    artifact, = [row for row in record["artifacts"] if row["path"] == str(ROOT / run / path)]
    return artifact["sha256"]


def predict(repo, checked, spec):
    cache = repo / ROOT / CACHE_RUN
    profile = repo / ROOT / PROFILE_RUN
    control = json.loads(checked(cache / "model-results.json", spec["control_replay_sha256"]))["candidate"]
    profile_archive = profile / "replay.tar.gz"
    checked(profile_archive, spec["profile_archive_sha256"])
    results = {}
    with tarfile.open(profile_archive) as archive:
        for case, old in control.items():
            rows = archive.extractfile(f"replay/cases/{case}/attention-profile.txt").read().decode().splitlines()
            full_exps = []
            for position, row in enumerate(rows, 1):
                index, length, *counts = map(int, row.split())
                cutoff = counts[22]
                completed_exp = 2 * length - cutoff
                if index != position or length != position or counts[23] != 96 * completed_exp:
                    raise ValueError(f"Source profile did not reconcile: {case}/{position}")
                full_exps.append(completed_exp)
            if len(full_exps) != old["done"]["positions"]:
                raise ValueError(f"Source profile geometry differs: {case}")
            savings = [0, *accumulate(73 * n for n in full_exps)]
            result = {}
            for name in ("prefix", "done"):
                row = old[name]
                prefix_positions = old["prefix"]["positions"]
                total = savings[row["positions"]]
                last_position = prefix_positions + old["outputs"] - 1
                first = row["first"] - savings[prefix_positions] if row["first_valid"] else 0
                last = row["last"] - savings[last_position] if row["first_valid"] else 0
                result[name] = dict(
                    cycles=row["cycles"]-total, first=first, last=last,
                    done=row["done"]-total if name=="done" else 0, saved_attention=total,
                )
            results[case] = dict(**result, full_exponentials=full_exps)
    return dict(cases=results, control=CACHE_RUN, profile=PROFILE_RUN, divider_steps_saved=73)
