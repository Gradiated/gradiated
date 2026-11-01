"""Snapshot, diff, restore and scan the agent-writable object state of twin teams.

Rollouts of the PostHog AI agent (runner/run_task.py, correct/run_hint.py, rft/) persist objects into the twin
teams (saved insights, dashboards, notebooks, flags, cohorts, surveys, experiments, actions, memories, edits and
soft deletes). This module measures that leakage and resets it. Run with the PostHog venv:

    cd /opt/posthog-env/posthog
    .venv/bin/python ../loader/team_state.py snapshot --team-id N [--out PATH]
    .venv/bin/python ../loader/team_state.py diff --team-id N [--baseline snapshot|loadtime]
    .venv/bin/python ../loader/team_state.py restore --team-id N [--baseline snapshot|loadtime] [--min-age-h H] [--apply]
    .venv/bin/python ../loader/team_state.py scan --tasks ../runner/tasks/test.jsonl     # read-only

Baselines:
  snapshot  loader/snapshots/<team>.json (full field values). Restore deletes objects created after it, re-inserts
            deleted rows and writes snapshot values back into modified or soft-deleted rows.
  loadtime  for teams without a snapshot: objects with created_at <= mtime(loader/state/<team>.json) + 30 min are
            baseline. Restore can only delete objects created after that; edits and soft deletes are reported only.

restore is a dry run unless --apply is given, and refuses teams 1 and 2 and organizations whose name does not start
with "Twin". In-process tracking for one rollout (used by run_task.py --reset-team-state) is RunTracker below.
Prints aggregates only (counts by kind), never object contents.
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
import datetime as dt
import threading
from collections import Counter, defaultdict

LOADER = "/opt/posthog-env/loader"
STATE_DIR = os.path.join(LOADER, "state")
SNAP_DIR = os.path.join(LOADER, "snapshots")
PROTECTED_TEAMS = {1, 2}
LOADTIME_SLACK = dt.timedelta(minutes=30)

# kind -> (model label, path from the model to the team id). Order = deletion order (dependents first).
KINDS: list[tuple[str, str, str]] = [
    ("alert_subscription", "alerts.AlertSubscription", "alert_configuration__team_id"),
    ("alert", "alerts.AlertConfiguration", "team_id"),
    ("threshold", "alerts.Threshold", "team_id"),
    ("experiment_to_saved_metric", "experiments.ExperimentToSavedMetric", "experiment__team_id"),
    ("experiment", "experiments.Experiment", "team_id"),
    ("experiment_saved_metric", "experiments.ExperimentSavedMetric", "team_id"),
    ("survey", "surveys.Survey", "team_id"),
    ("feature_flag_dashboards", "feature_flags.FeatureFlagDashboards", "feature_flag__team_id"),
    ("feature_flag_evaluation_context", "feature_flags.FeatureFlagEvaluationContext", "feature_flag__team_id"),
    ("feature_flag", "feature_flags.FeatureFlag", "team_id"),
    ("evaluation_context", "feature_flags.EvaluationContext", "team_id"),
    ("dashboard_tile", "dashboards.DashboardTile", "dashboard__team_id"),
    ("text", "dashboards.Text", "team_id"),
    ("dashboard", "dashboards.Dashboard", "team_id"),
    ("insight_viewed", "product_analytics.InsightViewed", "team_id"),
    ("insight", "product_analytics.Insight", "team_id"),
    ("resource_notebook", "notebooks.ResourceNotebook", "notebook__team_id"),
    ("notebook", "notebooks.Notebook", "team_id"),
    ("cohort", "cohorts.Cohort", "team_id"),
    ("action", "actions.Action", "team_id"),
    ("annotation", "annotations.Annotation", "team_id"),
    ("hog_function", "cdp.HogFunction", "team_id"),
    ("hog_flow", "workflows.HogFlow", "team_id"),
    ("message_template", "messaging.MessageTemplate", "team_id"),
    ("error_tracking_assignment", "error_tracking.ErrorTrackingIssueAssignment", "team_id"),
    ("error_tracking_issue", "error_tracking.ErrorTrackingIssue", "team_id"),
    ("task", "tasks.Task", "team_id"),
    ("replay_observation_label", "replay_vision.ReplayObservationLabel", "team_id"),
    ("replay_scanner", "replay_vision.ReplayScanner", "team_id"),
    ("account", "customer_analytics.Account", "team_id"),
    ("saved_query", "data_modeling.DataWarehouseSavedQuery", "team_id"),
    ("tagged_item", "posthog.TaggedItem", "team_id"),
    ("tag", "posthog.Tag", "team_id"),
    ("core_memory", "posthog_ai.CoreMemory", "team_id"),
    ("agent_memory", "posthog_ai.AgentMemory", "team_id"),
    ("file_system", "posthog.FileSystem", "team_id"),
    ("activity_log", "posthog.ActivityLog", "team_id"),  # read_data reads the activity log
]
# Kinds snapshotted by id only (append-only, many rows).
IDS_ONLY = {"activity_log"}
# Fields that change without an agent edit (query execution, cohort calculation, view tracking).
VOLATILE = {"updated_at", "last_refresh", "last_accessed_at", "last_viewed_at", "last_called_at", "refreshing",
            "refresh_attempt", "is_calculating", "last_calculation", "errors_calculating", "count",
            "pending_version", "last_error_at", "last_backfill_person_properties_at"}
VOLATILE_BY_KIND = {"cohort": {"version"}}


# --------------------------------------------------------------------------------------------------------------
# Django helpers


def init_django() -> None:
    sys.path.insert(0, "/opt/posthog-env")
    import boot

    boot.init()


_MODELS: dict[str, tuple] | None = None


def kinds() -> dict[str, tuple]:
    """kind -> (model, team_path, attnames, has_created_at, has_deleted). Kinds whose model is missing are skipped."""
    global _MODELS
    if _MODELS is None:
        from django.apps import apps

        out = {}
        for kind, label, path in KINDS:
            try:
                m = apps.get_model(label)
                m._base_manager.filter(**{path: 0}).query  # validates the path
            except Exception:
                continue
            attnames = [f.attname for f in m._meta.concrete_fields if not getattr(f, "generated", False)]
            names = {f.name for f in m._meta.concrete_fields}
            out[kind] = (m, path, attnames, "created_at" in names, "deleted" in names)
        _MODELS = out
    return _MODELS


def kind_of_model(model) -> str | None:
    model = model._meta.concrete_model
    for kind, (m, *_rest) in kinds().items():
        if m is model:
            return kind
    return None


def encode(v):
    from django.core.serializers.json import DjangoJSONEncoder

    return json.loads(json.dumps(v, cls=DjangoJSONEncoder, default=str))


def decode_row(model, row: dict) -> dict:
    out = {}
    for f in model._meta.concrete_fields:
        if f.attname in row:
            v = row[f.attname]
            try:
                out[f.attname] = f.to_python(v) if v is not None and not f.get_internal_type() == "JSONField" else v
            except Exception:
                out[f.attname] = v
    return out


def pk_key(v) -> str:
    return str(v)


def team_or_refuse(team_id: int):
    from posthog.models import Team

    if team_id in PROTECTED_TEAMS:
        raise SystemExit(f"refusing protected team {team_id}")
    team = Team.objects.select_related("organization").filter(id=team_id).first()
    if team is None:
        raise SystemExit(f"team {team_id} not found")
    if not (team.organization.name or "").startswith("Twin"):
        raise SystemExit(f"refusing team {team_id}: organization is not a twin org")
    return team


def load_threshold(team_id: int) -> dt.datetime | None:
    st = os.path.join(STATE_DIR, f"{team_id}.json")
    if not os.path.exists(st):
        return None
    return dt.datetime.fromtimestamp(os.path.getmtime(st), dt.UTC) + LOADTIME_SLACK


def snapshot_path(team_id: int) -> str:
    return os.path.join(SNAP_DIR, f"{team_id}.json")


def load_snapshot(team_id: int, path: str | None = None) -> dict | None:
    p = path or snapshot_path(team_id)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


# --------------------------------------------------------------------------------------------------------------
# snapshot / diff / restore


def take_snapshot(team_id: int) -> dict:
    from posthog.models import Team

    team = Team.objects.select_related("organization").get(id=team_id)
    snap = {"team_id": team_id, "org_name": team.organization.name, "taken_at": dt.datetime.now(dt.UTC).isoformat(),
            "objects": {}}
    for kind, (m, path, attnames, _c, _d) in kinds().items():
        qs = m._base_manager.filter(**{path: team_id})
        if kind in IDS_ONLY:
            snap["objects"][kind] = {pk_key(pk): None for pk in qs.values_list("pk", flat=True)}
        else:
            snap["objects"][kind] = {pk_key(r[m._meta.pk.attname]): encode(r) for r in qs.values(*attnames)}
    return snap


def compute_diff(team_id: int, baseline: str, snap: dict | None = None, min_age: dt.timedelta | None = None) -> dict:
    """Per kind: created / deleted / modified / soft_deleted pk lists (+ 'unknown' for loadtime limits).

    min_age: only objects whose created_at (created) or updated_at (modified) is older than now - min_age; rows
    without a timestamp are skipped from created/modified under min_age (age unknown), except loadtime tiles that
    cascade from aged objects anyway.
    """
    now = dt.datetime.now(dt.UTC)
    cutoff = now - min_age if min_age else None
    res: dict[str, dict] = {}
    if baseline == "snapshot":
        if snap is None:
            raise SystemExit(f"no snapshot for team {team_id}")
        for kind, (m, path, attnames, has_c, has_d) in kinds().items():
            base = snap["objects"].get(kind)
            if base is None:
                continue
            qs = m._base_manager.filter(**{path: team_id})
            r = {"created": [], "deleted": [], "modified": [], "soft_deleted": []}
            vol = VOLATILE | VOLATILE_BY_KIND.get(kind, set())
            if kind in IDS_ONLY:
                cur = {pk_key(pk): None for pk in qs.values_list("pk", flat=True)}
                if cutoff and has_c:  # ids-only kinds still need created_at for the age filter
                    new = [k for k in cur if k not in base]
                    if new:
                        cur.update({pk_key(pk): {"created_at": encode(c)} for pk, c in
                                    qs.filter(pk__in=new).values_list("pk", "created_at")})
            else:
                cur = {pk_key(row[m._meta.pk.attname]): encode(row) for row in qs.values(*attnames)}
            for k, row in cur.items():
                if k not in base:
                    if cutoff and not (row and has_c and row.get("created_at") and
                                       dt.datetime.fromisoformat(row["created_at"]) < cutoff):
                        continue
                    r["created"].append(k)
                elif row is not None and base[k] is not None:
                    diff = {f for f in attnames if f not in vol and row.get(f) != base[k].get(f)}
                    if not diff:
                        continue
                    if cutoff:
                        ts = row.get("updated_at") or row.get("last_modified_at")
                        if not ts or dt.datetime.fromisoformat(ts) >= cutoff:
                            continue
                    if has_d and "deleted" in diff and row.get("deleted") and not base[k].get("deleted"):
                        r["soft_deleted"].append(k)
                    else:
                        r["modified"].append(k)
            if not cutoff:
                r["deleted"] = [k for k in base if k not in cur]
            res[kind] = r
        return res

    thr = load_threshold(team_id)
    if thr is None:
        raise SystemExit(f"no loader state for team {team_id}")
    for kind, (m, path, attnames, has_c, has_d) in kinds().items():
        qs = m._base_manager.filter(**{path: team_id})
        r = {"created": [], "deleted": [], "modified": [], "soft_deleted": [], "unknown": False}
        if has_c:
            cq = qs.filter(created_at__gt=thr)
            if cutoff:
                cq = cq.filter(created_at__lt=cutoff)
            r["created"] = [pk_key(pk) for pk in cq.values_list("pk", flat=True)]
            base = qs.filter(created_at__lte=thr)
            ts_field = "updated_at" if "updated_at" in attnames else ("last_modified_at" if "last_modified_at" in attnames else None)
            if ts_field:
                bq = base.filter(**{f"{ts_field}__gt": thr})
                if has_d:
                    r["soft_deleted"] = [pk_key(pk) for pk in bq.filter(deleted=True).values_list("pk", flat=True)]
                    bq = bq.filter(deleted=False)
                r["modified"] = [pk_key(pk) for pk in bq.values_list("pk", flat=True)]
            elif has_d:
                # no update timestamp: a soft-deleted baseline row is a post-load delete (the loader creates none)
                r["soft_deleted"] = [pk_key(pk) for pk in base.filter(deleted=True).values_list("pk", flat=True)]
        elif kind == "dashboard_tile":
            # tiles have no created_at: count tiles hanging off post-load dashboards or insights (they cascade)
            cq = qs.filter(dashboard__created_at__gt=thr) | qs.filter(insight__created_at__gt=thr)
            r["created"] = [pk_key(pk) for pk in cq.values_list("pk", flat=True)]
            r["cascade_only"] = True
        elif kind == "core_memory":
            # the loader creates no CoreMemory; any row is agent-written (no timestamp, so no age filter)
            if not cutoff:
                r["created"] = [pk_key(pk) for pk in qs.values_list("pk", flat=True)]
        else:
            r["unknown"] = True
        res[kind] = r
    return res


def summarize(diff: dict) -> dict:
    out = {}
    for kind, r in diff.items():
        c = {k: len(r.get(k) or []) for k in ("created", "deleted", "modified", "soft_deleted")}
        c = {k: v for k, v in c.items() if v}
        if c:
            out[kind] = c
    return out


def apply_restore(team_id: int, baseline: str, diff: dict, snap: dict | None, apply: bool) -> dict:
    """Delete created objects, then (snapshot baseline) re-insert deleted rows and write back modified rows."""
    from django.db import transaction

    K = kinds()
    stats = Counter()
    errors = Counter()
    order = [k for k, *_ in KINDS if k in K]
    # 1. delete post-baseline objects (dependents first; Django cascades the rest). Two passes for PROTECT chains.
    pending = [(kind, pk) for kind in order for pk in (diff.get(kind, {}).get("created") or [])
               if not diff.get(kind, {}).get("cascade_only")]
    for _pass in range(2):
        left = []
        for kind, pk in pending:
            m, path, *_ = K[kind]
            obj = m._base_manager.filter(pk=pk, **{path: team_id}).first()
            if obj is None:
                stats[f"gone:{kind}"] += 1
                continue
            if not apply:
                stats[f"would_delete:{kind}"] += 1
                continue
            try:
                with transaction.atomic():
                    obj.delete()
                stats[f"deleted:{kind}"] += 1
            except Exception as e:  # noqa: BLE001
                left.append((kind, pk))
                errors[f"{kind}:{type(e).__name__}"] += 1
        pending = left
        if not pending:
            break
    if baseline != "snapshot" or snap is None:
        for kind in order:
            r = diff.get(kind, {})
            for what in ("modified", "soft_deleted"):
                if r.get(what):
                    stats[f"not_restorable_{what}:{kind}"] += len(r[what])
        return {"stats": dict(stats), "errors": dict(errors) if pending else {}, "unresolved": len(pending)}
    # 2. re-insert hard-deleted baseline rows (parents first), 3. write snapshot values into modified rows
    for kind in reversed(order):
        m, path, attnames, *_ = K[kind]
        r = diff.get(kind, {})
        base = snap["objects"].get(kind) or {}
        for pk in r.get("deleted") or []:
            if base.get(pk) is None:
                continue
            if not apply:
                stats[f"would_reinsert:{kind}"] += 1
                continue
            try:
                reinsert(m, decode_row(m, base[pk]))
                stats[f"reinserted:{kind}"] += 1
            except Exception as e:  # noqa: BLE001
                errors[f"reinsert:{kind}:{type(e).__name__}"] += 1
        for what in ("modified", "soft_deleted"):
            for pk in r.get(what) or []:
                if base.get(pk) is None:
                    continue
                if not apply:
                    stats[f"would_restore_{what}:{kind}"] += 1
                    continue
                try:
                    write_back(m, decode_row(m, base[pk]))
                    stats[f"restored_{what}:{kind}"] += 1
                except Exception as e:  # noqa: BLE001
                    errors[f"restore:{kind}:{type(e).__name__}"] += 1
    return {"stats": dict(stats), "errors": dict(errors), "unresolved": len(pending)}


def write_back(model, row: dict) -> int:
    pk_att = model._meta.pk.attname
    vals = {k: v for k, v in row.items() if k != pk_att}
    return model._base_manager.filter(pk=row[pk_att]).update(**vals)


def reinsert(model, row: dict) -> None:
    from django.db import transaction

    with transaction.atomic():
        model._base_manager.bulk_create([model(**row)])
        write_back(model, row)  # bulk_create re-stamps auto_now(_add) fields


# --------------------------------------------------------------------------------------------------------------
# In-process tracking for one rollout (run_task.py --reset-team-state)

_TRACKER: "RunTracker | None" = None
_LOCAL = threading.local()


class RunTracker:
    """Records objects this process creates and the original rows of objects it modifies or deletes, then undoes
    them. Rollouts of the same task share a team, so a rollout only undoes its own writes.

    Signals: post_save(created) -> created; pre_save on an existing row -> original row; pre_delete -> full row.
    QuerySet.update / bulk_update and QuerySet.bulk_create skip signals and are patched for tracked models.
    Raw SQL is not seen.
    """

    def __init__(self, team_id: int):
        self.team_id = team_id
        self.active = False
        self.lock = threading.RLock()
        self.created: dict[tuple[str, str], float] = {}
        self.originals: dict[tuple[str, str], dict] = {}
        self.deleted: dict[tuple[str, str], dict] = {}
        self.deleted_order: list[tuple[str, str]] = []
        self.untracked_created: Counter = Counter()
        self.snapshot = load_snapshot(team_id)
        self.refused = None
        self._orig_update = None
        self._orig_bulk_create = None

    # ---- install / signals
    def install(self) -> None:
        global _TRACKER
        from django.db.models import signals
        from django.db.models.query import QuerySet

        team = team_or_refuse_soft(self.team_id)
        if isinstance(team, str):
            self.refused = team
            return
        _TRACKER = self
        for kind, (m, *_r) in kinds().items():
            signals.pre_save.connect(_pre_save, sender=m, dispatch_uid=f"ts_pre_save_{kind}", weak=False)
            signals.post_save.connect(_post_save, sender=m, dispatch_uid=f"ts_post_save_{kind}", weak=False)
            signals.pre_delete.connect(_pre_delete, sender=m, dispatch_uid=f"ts_pre_delete_{kind}", weak=False)
            signals.post_delete.connect(_post_delete, sender=m, dispatch_uid=f"ts_post_delete_{kind}", weak=False)
        signals.post_save.connect(_post_save_any, dispatch_uid="ts_post_save_any", weak=False)
        if not getattr(QuerySet, "_ts_patched", False):
            self._orig_update = QuerySet.update
            self._orig_bulk_create = QuerySet.bulk_create
            orig_update, orig_bulk = QuerySet.update, QuerySet.bulk_create

            def update(qs, **kw):
                t = _TRACKER
                if t is not None and t.active and not getattr(_LOCAL, "busy", False):
                    kind = kind_of_model(qs.model)
                    if kind:
                        t.capture_queryset(kind, qs)
                return orig_update(qs, **kw)

            def bulk_create(qs, objs, *a, **kw):
                res = orig_bulk(qs, objs, *a, **kw)
                t = _TRACKER
                if t is not None and t.active and not getattr(_LOCAL, "busy", False):
                    kind = kind_of_model(qs.model)
                    if kind:
                        for o in res:
                            if o.pk is not None:
                                t.mark_created(kind, o.pk)
                return res

            QuerySet.update = update
            QuerySet.bulk_create = bulk_create
            QuerySet._ts_patched = True
        self.active = True

    def mark_created(self, kind: str, pk) -> None:
        with self.lock:
            self.created.setdefault((kind, pk_key(pk)), time.time())

    def capture_row(self, kind: str, pk) -> None:
        key = (kind, pk_key(pk))
        with self.lock:
            if key in self.created or key in self.originals:
                return
        m = kinds()[kind][0]
        _LOCAL.busy = True
        try:
            row = m._base_manager.filter(pk=pk).values(*kinds()[kind][2]).first()
        finally:
            _LOCAL.busy = False
        if row is not None:
            with self.lock:
                self.originals.setdefault(key, row)

    def capture_queryset(self, kind: str, qs) -> None:
        m, _p, attnames, *_ = kinds()[kind]
        _LOCAL.busy = True
        try:
            rows = list(m._base_manager.filter(pk__in=qs.order_by().values("pk")).values(*attnames)[:5000])
        finally:
            _LOCAL.busy = False
        with self.lock:
            for row in rows:
                key = (kind, pk_key(row[m._meta.pk.attname]))
                if key not in self.created:
                    self.originals.setdefault(key, row)

    # ---- undo
    def finish(self) -> dict:
        """Undo this process's writes in the team. Safe to call twice (second call is a no-op)."""
        if self.refused:
            return {"refused": self.refused}
        if not self.active:
            return getattr(self, "_result", {"inactive": True})
        self.active = False
        t0 = time.time()
        K = kinds()
        order = [k for k, *_ in KINDS if k in K]
        stats: Counter = Counter()
        errors: Counter = Counter()
        snap_objs = (self.snapshot or {}).get("objects") or {}
        from django.db import transaction

        _LOCAL.busy = True
        try:
            # 1. delete objects this process created (reverse creation order, then retry once)
            created = sorted(self.created.items(), key=lambda kv: -kv[1])
            pending = [k for k, _t in created]
            created_counts = Counter(kind for kind, _pk in pending)
            for _pass in range(2):
                left = []
                for kind, pk in pending:
                    m, path, *_ = K[kind]
                    obj = m._base_manager.filter(pk=pk, **{path: self.team_id}).first()
                    if obj is None:
                        stats[f"gone:{kind}"] += 1  # cascaded, deleted by the agent, or another team
                        continue
                    try:
                        with transaction.atomic():
                            obj.delete()
                        stats[f"deleted:{kind}"] += 1
                    except Exception as e:  # noqa: BLE001
                        left.append((kind, pk))
                        errors[f"delete:{kind}:{type(e).__name__}"] += 1
                pending = left
                if not pending:
                    break
            # 2. re-insert baseline rows this process hard-deleted (parents first = reverse of pre_delete order)
            for kind, pk in reversed(self.deleted_order):
                m, path, *_ = K[kind]
                row = self.deleted[(kind, pk)]
                if not row.get("_team_ok") or m._base_manager.filter(pk=row[m._meta.pk.attname]).exists():
                    continue
                base = (snap_objs.get(kind) or {}).get(pk)
                row = decode_row(m, base) if base else {k: v for k, v in row.items() if not k.startswith("_")}
                try:
                    reinsert(m, row)
                    stats[f"reinserted:{kind}"] += 1
                except Exception as e:  # noqa: BLE001
                    errors[f"reinsert:{kind}:{type(e).__name__}"] += 1
            # 3. restore rows this process modified (snapshot values when the team has a snapshot)
            for (kind, pk), row in self.originals.items():
                if (kind, pk) in self.created:
                    continue
                m, path, *_ = K[kind]
                if not m._base_manager.filter(pk=row[m._meta.pk.attname], **{path: self.team_id}).exists():
                    continue
                base = (snap_objs.get(kind) or {}).get(pk)
                target = decode_row(m, base) if base else row
                try:
                    cur = m._base_manager.filter(pk=row[m._meta.pk.attname]).values(*K[kind][2]).first()
                    if cur is not None and encode(cur) == encode(target):
                        stats[f"unchanged:{kind}"] += 1
                        continue
                    write_back(m, target)
                    stats[f"restored:{kind}"] += 1
                except Exception as e:  # noqa: BLE001
                    errors[f"restore:{kind}:{type(e).__name__}"] += 1
        finally:
            _LOCAL.busy = False
        self._result = {
            "created": dict(created_counts),
            "modified": dict(Counter(k for k, _ in self.originals)),
            "deleted_baseline": dict(Counter(k for k, _ in self.deleted_order)),
            "actions": dict(stats),
            "errors": dict(errors),
            "unresolved": len(pending),
            "untracked_created": dict(self.untracked_created),
            "baseline_values": "snapshot" if self.snapshot else "captured",
            "elapsed_s": round(time.time() - t0, 2),
        }
        return self._result


