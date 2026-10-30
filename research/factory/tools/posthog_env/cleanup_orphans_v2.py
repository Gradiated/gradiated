"""One batched ALTER DELETE per ClickHouse table for the rows of dead v2 team ids (orphans_v2.jsonl). Run when idle:
no rollouts, no loads (mutations are serialized server-wide). Prints counts only.

    cd /opt/posthog-env/posthog && .venv/bin/python ../loader/cleanup_orphans_v2.py [--dry-run]
"""
import argparse, json, os, sys

sys.path.insert(0, "/opt/posthog-env/loader")
from loader_common import ch, LOADER  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()
p = f"{LOADER}/orphans_v2.jsonl"
ids = sorted({int(json.loads(l)["team_id"]) for l in open(p)} if os.path.exists(p) else set())
live = set()
for f in ("teams.jsonl", "teams_v2.jsonl"):
    for l in open(f"{LOADER}/{f}"):
        r = json.loads(l)
        (live.discard if r.get("removed") else live.add)(int(r["team_id"]))
ids = [i for i in ids if i not in live and i not in (1, 2)]
print("orphan teams", len(ids))
if not ids or a.dry_run:
    sys.exit(0)
tables = ch("SELECT t.name FROM system.tables t WHERE t.database = currentDatabase() AND t.engine LIKE '%MergeTree%' "
            "AND t.total_rows > 0 AND t.name IN (SELECT table FROM system.columns WHERE database = currentDatabase() "
            "AND name = 'team_id')").split()
lst = ",".join(map(str, ids))
for t in tables:
    n = int(ch(f"SELECT count() FROM {t} WHERE team_id IN ({lst})").strip() or 0)
    if n:
        ch(f"ALTER TABLE {t} DELETE WHERE team_id IN ({lst})", settings={"mutations_sync": 2})
        print("cleared", t, n, flush=True)
os.rename(p, p + ".done")
