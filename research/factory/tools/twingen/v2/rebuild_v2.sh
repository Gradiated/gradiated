#!/bin/bash
# One-command v2 build: traces -> specs -> facts -> qfacts -> xindex -> gen2 -> load -> tasks -> replay ->
# calibrate/repair -> regenerate + reload changed twins -> replay -> per-task status.
#
#   rebuild_v2.sh --traces DIR --root WORK --tag TAG [--splits test_v2] [--workers 2] [--from STEP] [--to STEP]
#
#   --traces  directory with train.jsonl / dev.jsonl / test_v2.jsonl (searched recursively); omit to use the
#             original traces and the current specs (then --root defaults to the current data root)
#   --root    data root for this build (specs, facts, projects, overrides); required with --traces
#   --tag     keeps this build's teams (org "Twin2<tag> ", loader/teams_v2_<tag>.jsonl), tasks
#             (runner/tasks/v2_<tag>/) and replay (/tmp/fid2_<tag>) apart from other builds
#   --splits  splits to build (default test_v2; the replay/verify steps cover test_v2)
#   --from/--to  run a sub-range of steps: specs facts qfacts xindex gen load tasks replay repair reload after
#
# Loads run with --workers ClickHouse loaders (default 2; ClickHouse and Postgres are shared, keep it low).
# Replaced teams leave ClickHouse rows of dead team ids; run loader/cleanup_orphans_v2.py when nothing else runs.
set -euo pipefail
V2=/opt/posthog-sft/env-research/twingen/v2
TG=/opt/posthog-sft/env-research/twingen
PH=/opt/posthog-env/posthog
TRACES="" ROOT="" TAG="" SPLITS=test_v2 WORKERS=2 FROM=specs TO=after
while [ $# -gt 0 ]; do
  case "$1" in
    --traces) TRACES=$2; shift 2;; --root) ROOT=$2; shift 2;; --tag) TAG=$2; shift 2;;
    --splits) SPLITS=$2; shift 2;; --workers) WORKERS=$2; shift 2;; --from) FROM=$2; shift 2;; --to) TO=$2; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -n "$TRACES" ] && [ -z "$ROOT" ] && { echo "--root is required with --traces"; exit 2; }
[ -n "$TRACES" ] && export TWIN_V2_TRACES=$TRACES
[ -n "$ROOT" ] && export TWIN_V2_ROOT=$ROOT
export TWIN_V2_TAG=$TAG
eval "$(python3 -c "
import sys; sys.path.insert(0, '$V2'); import paths as P
for k in ('ROOT','PROJECTS','CALIB','TASKS_DIR','REPLAY_DIR','TEAMS','TARGETS','QFACTS'): print(f'P_{k}={getattr(P, k)!r}')
")"
STEPS=(specs facts qfacts xindex gen load tasks replay repair reload after)
idx() { local i; for i in "${!STEPS[@]}"; do if [ "${STEPS[$i]}" = "$1" ]; then echo "$i"; fi; done; return 0; }
A=$(idx "$FROM"); B=$(idx "$TO")
run() { local i; i=$(idx "$1"); [ "$i" -ge "$A" ] && [ "$i" -le "$B" ]; }
[ -z "$A" ] || [ -z "$B" ] && { echo "unknown step in --from/--to"; exit 2; }
log() { echo "[$(date +%T)] $*"; }
reasons=$(echo "$SPLITS" | tr , ,)
mkdir -p "$P_TASKS_DIR" "$P_REPLAY_DIR"

if run specs; then
  if [ -n "$TRACES" ]; then log specs; python3 -I $V2/build_specs.py --splits "$SPLITS"; else log "specs: using current specs"; fi
fi
run facts && { log facts; python3 -I $V2/facts.py --splits "$SPLITS"; }
run qfacts && { log qfacts; (cd $PH && .venv/bin/python $V2/qfacts.py --split "$SPLITS" 2>/dev/null | tail -1); }
run xindex && { log xindex; python3 -I $V2/xindex.py; }
run gen && { log gen; $TG/.venv/bin/python $V2/run_all2.py --reason "$reasons" --workers 8 --calib-dir "$P_CALIB" | tail -1; }
run load && { log load; (cd $PH && .venv/bin/python ../loader/load_all_v2.py --group "$reasons" --workers "$WORKERS" | tail -1); }
run tasks && { log tasks; python3 /opt/posthog-env/runner/build_tasks_v2.py --splits "$SPLITS"; }
replay() {  # $1 = label
  (cd $PH && python3 $V2/replay/extract_calls.py >/dev/null \
    && PYTHONUNBUFFERED=1 .venv/bin/python $V2/replay/replay.py > "$P_REPLAY_DIR/replay.log" 2>&1 \
    && PYTHONUNBUFFERED=1 .venv/bin/python $V2/replay/replay_ins.py > "$P_REPLAY_DIR/replay_ins.log" 2>&1 \
    && python3 $V2/replay/classify_sql.py > "$P_REPLAY_DIR/classify.out" && python3 $V2/replay/pertask.py > "$P_REPLAY_DIR/pertask.out" \
    && .venv/bin/python $V2/artefact_check.py 2>/dev/null | tail -1 \
    && python3 $V2/verify_tasks.py --label "$1" $([ "$1" = after ] && echo --final) \
    && python3 $V2/fidelity_compare.py /tmp/fid "$P_REPLAY_DIR" > "$P_REPLAY_DIR/compare_$1.txt")
}
run replay && { log "replay (before)"; replay before; }
if run repair; then
  log "repair: calibration + replay-driven overrides"
  python3 $V2/calib.py --replay "$P_REPLAY_DIR/replay.jsonl" --replay-ins "$P_REPLAY_DIR/replay_ins.jsonl" --out "$P_CALIB" --existing "$P_CALIB"
  python3 $V2/repair_overrides.py --replay "$P_REPLAY_DIR/replay.jsonl"
fi
if run reload; then
  log "reload: regenerate, reload twins whose project changed"
  python3 - "$P_PROJECTS" > "$P_REPLAY_DIR/manifests_before.json" <<'PY'
import glob, json, os, sys
print(json.dumps({os.path.basename(os.path.dirname(p)): json.load(open(p)).get("v2") for p in glob.glob(sys.argv[1] + "/*/manifest.json")}, default=str))
PY
  $TG/.venv/bin/python $V2/run_all2.py --reason "$reasons" --workers 8 --calib-dir "$P_CALIB" | tail -1
  CHANGED=$(python3 - "$P_PROJECTS" "$P_REPLAY_DIR/manifests_before.json" <<'PY'
import glob, json, os, sys
b = json.load(open(sys.argv[2]))
ch = [k for k in b if json.dumps(json.load(open(f"{sys.argv[1]}/{k}/manifest.json")).get("v2"), default=str, sort_keys=True) != json.dumps(b[k], default=str, sort_keys=True)]
print(",".join(ch))
PY
)
  log "changed twins: $(echo "$CHANGED" | tr , '\n' | grep -c . || true)"
  [ -n "$CHANGED" ] && (cd $PH && .venv/bin/python ../loader/load_all_v2.py --force --workers "$WORKERS" --ids "$CHANGED" | tail -1)
  python3 /opt/posthog-env/runner/build_tasks_v2.py --splits "$SPLITS"
fi
run after && { log "replay (after)"; replay after; cat "$P_REPLAY_DIR/compare_after.txt"; }
log done