def install_exit_hooks(tracker: RunTracker) -> None:
    """Undo on an uncaught exception or SIGTERM too. SIGKILL (run_tasks.py hard timeout) cannot be caught; the
    'sweep' mode of a later run removes what such a run left once it is older than the sweep age."""
    import signal

    prev = sys.excepthook

    def hook(tp, val, tb):
        try:
            tracker.finish()
        except Exception:  # noqa: BLE001
            pass
        prev(tp, val, tb)

    sys.excepthook = hook

    def on_term(signum, _frame):
        try:
            tracker.finish()
        finally:
            os._exit(128 + signum)

    try:
        signal.signal(signal.SIGTERM, on_term)
    except ValueError:  # not the main thread
        pass


def team_or_refuse_soft(team_id: int):
    try:
        return team_or_refuse(team_id)
    except SystemExit as e:
        return str(e)


def _pre_save(sender, instance, raw=False, **kw):
    t = _TRACKER
    if t is None or not t.active or raw or getattr(_LOCAL, "busy", False) or instance._state.adding or instance.pk is None:
        return
    kind = kind_of_model(sender)
    if kind:
        t.capture_row(kind, instance.pk)


def _post_save(sender, instance, created=False, raw=False, **kw):
    t = _TRACKER
    if t is None or not t.active or raw or not created or getattr(_LOCAL, "busy", False):
        return
    kind = kind_of_model(sender)
    if kind:
        t.mark_created(kind, instance.pk)


