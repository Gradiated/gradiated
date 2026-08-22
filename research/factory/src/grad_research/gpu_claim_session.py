from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from .gpu_pool import GpuPool


class GpuClaimSessionError(RuntimeError):
    pass


class GpuClaimSession:
    """Own one exact GPU claim, its heartbeats, and its generation-fenced release.

    Recoverable integration errors should be caught and repaired inside the
    context. By default, leaving the context is the lifecycle boundary and the
    claim is released to maintenance unless ``release`` was called explicitly.
    A repair-capable owner may set ``release_on_exception=False`` and catch the
    exception outside the context; its heartbeat remains live until that owner
    explicitly repairs and releases the session.
    """

    def __init__(
        self,
        pool: GpuPool,
        project: str,
        bench_id: str,
        *,
        lease_seconds: int = 3600,
        heartbeat_seconds: float = 60.0,
        release_condition: str = "maintenance",
        release_contents: Mapping[str, Any] | None = None,
        release_on_exception: bool = True,
        expected_claimed_at: str | None = None,
    ):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if heartbeat_seconds >= lease_seconds:
            raise ValueError("heartbeat_seconds must be shorter than lease_seconds")
        if release_condition not in {"ready", "maintenance"}:
            raise ValueError("release_condition must be ready or maintenance")
        if expected_claimed_at is not None and not expected_claimed_at:
            raise ValueError("expected_claimed_at must be a nonempty string")

        self.pool = pool
        self.project = project
        self.bench_id = bench_id
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.release_condition = release_condition
        self.release_contents = (
            dict(release_contents) if release_contents is not None else None
        )
        self.release_on_exception = release_on_exception
        self.expected_claimed_at = expected_claimed_at

        self.claimed_at: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._heartbeat_error: BaseException | None = None
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def __enter__(self) -> GpuClaimSession:
        if self.expected_claimed_at is None:
            bench = self.pool.claim(
                self.project,
                bench_id=self.bench_id,
                lease_seconds=self.lease_seconds,
            )
        else:
            bench = self.pool.show(self.bench_id)
        if bench.get("id") != self.bench_id:
            raise GpuClaimSessionError(
                f"project {self.project} owns {bench.get('id')}, not {self.bench_id}"
            )
        claim = bench.get("claim")
        if not isinstance(claim, dict) or claim.get("project") != self.project:
            raise GpuClaimSessionError("GPU pool returned an invalid claim")
        claimed_at = claim.get("claimed_at")
        if not isinstance(claimed_at, str) or not claimed_at:
            raise GpuClaimSessionError("GPU claim is missing claimed_at")
        if (
            self.expected_claimed_at is not None
            and claimed_at != self.expected_claimed_at
        ):
            raise GpuClaimSessionError(
                "GPU claim generation does not match expected_claimed_at"
            )

        self.claimed_at = claimed_at
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"gpu-claim-heartbeat-{self.project}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                bench = self.pool.heartbeat(
                    self.project,
                    bench_id=self.bench_id,
                    expected_claimed_at=self.claimed_at,
                )
                claim = bench.get("claim")
                if (
                    not isinstance(claim, dict)
                    or claim.get("claimed_at") != self.claimed_at
                ):
                    raise GpuClaimSessionError(
                        "GPU claim generation changed during heartbeat"
                    )
            except BaseException as error:
                self._heartbeat_error = error
                self._stop.set()
                return

    def check(self) -> None:
        if self._heartbeat_error is not None:
            raise GpuClaimSessionError("GPU claim heartbeat failed") from (
                self._heartbeat_error
            )

    def release(
        self,
        *,
        condition: str | None = None,
        contents: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.claimed_at is None:
            raise GpuClaimSessionError("GPU claim session has not started")
        if self._released:
            raise GpuClaimSessionError("GPU claim session is already released")

        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        release_condition = condition or self.release_condition
        release_contents = (
            dict(contents) if contents is not None else self.release_contents
        )
        bench = self.pool.release(
            self.project,
            bench_id=self.bench_id,
            expected_claimed_at=self.claimed_at,
            contents=release_contents,
            condition=release_condition,
        )
        self._released = True
        return bench

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if self._released or self.claimed_at is None:
            return False
        if exc_value is not None and not self.release_on_exception:
            return False
        try:
            self.release()
        except BaseException as release_error:
            if exc_value is None:
                raise
            exc_value.add_note(
                f"GPU claim maintenance release also failed: {release_error!r}"
            )
        return False
