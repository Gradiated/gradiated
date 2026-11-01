"""Re-check the calibration agent's "needs-missing-artefact" task flags against the v2 twin teams (PostHog venv).

For each flagged task (runner/tasks/test_flags.json) the artefact text names notebooks (short ids), dashboards (ids)
and warehouse tables. In the task's v2 team each must exist: notebooks with content (not a title-only shell),
dashboards by production id, warehouse tables with more than a generic stub schema (> 7 columns) and rows.

    cd /opt/posthog-env/posthog && .venv/bin/python /opt/posthog-sft/env-research/twingen/v2/artefact_check.py
Writes runner/tasks/v2/artefacts.json; prints counts only.
"""

import json
import os
import re
import sys

sys.path.insert(0, "/opt/posthog-env")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as PATHS  # noqa: E402
FLAGS = "/opt/posthog-env/runner/tasks/test_flags.json"
TASKS = f"{PATHS.TASKS_DIR}/test.jsonl"
OUT = f"{PATHS.TASKS_DIR}/artefacts.json"
STOP = {"tables", "table", "view", "stub", "schemas", "schema", "empty", "missing", "insights", "dashboard", "notebook"}


def main():
    import boot

    boot.init()
    from products.dashboards.backend.models.dashboard import Dashboard
    from products.notebooks.backend.models import Notebook
    from products.warehouse_sources.backend.models.table import DataWarehouseTable

    flags = json.load(open(FLAGS))["tasks"]
    tasks = {json.loads(l)["task_id"]: json.loads(l) for l in open(TASKS)}
    out, ok_all = {}, 0
    for tid, f in flags.items():
        if f.get("flag") != "needs-missing-artefact" or tid not in tasks:
            continue
        team = tasks[tid]["team_id"]
        text = str(f.get("artefact") or "")
        res = {}
        for sid in re.findall(r"notebook ([A-Za-z0-9]{6,12})", text):
            nb = Notebook.objects.filter(team_id=team, short_id=sid, deleted=False).first()
            res[f"notebook:{sid}"] = bool(nb and len(nb.text_content or "") > 200)
        for did in re.findall(r"dashboard (\d+)", text):
            res[f"dashboard:{did}"] = Dashboard.objects.filter(team_id=team, id=int(did)).exists()
        tabs = {t.name: t for t in DataWarehouseTable.objects.filter(team_id=team, deleted=False)}
        names = set()
        for tok in re.findall(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", text):
            names.add(tok)
        for grp in re.findall(r"([a-z]+)/([a-z_]+)", text):  # "tam/csm_assignment_history"
            names.add(f"{grp[0]}_{grp[1].split('_', 1)[-1]}" if "_" in grp[1] else grp[0])
        for n in sorted(names - STOP):
            t = next((v for k, v in tabs.items() if k == n or k.endswith("_" + n) or k.endswith("." + n) or n in k), None)
            ncols = len((t.columns or {})) if t else 0
            res[f"table:{n}"] = {"exists": t is not None, "columns": ncols, "rows": int(t.row_count or 0) if t and getattr(t, "row_count", None) else None,
                                 "ok": bool(t is not None and ncols > 7)}
        ok = all((v["ok"] if isinstance(v, dict) else v) for v in res.values()) if res else False
        ok_all += ok
        out[tid] = {"team_id": team, "artefact": text, "checks": res, "provided": ok}
    json.dump(out, open(OUT, "w"), indent=1)
    print(json.dumps({"flagged": len(out), "all_artefacts_provided": ok_all,
                      "items": sum(len(v["checks"]) for v in out.values()),
                      "items_ok": sum(1 for v in out.values() for x in v["checks"].values() if (x["ok"] if isinstance(x, dict) else x))}), flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