def _post_save_any(sender, instance, created=False, **kw):
    t = _TRACKER
    if t is None or not t.active or not created or getattr(_LOCAL, "busy", False):
        return
    if kind_of_model(sender) is None and getattr(instance, "team_id", None) == t.team_id:
        with t.lock:
            t.untracked_created[sender._meta.label] += 1


def _pre_delete(sender, instance, **kw):
    t = _TRACKER
    if t is None or not t.active or getattr(_LOCAL, "busy", False):
        return
    kind = kind_of_model(sender)
    if not kind:
        return
    key = (kind, pk_key(instance.pk))
    with t.lock:
        if key in t.created or key in t.deleted:
            return
    m, path, attnames, *_ = kinds()[kind]
    _LOCAL.busy = True
    try:
        row = m._base_manager.filter(pk=instance.pk).values(*attnames).first()
        team_ok = m._base_manager.filter(pk=instance.pk, **{path: t.team_id}).exists() if row else False
    finally:
        _LOCAL.busy = False
    if row is None:
        return
    row = dict(row, _team_ok=team_ok)
    with t.lock:
        t.deleted[key] = t.originals.get(key) and dict(t.originals[key], _team_ok=team_ok) or row
        t.deleted_order.append(key)


def _post_delete(sender, instance, **kw):
    pass  # created rows that were deleted again show up as "gone" at finish()


