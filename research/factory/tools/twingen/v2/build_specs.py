"""Build conversation specs, clusters and the v2 target list for a separate data root (stdlib).

Runs the v1 spec extractor and clusterer (../../twins/extract.py, cluster.py; unchanged) with their input traces
and output directory redirected to PATHS (TWIN_V2_TRACES, TWIN_V2_ROOT), then writes PATHS.TARGETS for the
requested splits. Refuses to overwrite the original specs/targets (TWIN_V2_ROOT must not be the default root).

    TWIN_V2_TRACES=DIR TWIN_V2_ROOT=WORK python3 -I build_specs.py [--splits test_v2,dev]
Prints aggregates only.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths as PATHS  # noqa: E402

TWINS_CODE = "/opt/posthog-sft/env-research/twins"
sys.path.insert(0, TWINS_CODE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="test_v2,dev")
    a = ap.parse_args()
    if PATHS.ROOT == "/opt/posthog-sft/env-research":
        raise SystemExit("set TWIN_V2_ROOT to a new work directory (the default root holds the current specs)")
    files = PATHS.trace_files()
    if not files:
        raise SystemExit("no train/dev/test_v2.jsonl found under TWIN_V2_TRACES")
    os.makedirs(PATHS.TWINS, exist_ok=True)
    os.makedirs(PATHS.TWINGEN_DATA, exist_ok=True)
    import twinlib
    twinlib.FILES = files
    import extract
    extract.OUT, extract.SPECS = PATHS.TWINS, PATHS.SPECS
    extract.main()
    import cluster
    cluster.OUT, cluster.CL = PATHS.TWINS, os.path.join(PATHS.TWINS, "clusters")
    cluster.main()
    n = 0
    with open(PATHS.TARGETS, "w") as fh:
        for line in open(os.path.join(PATHS.TWINS, "index.jsonl")):
            r = json.loads(line)
            spec = json.load(open(os.path.join(PATHS.TWINS, r["spec_file"])))
            if spec.get("split") in a.splits.split(","):
                fh.write(json.dumps({"id": spec["conversation_id"], "spec": os.path.join(PATHS.TWINS, r["spec_file"]),
                                     "reason": spec["split"]}) + "\n")
                n += 1
    print(json.dumps({"traces": sorted(files), "targets": n}))


if __name__ == "__main__":
    main()
