from __future__ import annotations

import argparse
import fcntl
import json
import os
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from .util import parse_utc, require_id, require_number, require_text, utc_now


class GpuPoolError(ValueError):
    pass


class GpuPool:
    def __init__(self, lab_dir: Path, *, now: Callable[[], str] = utc_now):
        self.lab_dir = Path(lab_dir).resolve()
        self.runtime_dir = self.lab_dir / "runtime"
        self.inventory_path = self.runtime_dir / "gpus.json"
        self.events_path = self.runtime_dir / "gpu_events.jsonl"
        self.lock_path = self.runtime_dir / "gpus.lock"
        self.now = now
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self._locked():
            if not self.inventory_path.exists():
                self._write({"schema_version": 1, "updated_at": self.now(), "benches": {}})

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self.lock_path.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.inventory_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise GpuPoolError(f"cannot read GPU inventory: {error}") from error
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 1
            or not isinstance(value.get("benches"), dict)
        ):
            raise GpuPoolError("GPU inventory must use schema_version 1")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        value["updated_at"] = self.now()
        temporary = self.inventory_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, self.inventory_path)

    def _event(self, event: str, **fields: Any) -> None:
        row = {"schema_version": 1, "timestamp": self.now(), "event": event, **fields}
        with self.events_path.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    @staticmethod
    def _bench(value: dict[str, Any], bench_id: str) -> dict[str, Any]:
        bench = value["benches"].get(bench_id)
        if not isinstance(bench, dict):
            raise GpuPoolError(f"unknown GPU bench: {bench_id}")
        return bench

    def _with_staleness(self, bench: dict[str, Any]) -> dict[str, Any]:
        row = json.loads(json.dumps(bench))
        claim = row.get("claim")
        if isinstance(claim, dict):
            claim["stale"] = parse_utc(claim["lease_until_utc"]) < parse_utc(
                self.now(), "current time"
            )
        return row

    @staticmethod
    def _lease_until(bench: dict[str, Any], timestamp: str, lease_seconds: int):
        requested = parse_utc(timestamp) + timedelta(seconds=lease_seconds)
        lifecycle_deadline = parse_utc(
            bench["lifecycle"]["deadline_utc"], "lifecycle.deadline_utc"
        )
        return min(requested, lifecycle_deadline)

    def snapshot(self, *, include_retired: bool = False) -> dict[str, Any]:
        with self._locked():
            value = self._read()
        benches = [
            self._with_staleness(bench)
            for _, bench in sorted(value["benches"].items())
            if include_retired or bench.get("status") != "retired"
        ]
        return {
            "schema_version": 1,
            "inventory_path": str(self.inventory_path),
            "updated_at": value.get("updated_at"),
            "benches": benches,
        }

    @staticmethod
    def _validated_spec(spec: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(spec, dict):
            raise GpuPoolError("bench specification must be an object")
        try:
            bench_id = require_id("id", spec.get("id"))
            provider = require_text("provider", spec.get("provider"))
            accelerator = require_text("accelerator", spec.get("accelerator"))
            hourly_cost_usd = require_number(
                "hourly_cost_usd", spec.get("hourly_cost_usd"), nonnegative=True
            )
        except ValueError as error:
            raise GpuPoolError(str(error)) from error
        resource = spec.get("resource")
        if not isinstance(resource, dict) or not resource:
            raise GpuPoolError("resource must describe the provider allocation")
        if not all(isinstance(key, str) and isinstance(value, str) and value for key, value in resource.items()):
            raise GpuPoolError("resource fields must be nonempty strings")
        contents = spec.get("contents")
        if not isinstance(contents, dict):
            raise GpuPoolError("contents must describe what is resident on the bench")
        lifecycle = spec.get("lifecycle")
        if not isinstance(lifecycle, dict):
            raise GpuPoolError("lifecycle must name the director-owned watchdog and deadline")
        watchdog = lifecycle.get("watchdog")
        if not isinstance(watchdog, dict) or not watchdog.get("unit"):
            raise GpuPoolError("lifecycle.watchdog.unit is required")
        try:
            parse_utc(lifecycle.get("deadline_utc"), "lifecycle.deadline_utc")
        except ValueError as error:
            raise GpuPoolError(str(error)) from error
        return {
            "id": bench_id,
            "provider": provider,
            "accelerator": accelerator,
            "resource": resource,
            "contents": contents,
            "lifecycle": lifecycle,
            "hourly_cost_usd": hourly_cost_usd,
        }

    def register(self, spec: dict[str, Any]) -> dict[str, Any]:
        normalized = self._validated_spec(spec)
        with self._locked():
            value = self._read()
            if normalized["id"] in value["benches"]:
                raise GpuPoolError(f"GPU bench already exists: {normalized['id']}")
            timestamp = self.now()
            bench = {
                **normalized,
                "status": "available",
                "claim": None,
                "drain_after_release": False,
                "registered_at": timestamp,
                "updated_at": timestamp,
                "idle_since": timestamp,
            }
            value["benches"][bench["id"]] = bench
            self._write(value)
            self._event("bench_registered", bench_id=bench["id"])
            return self._with_staleness(bench)

    def claim(
        self,
        project: str,
        *,
        bench_id: str | None = None,
        accelerator: str | None = None,
        model: str | None = None,
        lease_seconds: int = 3600,
    ) -> dict[str, Any]:
        try:
            project = require_id("project", project)
        except ValueError as error:
            raise GpuPoolError(str(error)) from error
        if lease_seconds <= 0:
            raise GpuPoolError("lease_seconds must be positive")
        with self._locked():
            value = self._read()
            existing = next(
                (
                    bench
                    for bench in value["benches"].values()
                    if isinstance(bench.get("claim"), dict)
                    and bench["claim"].get("project") == project
                ),
                None,
            )
            if existing is not None:
                return self._with_staleness(existing)
            candidates = []
            for bench in value["benches"].values():
                if bench.get("status") != "available":
                    continue
                if parse_utc(bench["lifecycle"]["deadline_utc"]) <= parse_utc(
                    self.now(), "current time"
                ):
                    continue
                if bench_id is not None and bench.get("id") != bench_id:
                    continue
                if accelerator is not None and bench.get("accelerator") != accelerator:
                    continue
                if model is not None and bench.get("contents", {}).get("model") != model:
                    continue
                candidates.append(bench)
            if not candidates:
                raise GpuPoolError("no available GPU bench matches this project")
            bench = sorted(candidates, key=lambda row: (row.get("idle_since", ""), row["id"]))[0]
            timestamp = self.now()
            lease_until = self._lease_until(bench, timestamp, lease_seconds)
            bench["status"] = "claimed"
            bench["claim"] = {
                "project": project,
                "claimed_at": timestamp,
                "heartbeat_at": timestamp,
                "lease_seconds": lease_seconds,
                "lease_until_utc": lease_until.isoformat().replace("+00:00", "Z"),
            }
            bench["idle_since"] = None
            bench["updated_at"] = timestamp
            self._write(value)
            self._event("bench_claimed", bench_id=bench["id"], project=project)
            return self._with_staleness(bench)

    def _claimed(self, value: dict[str, Any], project: str) -> dict[str, Any]:
        for bench in value["benches"].values():
            claim = bench.get("claim")
            if isinstance(claim, dict) and claim.get("project") == project:
                return bench
        raise GpuPoolError(f"project does not own a GPU bench: {project}")

    def heartbeat(self, project: str) -> dict[str, Any]:
        with self._locked():
            value = self._read()
            bench = self._claimed(value, project)
            timestamp = self.now()
            seconds = int(bench["claim"].get("lease_seconds", 3600))
            lease_until = self._lease_until(bench, timestamp, seconds)
            if lease_until <= parse_utc(timestamp):
                raise GpuPoolError("GPU bench lifecycle deadline has passed")
            bench["claim"]["heartbeat_at"] = timestamp
            bench["claim"]["lease_until_utc"] = lease_until.isoformat().replace(
                "+00:00", "Z"
            )
            bench["updated_at"] = timestamp
            self._write(value)
            self._event("claim_heartbeat", bench_id=bench["id"], project=project)
            return self._with_staleness(bench)

    def update(self, project: str, contents: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(contents, dict):
            raise GpuPoolError("contents update must be an object")
        with self._locked():
            value = self._read()
            bench = self._claimed(value, project)
            bench["contents"].update(contents)
            bench["updated_at"] = self.now()
            self._write(value)
            self._event("bench_updated", bench_id=bench["id"], project=project)
            return self._with_staleness(bench)

    def release(
        self,
        project: str,
        *,
        contents: dict[str, Any] | None = None,
        condition: str = "ready",
    ) -> dict[str, Any]:
        if condition not in {"ready", "maintenance"}:
            raise GpuPoolError("condition must be ready or maintenance")
        if contents is not None and not isinstance(contents, dict):
            raise GpuPoolError("contents update must be an object")
        with self._locked():
            value = self._read()
            bench = self._claimed(value, project)
            if contents:
                bench["contents"].update(contents)
            timestamp = self.now()
            lifecycle_deadline_passed = parse_utc(
                bench["lifecycle"]["deadline_utc"], "lifecycle.deadline_utc"
            ) <= parse_utc(timestamp, "current time")
            if bench.get("drain_after_release") or lifecycle_deadline_passed:
                bench["status"] = "draining"
            else:
                bench["status"] = "available" if condition == "ready" else "maintenance"
            bench["claim"] = None
            bench["idle_since"] = timestamp if bench["status"] == "available" else None
            bench["updated_at"] = timestamp
            self._write(value)
            self._event(
                "bench_released",
                bench_id=bench["id"],
                project=project,
                condition=condition,
                resulting_status=bench["status"],
                lifecycle_deadline_passed=lifecycle_deadline_passed,
            )
            return self._with_staleness(bench)

    def drain(self, bench_id: str) -> dict[str, Any]:
        with self._locked():
            value = self._read()
            bench = self._bench(value, bench_id)
            if bench["status"] == "retired":
                raise GpuPoolError("retired GPU bench cannot be drained")
            if bench["status"] == "claimed":
                bench["drain_after_release"] = True
            else:
                bench["status"] = "draining"
                bench["idle_since"] = None
            bench["updated_at"] = self.now()
            self._write(value)
            self._event("bench_drain_requested", bench_id=bench_id)
            return self._with_staleness(bench)

    def reclaim(self, bench_id: str, *, reason: str) -> dict[str, Any]:
        try:
            reason = require_text("reason", reason)
        except ValueError as error:
            raise GpuPoolError(str(error)) from error
        with self._locked():
            value = self._read()
            bench = self._bench(value, bench_id)
            if bench.get("status") != "claimed":
                raise GpuPoolError("only a claimed GPU bench can be reclaimed")
            previous_project = bench["claim"].get("project")
            bench["claim"] = None
            bench["status"] = "maintenance"
            bench["idle_since"] = None
            bench["updated_at"] = self.now()
            self._write(value)
            self._event(
                "bench_reclaimed",
                bench_id=bench_id,
                previous_project=previous_project,
                reason=reason,
            )
            return self._with_staleness(bench)

    def ready(
        self, bench_id: str, *, contents: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if contents is not None and not isinstance(contents, dict):
            raise GpuPoolError("contents update must be an object")
        with self._locked():
            value = self._read()
            bench = self._bench(value, bench_id)
            if bench.get("status") in {"claimed", "retired"}:
                raise GpuPoolError("claimed or retired GPU bench cannot be made ready")
            timestamp = self.now()
            if parse_utc(
                bench["lifecycle"]["deadline_utc"], "lifecycle.deadline_utc"
            ) <= parse_utc(timestamp, "current time"):
                raise GpuPoolError("GPU bench lifecycle deadline has passed")
            if contents:
                bench["contents"].update(contents)
            bench["status"] = "available"
            bench["drain_after_release"] = False
            bench["idle_since"] = timestamp
            bench["updated_at"] = timestamp
            self._write(value)
            self._event("bench_ready", bench_id=bench_id)
            return self._with_staleness(bench)

    def retire(self, bench_id: str, *, cleanup_verified: bool) -> dict[str, Any]:
        if not cleanup_verified:
            raise GpuPoolError("retiring a GPU bench requires verified provider cleanup")
        with self._locked():
            value = self._read()
            bench = self._bench(value, bench_id)
            if bench.get("status") == "claimed":
                raise GpuPoolError("claimed GPU bench must be drained and released first")
            bench["status"] = "retired"
            bench["claim"] = None
            bench["idle_since"] = None
            bench["updated_at"] = self.now()
            self._write(value)
            self._event("bench_retired", bench_id=bench_id, cleanup_verified=True)
            return self._with_staleness(bench)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise GpuPoolError(f"cannot read JSON object: {error}") from error
    if not isinstance(value, dict):
        raise GpuPoolError("JSON input must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atomic shared GPU bench inventory")
    parser.add_argument("--lab", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    list_command = commands.add_parser("list")
    list_command.add_argument("--all", action="store_true")
    register = commands.add_parser("register")
    register.add_argument("--spec", type=Path, required=True)
    claim = commands.add_parser("claim")
    claim.add_argument("--project", required=True)
    claim.add_argument("--bench")
    claim.add_argument("--accelerator")
    claim.add_argument("--model")
    claim.add_argument("--lease-seconds", type=int, default=3600)
    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("--project", required=True)
    update = commands.add_parser("update")
    update.add_argument("--project", required=True)
    update.add_argument("--contents", type=Path, required=True)
    release = commands.add_parser("release")
    release.add_argument("--project", required=True)
    release.add_argument("--contents", type=Path)
    release.add_argument("--condition", choices=("ready", "maintenance"), default="ready")
    drain = commands.add_parser("drain")
    drain.add_argument("--bench", required=True)
    reclaim = commands.add_parser("reclaim")
    reclaim.add_argument("--bench", required=True)
    reclaim.add_argument("--reason", required=True)
    ready = commands.add_parser("ready")
    ready.add_argument("--bench", required=True)
    ready.add_argument("--contents", type=Path)
    retire = commands.add_parser("retire")
    retire.add_argument("--bench", required=True)
    retire.add_argument("--cleanup-verified", action="store_true")

    args = parser.parse_args(argv)
    pool = GpuPool(args.lab)
    try:
        if args.command == "list":
            result = pool.snapshot(include_retired=args.all)
        elif args.command == "register":
            result = pool.register(_load_object(args.spec))
        elif args.command == "claim":
            result = pool.claim(
                args.project,
                bench_id=args.bench,
                accelerator=args.accelerator,
                model=args.model,
                lease_seconds=args.lease_seconds,
            )
        elif args.command == "heartbeat":
            result = pool.heartbeat(args.project)
        elif args.command == "update":
            result = pool.update(args.project, _load_object(args.contents))
        elif args.command == "release":
            contents = _load_object(args.contents) if args.contents else None
            result = pool.release(args.project, contents=contents, condition=args.condition)
        elif args.command == "drain":
            result = pool.drain(args.bench)
        elif args.command == "reclaim":
            result = pool.reclaim(args.bench, reason=args.reason)
        elif args.command == "ready":
            contents = _load_object(args.contents) if args.contents else None
            result = pool.ready(args.bench, contents=contents)
        else:
            result = pool.retire(args.bench, cleanup_verified=args.cleanup_verified)
    except GpuPoolError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