def sweep(team_id: int, min_age_h: float = 2.0) -> dict:
    """Pre-run sweep: undo post-baseline state older than min_age_h (so no live rollout owns it)."""
    if team_id in PROTECTED_TEAMS:
        return {"refused": "protected team"}
    t = team_or_refuse_soft(team_id)
    if isinstance(t, str):
        return {"refused": t}
    snap = load_snapshot(team_id)
    baseline = "snapshot" if snap else "loadtime"
    if baseline == "loadtime" and load_threshold(team_id) is None:
        return {"skipped": "no snapshot and no loader state"}
    t0 = time.time()
    d = compute_diff(team_id, baseline, snap, min_age=dt.timedelta(hours=min_age_h))
    res = apply_restore(team_id, baseline, d, snap, apply=True)
    return {"baseline": baseline, "min_age_h": min_age_h, "found": summarize(d), **res,
            "elapsed_s": round(time.time() - t0, 2)}


# --------------------------------------------------------------------------------------------------------------
# CLI


def cmd_snapshot(a) -> None:
    team = team_or_refuse(a.team_id)
    snap = take_snapshot(team.id)
    out = a.out or snapshot_path(team.id)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".tmp", "w") as f:
        json.dump(snap, f)
    os.replace(out + ".tmp", out)
    print(json.dumps({"team_id": team.id, "out": out, "counts": {k: len(v) for k, v in snap["objects"].items() if v}}))


