"""One batched ALTER DELETE per ClickHouse table for the rows of dead v2 team ids (orphans_v2.jsonl). Run when idle:
no rollouts, no loads (mutations are serialized server-wide). Prints counts only.

    cd /opt/posthog-env/posthog && .venv/bin/python ../loader/cleanup_orphans_v2.py [--dry-run]
"""
import argparse, json, os, sys

sys.path.insert(0, "/opt/posthog-env/loader")
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import paths as PATHS  # noqa: E402
from loader_common import ch, LOADER  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--batch", type=int, default=55, help="team ids per mutation (modest batches; mutations are serialized)")
ap.add_argument("--pause-s", type=float, default=30)
a = ap.parse_args()
p = PATHS.ORPHANS
ids = sorted({int(json.loads(l)["team_id"]) for l in open(p)} if os.path.exists(p) else set())
live = set()
import glob
for f in glob.glob(f"{LOADER}/teams*.jsonl"):
    for l in open(f):
        r = json.loads(l)
        (live.discard if r.get("removed") else live.add)(int(r["team_id"]))
ids = [i for i in ids if i not in live and i not in (1, 2)]
print("orphan teams", len(ids))
if not ids or a.dry_run:
    sys.exit(0)
tables = ch("SELECT t.name FROM system.tables t WHERE t.database = currentDatabase() AND t.engine LIKE '%MergeTree%' "
            "AND t.total_rows > 0 AND t.name IN (SELECT table FROM system.columns WHERE database = currentDatabase() "
            "AND name = 'team_id')").split()
import time
for b in range(0, len(ids), a.batch):
    lst = ",".join(map(str, ids[b:b + a.batch]))
    for t in tables:
        n = int(ch(f"SELECT count() FROM {t} WHERE team_id IN ({lst})").strip() or 0)
        if n:
            ch(f"ALTER TABLE {t} DELETE WHERE team_id IN ({lst})", settings={"mutations_sync": 2})
            print("batch", b // a.batch, "cleared", t, n, flush=True)
    time.sleep(a.pause_s)
os.rename(p, p + ".done")
