"""Load a twingen v2 project (projects_v2/<id>) as a NEW twin team (org "Twin2 <id>"), next to the v1 teams.

v1 is untouched: v2 teams have their own org prefix ("Twin2 "), user (twin2-<id>@twins.test), teams file
(loader/teams_v2.jsonl), state dir (loader/state_v2/) and project dir (twingen/projects_v2/). It reuses load_twin.py
(imported, not modified) and changes only:
- objects: saved insights and notebooks keep their production short ids, insights their production query JSON (absolute
  dates shifted by shift_days like the data), notebooks their production markdown (a markdown notebook node, so
  read_data renders it as in production), dashboards their production id when it is free, with tiles linked by short id;
- after the load, a team_state snapshot (loader/snapshots/<team>.json) so rollouts can be reset exactly.

    cd /opt/posthog-env/posthog
    .venv/bin/python ../loader/load_twin_v2.py <twin_id> [--anchor-date YYYY-MM-DD] [--force]
    .venv/bin/python ../loader/load_twin_v2.py --remove TEAM_ID       # v2 teams only
Prints aggregates only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import traceback

sys.path.insert(0, "/opt/posthog-env")
sys.path.insert(0, "/opt/posthog-env/loader")
import load_twin as LT  # noqa: E402
import loader_common as LC  # noqa: E402
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import paths as PATHS  # noqa: E402

PREFIX = PATHS.PREFIX
LOADER = LC.LOADER
TEAMS_V2 = PATHS.TEAMS
STATE_V2 = PATHS.STATE
PROJECTS_V2 = PATHS.PROJECTS
os.makedirs(STATE_V2, exist_ok=True)

# v2 paths for the parts of load_twin that write state (module globals; v1 files are never written)
LT.TEAMS_JSONL = TEAMS_V2
LT.STATE = STATE_V2
LT.ORPHANS_JSONL = PATHS.ORPHANS
DATE_Q = re.compile(r"(?<=['\"])(\d{4}-\d\d-\d\d)(?=[ T'\"\\])")


def read_teams_v2() -> dict:
    out = {}
    if os.path.exists(TEAMS_V2):
        for line in open(TEAMS_V2):
            if line.strip():
                r = json.loads(line)
                if r.get("removed"):
                    out.pop(r["twin_id"], None)
                else:
                    out[r["twin_id"]] = r
    return out


def shift_dates_json(obj, days: int):
    if not days:
        return obj
    s = json.dumps(obj)
    s = DATE_Q.sub(lambda m: (dt.date.fromisoformat(m.group(1)) + dt.timedelta(days=days)).isoformat(), s)
    return json.loads(s)


def remove_team_v2(team_id: int, clickhouse: bool = True) -> None:
    from posthog.models import Team, User

    assert team_id not in LC.PROTECTED_TEAMS
    team = Team.objects.filter(id=team_id).first()
    if team is not None and not team.organization.name.startswith(PREFIX):
        raise SystemExit(f"team {team_id} is not a v2 twin team")
    if clickhouse:
        LT.TwinLoader.reset_team_data(None, team_id)  # type: ignore[arg-type]
    else:
        LC.append_jsonl(LT.ORPHANS_JSONL, {"team_id": team_id, "at": dt.datetime.now(dt.UTC).isoformat()})
        from posthog.persons_db import persons_db_connection

        with persons_db_connection(writer=True) as conn, conn.cursor() as cur:
            for t in ("posthog_persondistinctid", "posthog_person", "posthog_group", "posthog_grouptypemapping"):
                cur.execute(f"DELETE FROM {t} WHERE team_id = %s", (team_id,))
            conn.commit()
    if team is not None:
        org = team.organization
        users = list(User.objects.filter(organization_membership__organization=org))
        org.delete()
        for u in users:
            if u.email.endswith("@twins.test") and u.email.startswith("twin2-"):
                u.delete()
    snap = f"{LOADER}/snapshots/{team_id}.json"
    if os.path.exists(snap):
        os.remove(snap)


LT.remove_team = remove_team_v2


class TwinLoaderV2(LT.TwinLoader):
    def ensure_team(self):
        from django.db import transaction

        from posthog.models import Organization, Team, User

        existing = read_teams_v2().get(self.twin_id)
        if existing and not self.force:
            return None, False
        if existing and self.force:
            team = Team.objects.filter(id=existing["team_id"]).first()
            if team is not None and team.organization.name.startswith(PREFIX):
                self.reset_team_data(team.id)
                self._reset_objects(team)
                return team, False
        tz = self.manifest.get("timezone") or "UTC"
        email = f"twin2-{self.twin_id[:24]}@twins.test"
        with transaction.atomic():
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=None, first_name="Twin")
            org, _, team = Organization.objects.bootstrap(
                user, name=f"{PREFIX}{self.twin_id}", team_fields={"name": "Default project", "timezone": tz})
        return team, True

    def _reset_objects(self, team):
        """--force reload: remove the team's objects and warehouse rows before re-creating them."""
        from products.dashboards.backend.models.dashboard import Dashboard
        from products.notebooks.backend.models import Notebook
        from products.product_analytics.backend.models.insight import Insight

        for M in (Insight, Dashboard, Notebook):
            M.objects.filter(team=team).delete()
        for mod, name in (("products.feature_flags.backend.models.feature_flag", "FeatureFlag"),
                          ("posthog.models", "Cohort"), ("posthog.models", "Action"),
                          ("products.surveys.backend.models", "Survey"),
                          ("products.experiments.backend.models.experiment", "Experiment")):
            try:
                M = getattr(__import__(mod, fromlist=[name]), name)
                M.objects.filter(team=team).delete()
            except Exception:  # noqa: BLE001
                pass
        try:
            from products.warehouse_sources.backend.models.table import DataWarehouseTable
            from products.warehouse_sources.backend.models.credential import DataWarehouseCredential  # noqa: F401
            DataWarehouseTable.objects.filter(team=team).delete()
        except Exception:  # noqa: BLE001
            pass

    def issue_remap(self) -> dict[str, str]:
        """Error-tracking issue ids are global primary keys and the v1 twin of the same conversation already holds the
        production ids, so ids taken by another team get a v2 UUID (events carry the same remapped id)."""
        from products.error_tracking.backend.models import ErrorTrackingIssue

        remap = super().issue_remap()
        ids = [str(i.get("id")) for i in self.objects.get("error_tracking_issues") or [] if i.get("id") is not None]
        cand = {i: remap.get(i, i) for i in ids}
        taken = set(str(x) for x in ErrorTrackingIssue.objects.filter(id__in=[v for v in cand.values() if LT.is_uuid(v)])
                    .exclude(team_id=getattr(self, "_team_id", -1)).values_list("id", flat=True))
        for i, v in cand.items():
            if v in taken:
                remap[i] = str(LT.uuid.uuid5(LT.NS, f"v2:{self.twin_id}:{i}"))
                self.stats["issues_id_remapped_v1_collision"] = self.stats.get("issues_id_remapped_v1_collision", 0) + 1
        return remap

    def load_clickhouse(self, team_id: int):
        self._team_id = team_id
        return super().load_clickhouse(team_id)

    def load_objects(self, team, user):
        O = self.objects
        held = {k: O.pop(k, None) for k in ("insights", "notebooks", "dashboards")}
        try:
            super().load_objects(team, user)  # flags, experiments, cohorts, actions, surveys, accounts, issues
        finally:
            for k, v in held.items():
                if v is not None:
                    O[k] = v
        self._load_v2_objects(team, user)

    def _load_v2_objects(self, team, user):
        from django.db import transaction

        from products.dashboards.backend.models.dashboard import Dashboard
        from products.dashboards.backend.models.dashboard_tile import DashboardTile
        from products.notebooks.backend.markdown_conversion import build_markdown_notebook_content
        from products.notebooks.backend.models import Notebook
        from products.product_analytics.backend.models.insight import Insight

        O = self.objects
        st = self.stats.setdefault("v2_objects", {})

        def bump(k):
            st[k] = st.get(k, 0) + 1

        def attempt(kind, fn):
            try:
                with transaction.atomic():
                    r = fn()
                self._count(kind, True)
                return r
            except Exception as e:  # noqa: BLE001
                self._count(kind, False)
                self.stats["warnings"].append(f"{kind}: {type(e).__name__}: {str(e)[:120]}")
                return None

        dashboards = {}
        for d in O.get("dashboards") or []:
            def mk_d(d=d):
                kw = dict(team=team, name=(d.get("name") or "Dashboard")[:400], description=d.get("description") or "",
                          created_by=user)
                did = d.get("dashboard_id")
                if isinstance(did, int) and not Dashboard._base_manager.filter(id=did).exists():
                    kw["id"] = did
                    bump("dashboards_prod_id")
                return Dashboard.objects.create(**kw)
            obj = attempt("dashboards", mk_d)
            if obj:
                for key in (d.get("name"), d.get("key"), d.get("dashboard_id")):
                    if key is not None:
                        dashboards[str(key)] = obj
        insights = {}
        for i in O.get("insights") or []:
            q = i.get("query_full") or i.get("query")
            if not isinstance(q, dict) or not q.get("kind"):
                q = None
            elif i.get("query_full"):
                q = shift_dates_json(q, self.shift_days)

            def mk_i(i=i, q=q):
                kw = dict(team=team, name=(i.get("name") or "")[:400] or None, description=(i.get("description") or "")[:400],
                          query=q, saved=True, created_by=user, last_modified_by=user)
                sid = i.get("short_id") or (i.get("key") if re.fullmatch(r"[A-Za-z0-9]{6,12}", str(i.get("key") or "")) else None)
                if sid and not Insight.objects.filter(team=team, short_id=sid).exists():
                    kw["short_id"] = sid
                    bump("insights_prod_short_id")
                if i.get("query_full"):
                    bump("insights_prod_query")
                return Insight.objects.create(**kw)
            ins = attempt("insights", mk_i)
            if ins:
                insights[ins.short_id] = ins
                for dn in i.get("dashboards") or []:
                    if str(dn) in dashboards:
                        DashboardTile.objects.get_or_create(dashboard=dashboards[str(dn)], insight=ins)
        for d in O.get("dashboards") or []:
            dash = dashboards.get(str(d.get("key")))
            for sid in d.get("tile_short_ids") or []:
                if dash and sid in insights:
                    DashboardTile.objects.get_or_create(dashboard=dash, insight=insights[sid])
                    bump("dashboard_tiles_prod")
        for n in O.get("notebooks") or []:
            def mk_n(n=n):
                title = (n.get("title") or "Notebook")[:256]
                md = n.get("content_markdown")
                if md:
                    content = build_markdown_notebook_content(md)
                    bump("notebooks_prod_content")
                else:
                    content = {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 1},
                                                           "content": [{"type": "text", "text": title}]}]}
                kw = dict(team=team, title=title, content=content, text_content=md or title, created_by=user,
                          last_modified_by=user)
                sid = n.get("short_id")
                if sid and not Notebook.objects.filter(team=team, short_id=sid).exists():
                    kw["short_id"] = sid[:12]
                    bump("notebooks_prod_short_id")
                return Notebook.objects.create(**kw)
            attempt("notebooks", mk_n)

    def run(self):
        state = super().run()
        if state:
            # snapshot of the post-load object state for exact resets (team_state.py restore --baseline snapshot)
            r = subprocess.run([sys.executable, f"{LOADER}/team_state.py", "snapshot", "--team-id", str(state["team_id"])],
                               capture_output=True, text=True, timeout=600)
            print(f"[load_twin_v2] snapshot team {state['team_id']}: rc={r.returncode}")
        return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir", nargs="?")
    ap.add_argument("--anchor-date", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--remove", type=int, default=None)
    ap.add_argument("--replace", action="store_true",
                    help="load into a NEW team and drop the old v2 team in Postgres only (its ClickHouse rows go to "
                         "orphans_v2.jsonl for one batched cleanup_orphans_v2 run); avoids a per-team ClickHouse mutation")
    a = ap.parse_args()
    if a.remove is not None:
        import boot

        boot.init()
        remove_team_v2(a.remove)
        LC.append_jsonl(TEAMS_V2, {"twin_id": next((k for k, v in read_teams_v2().items() if v["team_id"] == a.remove), None),
                                   "team_id": a.remove, "removed": True})
        print(f"[load_twin_v2] removed team {a.remove}")
        return
    pdir = a.project_dir if os.path.isabs(a.project_dir) or os.path.exists(a.project_dir) else os.path.join(PROJECTS_V2, a.project_dir)
    manifest = json.load(open(os.path.join(pdir, "manifest.json")))
    if a.anchor_date:
        shift = LT.shift_for(manifest, dt.date.fromisoformat(a.anchor_date))
    else:
        # whole days that keep the shifted "now" at or before the real clock (no future events; drift < 1 day)
        shift = (dt.datetime.now(dt.UTC) - LT.parse_dt(manifest["now_utc"])).days
    if a.replace:
        import boot

        boot.init()
        twin = os.path.basename(pdir.rstrip("/"))
        old = read_teams_v2().get(twin)
        if old:
            remove_team_v2(int(old["team_id"]), clickhouse=False)
            LC.append_jsonl(TEAMS_V2, {"twin_id": twin, "team_id": old["team_id"], "removed": True, "replaced": True})
    try:
        TwinLoaderV2(pdir, None, shift, a.force and not a.replace).run()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(limit=8)
        sys.exit(1)


if __name__ == "__main__":
    main()