def resolve_baseline(team_id: int, baseline: str | None, snap_path: str | None):
    snap = load_snapshot(team_id, snap_path)
    if baseline is None:
        baseline = "snapshot" if snap else "loadtime"
    if baseline == "snapshot" and snap is None:
        raise SystemExit(f"no snapshot for team {team_id}")
    return baseline, snap


def cmd_diff(a) -> None:
    from posthog.models import Team

    if not Team.objects.filter(id=a.team_id).exists():
        raise SystemExit("team not found")
    baseline, snap = resolve_baseline(a.team_id, a.baseline, a.snapshot)
    d = compute_diff(a.team_id, baseline, snap)
    unknown = sorted(k for k, r in d.items() if r.get("unknown"))
    print(json.dumps({"team_id": a.team_id, "baseline": baseline, "changes": summarize(d),
                      "total": {w: sum(len(r.get(w) or []) for r in d.values())
                                for w in ("created", "deleted", "modified", "soft_deleted")},
                      **({"untracked_kinds_loadtime": unknown} if unknown else {})}, indent=1))


def cmd_restore(a) -> None:
    team = team_or_refuse(a.team_id)
    baseline, snap = resolve_baseline(team.id, a.baseline, a.snapshot)
    min_age = dt.timedelta(hours=a.min_age_h) if a.min_age_h else None
    d = compute_diff(team.id, baseline, snap, min_age=min_age)
    res = apply_restore(team.id, baseline, d, snap, apply=a.apply)
    print(json.dumps({"team_id": team.id, "baseline": baseline, "apply": a.apply, "found": summarize(d), **res}, indent=1))


