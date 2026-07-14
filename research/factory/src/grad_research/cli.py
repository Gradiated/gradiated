from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .admission import validate_paid_run
from .artifacts import ArtifactStore, package_run_directory
from .demo import run_demo
from .director import ResearchDirector
from .events import EventStore
from .legacy import import_legacy_campaign, replay_legacy_ledger
from .labd import LabDatabase
from .operations import resume_program
from .portfolio import select_portfolio
from .telemetry import build_telemetry_contract


def _write(value: object, path: Path | None = None) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded)
    else:
        print(encoded, end="")


def _now(value: str | None) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.now(timezone.utc)


def _lab_path(root: Path, explicit: Path | None) -> Path:
    return explicit or root / "lab.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(prog="grad-research")
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="run the deterministic two-cycle synthetic campaign")
    demo.add_argument("--root", type=Path, required=True)

    replay = commands.add_parser("replay-legacy", help="normalize a legacy JSONL ledger without promoting claims")
    replay.add_argument("--root", type=Path, required=True)
    replay.add_argument("--program", required=True)
    replay.add_argument("--ledger", type=Path, required=True)
    replay.add_argument("--status", type=Path)
    replay.add_argument("--decision", type=Path)

    project = commands.add_parser("project", help="project a program event stream into one state view")
    project.add_argument("--root", type=Path, required=True)
    project.add_argument("--program", required=True)
    project.add_argument("--output", type=Path)

    context = commands.add_parser("context", help="print the generated coordinator context")
    context.add_argument("--root", type=Path, required=True)
    context.add_argument("--program", required=True)

    resume = commands.add_parser(
        "resume", help="acquire the coordinator fence and emit recovery actions plus runnable work packets"
    )
    resume.add_argument("--root", type=Path, required=True)
    resume.add_argument("--program", required=True)
    resume.add_argument("--owner", required=True, help="stable name for this Codex session")
    resume.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    resume.add_argument("--ttl-seconds", type=int, default=900)
    resume.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")
    resume.add_argument("--deep-artifact-audit", action="store_true")

    budget = commands.add_parser("authorize-budget", help="record immutable campaign spend authority")
    budget.add_argument("--root", type=Path, required=True)
    budget.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    budget.add_argument("--campaign", required=True)
    budget.add_argument("--authorized-usd", type=float, required=True)
    budget.add_argument("--already-spent-usd", type=float, default=0)

    amend_budget = commands.add_parser("amend-budget", help="explicitly increase campaign spend authority")
    amend_budget.add_argument("--root", type=Path, required=True)
    amend_budget.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    amend_budget.add_argument("--campaign", required=True)
    amend_budget.add_argument("--authorized-usd", type=float, required=True)

    admit = commands.add_parser("admit-paid-run", help="fence, reserve, and durably admit an exact paid run")
    admit.add_argument("--root", type=Path, required=True)
    admit.add_argument("--program", required=True)
    admit.add_argument("--spec", type=Path, required=True)
    admit.add_argument("--owner", required=True)
    admit.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    admit.add_argument("--ttl-seconds", type=int, default=900)
    admit.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")

    allocation = commands.add_parser(
        "register-allocation", help="bind the one provider resource created from an admitted reservation"
    )
    allocation.add_argument("--root", type=Path, required=True)
    allocation.add_argument("--program", required=True)
    allocation.add_argument("--owner", required=True)
    allocation.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    allocation.add_argument("--allocation-id", required=True)
    allocation.add_argument("--reservation-id", required=True)
    allocation.add_argument("--provider", required=True)
    allocation.add_argument("--provider-resource-id", required=True)
    allocation.add_argument("--setup-key", required=True)
    allocation.add_argument("--absolute-deadline", required=True, help="RFC3339 timestamp")
    allocation.add_argument("--ttl-seconds", type=int, default=900)
    allocation.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")

    retain = commands.add_parser("retain-allocation", help="record the exact resident setup kept for the next arm")
    retain.add_argument("--root", type=Path, required=True)
    retain.add_argument("--program", required=True)
    retain.add_argument("--owner", required=True)
    retain.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    retain.add_argument("--allocation-id", required=True)
    retain.add_argument("--resident-manifest", required=True)
    retain.add_argument("--ttl-seconds", type=int, default=900)
    retain.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")

    cleanup = commands.add_parser("request-cleanup", help="mark an allocation for provider-adapter deletion")
    cleanup.add_argument("--root", type=Path, required=True)
    cleanup.add_argument("--program", required=True)
    cleanup.add_argument("--owner", required=True)
    cleanup.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    cleanup.add_argument("--allocation-id", required=True)
    cleanup.add_argument("--ttl-seconds", type=int, default=900)
    cleanup.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")

    cleanup_verified = commands.add_parser(
        "mark-cleanup-verified",
        help="close a tracked allocation after the provider adapter proves two-view absence",
    )
    cleanup_verified.add_argument("--root", type=Path, required=True)
    cleanup_verified.add_argument("--program", required=True)
    cleanup_verified.add_argument("--owner", required=True)
    cleanup_verified.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    cleanup_verified.add_argument("--allocation-id", required=True)
    cleanup_verified.add_argument("--verification-sha256", required=True)
    cleanup_verified.add_argument("--get-absent", action="store_true")
    cleanup_verified.add_argument("--inventory-absent", action="store_true")
    cleanup_verified.add_argument("--ttl-seconds", type=int, default=900)
    cleanup_verified.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")

    settle = commands.add_parser("settle-session", help="settle a cleaned reservation from stored cost evidence")
    settle.add_argument("--root", type=Path, required=True)
    settle.add_argument("--program", required=True)
    settle.add_argument("--lab", type=Path, help="defaults to ROOT/lab.sqlite3")
    settle.add_argument("--reservation-id", required=True)
    settle.add_argument("--actual-cost-usd", type=float, required=True)
    settle.add_argument("--cost-evidence-sha256", required=True)

    admission = commands.add_parser("validate-paid-run", help="fail-closed validation before provider mutation")
    admission.add_argument("spec", type=Path)
    admission.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")

    telemetry = commands.add_parser(
        "telemetry-template", help="emit a complete low-overhead or deep diagnostic telemetry contract"
    )
    telemetry.add_argument("--mode", choices=("scoreable", "diagnostic_only"), default="scoreable")
    telemetry.add_argument("--output", type=Path)

    pack = commands.add_parser(
        "pack-run", help="hash, validate, and content-address all artifacts declared by a paid run"
    )
    pack.add_argument("--root", type=Path, required=True)
    pack.add_argument("--program", required=True)
    pack.add_argument("--spec", type=Path, required=True)
    pack.add_argument("--run-dir", type=Path, required=True)
    pack.add_argument(
        "--failure-class",
        help="package a compact non-scientific failure bundle using RUN_DIR/failure.json",
    )

    verify = commands.add_parser("verify-artifacts", help="verify a content-addressed run bundle")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--program", required=True)
    verify.add_argument("--manifest", required=True, help="bundle manifest SHA-256")
    verify.add_argument("--deep", action="store_true", help="rehash every raw object")

    store_artifact = commands.add_parser(
        "store-artifact", help="content-address one observation, analysis, or simulation artifact"
    )
    store_artifact.add_argument("--root", type=Path, required=True)
    store_artifact.add_argument("--program", required=True)
    store_artifact.add_argument("file", type=Path)

    record = commands.add_parser(
        "record", help="idempotently append a baseline, observation, scout batch, or result"
    )
    record.add_argument("--root", type=Path, required=True)
    record.add_argument("--program", required=True)
    record.add_argument("--kind", choices=("baseline", "baseline_refresh", "observation", "scouts", "local_run", "result"), required=True)
    record.add_argument("--input", type=Path, required=True)
    record.add_argument("--reason", help="required only for baseline_refresh")

    select_cycle = commands.add_parser(
        "select-cycle", help="select the diverse portfolio for one recorded discovery cycle"
    )
    select_cycle.add_argument("--root", type=Path, required=True)
    select_cycle.add_argument("--program", required=True)
    select_cycle.add_argument("--cycle", type=int, required=True)
    select_cycle.add_argument("--max-size", type=int, default=5)

    select = commands.add_parser("select-scouts", help="rank scouts while preserving portfolio diversity")
    select.add_argument("input", type=Path)
    select.add_argument("--output", type=Path)
    select.add_argument("--max-size", type=int, default=5)

    bootstrap = commands.add_parser("bootstrap-glm47", help="resume the completed Sol GLM campaign in the factory")
    bootstrap.add_argument("--root", type=Path, required=True)
    bootstrap.add_argument("--campaign-dir", type=Path, required=True)
    bootstrap.add_argument("--program", default="glm-4.7-flash")

    args = parser.parse_args()
    if args.command == "demo":
        result = run_demo(args.root)
        _write(result)
    elif args.command == "replay-legacy":
        store = EventStore(args.root, args.program)
        if bool(args.status) != bool(args.decision):
            parser.error("--status and --decision must be supplied together")
        summary = (
            import_legacy_campaign(args.ledger, args.status, args.decision, store)
            if args.status
            else replay_legacy_ledger(args.ledger, store)
        )
        store.write_state()
        _write({"summary": summary, "state": store.project()})
    elif args.command == "project":
        store = EventStore(args.root, args.program)
        _write(store.project(), args.output)
    elif args.command == "context":
        from .context import build_coordinator_context

        print(build_coordinator_context(EventStore(args.root, args.program).project()), end="")
    elif args.command == "resume":
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            _write(
                resume_program(
                    ResearchDirector(args.root, args.program),
                    lab,
                    owner=args.owner,
                    ttl_seconds=args.ttl_seconds,
                    now=_now(args.now),
                    deep_artifact_audit=args.deep_artifact_audit,
                )
            )
        finally:
            lab.close()
    elif args.command == "authorize-budget":
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            lab.ensure_budget(
                args.campaign,
                authorized_usd=args.authorized_usd,
                already_spent_usd=args.already_spent_usd,
            )
            _write(lab.snapshot())
        finally:
            lab.close()
    elif args.command == "amend-budget":
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            lab.amend_budget(args.campaign, authorized_usd=args.authorized_usd)
            _write(lab.snapshot())
        finally:
            lab.close()
    elif args.command == "admit-paid-run":
        now = _now(args.now)
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            lease = lab.acquire_coordinator(
                args.program, args.owner, ttl_seconds=args.ttl_seconds, now=now.timestamp()
            )
            director = ResearchDirector(args.root, args.program)
            admitted = director.admit_paid_run(
                json.loads(args.spec.read_text()), lab=lab, owner=args.owner, epoch=lease["epoch"], now=now
            )
            _write({"admission": admitted, "lease": lease, "state_path": str(director.write_state())})
        finally:
            lab.close()
    elif args.command == "register-allocation":
        now = _now(args.now)
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            lease = lab.acquire_coordinator(
                args.program, args.owner, ttl_seconds=args.ttl_seconds, now=now.timestamp()
            )
            lab.register_allocation(
                allocation_id=args.allocation_id,
                reservation_id=args.reservation_id,
                provider=args.provider,
                provider_resource_id=args.provider_resource_id,
                setup_key=args.setup_key,
                owner=args.owner,
                epoch=lease["epoch"],
                absolute_deadline=_now(args.absolute_deadline).timestamp(),
                now=now.timestamp(),
            )
            _write(lab.snapshot())
        finally:
            lab.close()
    elif args.command in {"retain-allocation", "request-cleanup"}:
        now = _now(args.now)
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            lease = lab.acquire_coordinator(
                args.program, args.owner, ttl_seconds=args.ttl_seconds, now=now.timestamp()
            )
            if args.command == "retain-allocation":
                ResearchDirector(args.root, args.program).artifacts.verify_reference(
                    args.resident_manifest, deep=True
                )
                lab.mark_retained(
                    args.allocation_id,
                    owner=args.owner,
                    epoch=lease["epoch"],
                    resident_manifest_sha256=args.resident_manifest,
                    now=now.timestamp(),
                )
            else:
                lab.request_cleanup(
                    args.allocation_id, owner=args.owner, epoch=lease["epoch"], now=now.timestamp()
                )
            _write(lab.snapshot())
        finally:
            lab.close()
    elif args.command == "mark-cleanup-verified":
        now = _now(args.now)
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            lease = lab.acquire_coordinator(
                args.program, args.owner, ttl_seconds=args.ttl_seconds, now=now.timestamp()
            )
            lab.mark_cleanup_verified(
                args.allocation_id,
                owner=args.owner,
                epoch=lease["epoch"],
                now=now.timestamp(),
                get_absent=args.get_absent,
                inventory_absent=args.inventory_absent,
                verification_sha256=args.verification_sha256,
            )
            _write(lab.snapshot())
        finally:
            lab.close()
    elif args.command == "settle-session":
        director = ResearchDirector(args.root, args.program)
        director.artifacts.verify_reference(args.cost_evidence_sha256, deep=True)
        lab = LabDatabase(_lab_path(args.root, args.lab))
        try:
            lab.settle_session(
                args.reservation_id,
                actual_cost_usd=args.actual_cost_usd,
                cost_evidence_sha256=args.cost_evidence_sha256,
            )
            _write(lab.snapshot())
        finally:
            lab.close()
    elif args.command == "validate-paid-run":
        now = (
            datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            if args.now
            else datetime.now(timezone.utc)
        )
        _write(validate_paid_run(json.loads(args.spec.read_text()), now=now))
    elif args.command == "telemetry-template":
        _write(build_telemetry_contract(args.mode), args.output)
    elif args.command == "pack-run":
        spec = json.loads(args.spec.read_text())
        _write(
            package_run_directory(
                ArtifactStore(args.root, args.program),
                spec,
                args.spec,
                args.run_dir,
                failure_class=args.failure_class,
            )
        )
    elif args.command == "verify-artifacts":
        store = ArtifactStore(args.root, args.program)
        _write(store.verify_bundle(args.manifest, deep=args.deep))
    elif args.command == "store-artifact":
        store = ArtifactStore(args.root, args.program)
        sha256 = store.put_file(args.file)
        _write({"sha256": sha256, "object_path": str(store.object_path(sha256))})
    elif args.command == "record":
        value = json.loads(args.input.read_text())
        director = ResearchDirector(args.root, args.program)
        if args.kind == "baseline":
            recorded = director.freeze_baseline(value)
        elif args.kind == "baseline_refresh":
            if not args.reason:
                parser.error("--reason is required for baseline_refresh")
            recorded = director.refresh_baseline(value, reason=args.reason)
        elif args.kind == "observation":
            recorded = director.record_observation(value)
        elif args.kind == "scouts":
            cards = value["scouts"] if isinstance(value, dict) else value
            recorded = director.propose_scouts(cards)
        elif args.kind == "local_run":
            recorded = director.register_local_run(value)
        else:
            recorded = director.complete_run(value)
        _write(
            {
                "recorded": recorded,
                "state_path": str(director.write_state()),
                "context_path": str(director.write_coordinator_context()),
            }
        )
    elif args.command == "select-cycle":
        director = ResearchDirector(args.root, args.program)
        selected = director.select_portfolio(args.cycle, max_size=args.max_size)
        _write(
            {
                "portfolio": selected,
                "state_path": str(director.write_state()),
                "context_path": str(director.write_coordinator_context()),
            }
        )
    elif args.command == "select-scouts":
        value = json.loads(args.input.read_text())
        cards = value["scouts"] if isinstance(value, dict) else value
        _write(select_portfolio(cards, max_size=args.max_size), args.output)
    elif args.command == "bootstrap-glm47":
        from .sol_glm47 import bootstrap_glm47

        _write(bootstrap_glm47(args.root, args.campaign_dir, program_id=args.program))
    return 0