def cmd_scan(a) -> None:
    """Read-only loadtime-baseline leakage report over the teams of task files."""
    team_ids: dict[int, int] = Counter()
    for path in a.tasks:
        with open(path) as f:
            for line in f:
                if line.strip():
                    team_ids[json.loads(line)["team_id"]] += 1
    per_kind = Counter()
    teams_by_kind = Counter()
    mod_kind = Counter()
    soft_kind = Counter()
    affected = 0
    affected_any = 0
    no_state = 0
    by_team_total = []
    for tid in sorted(team_ids):
        if tid in PROTECTED_TEAMS:
            continue
        if load_threshold(tid) is None:
            no_state += 1
            continue
        d = compute_diff(tid, "loadtime")
        n = 0
        for kind, r in d.items():
            c = len(r.get("created") or [])
            if c:
                per_kind[kind] += c
                teams_by_kind[kind] += 1
                if not r.get("cascade_only"):
                    n += c
            mod_kind[kind] += len(r.get("modified") or [])
            soft_kind[kind] += len(r.get("soft_deleted") or [])
        if n:
            affected += 1
        if n or any(r.get("modified") or r.get("soft_deleted") for r in d.values()):
            affected_any += 1
        by_team_total.append(n)
    by_team_total.sort(reverse=True)
    print(json.dumps({
        "task_files": a.tasks, "tasks": sum(team_ids.values()), "teams": len(team_ids), "teams_without_loader_state": no_state,
        "teams_with_post_load_objects": affected, "teams_with_any_change": affected_any,
        "created_by_kind": dict(per_kind.most_common()), "teams_by_kind": dict(teams_by_kind.most_common()),
        "created_total_excl_tiles": sum(v for k, v in per_kind.items() if k != "dashboard_tile"),
        "modified_after_load_by_kind": {k: v for k, v in mod_kind.most_common() if v},
        "soft_deleted_by_kind": {k: v for k, v in soft_kind.most_common() if v},
        "max_created_in_one_team": by_team_total[0] if by_team_total else 0,
        "note": "loadtime baseline: created_at > mtime(state)+30min; tag/tagged_item/text/insight_viewed have no "
                "timestamp and are not counted; modified = updated_at/last_modified_at after load (includes "
                "volatile fields)",
    }, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("snapshot")
    p.add_argument("--team-id", type=int, required=True)
    p.add_argument("--out")
    for name in ("diff", "restore"):
        p = sub.add_parser(name)
        p.add_argument("--team-id", type=int, required=True)
        p.add_argument("--baseline", choices=["snapshot", "loadtime"], help="default: snapshot if present, else loadtime")
        p.add_argument("--snapshot", help="snapshot path (default loader/snapshots/<team>.json)")
        if name == "restore":
            p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
            p.add_argument("--dry-run", action="store_true", help="explicit dry run (the default)")
            p.add_argument("--min-age-h", type=float, default=0.0,
                           help="only undo objects created/modified more than H hours ago")
    p = sub.add_parser("scan")
    p.add_argument("--tasks", nargs="+", required=True)
    a = ap.parse_args()
    if getattr(a, "dry_run", False):
        a.apply = False
    init_django()
    {"snapshot": cmd_snapshot, "diff": cmd_diff, "restore": cmd_restore, "scan": cmd_scan}[a.cmd](a)
    sys.stdout.flush()
    os._exit(0)  # skip interpreter teardown (the personhog fake raises on close)


if __name__ == "__main__":
    main()
