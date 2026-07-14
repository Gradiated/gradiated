from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from .util import ValidationError, content_hash, micros_to_usd, require_id, require_sha256, require_text, usd_to_micros


class LabError(RuntimeError):
    pass


class LeaseBusy(LabError):
    pass


class Fenced(LabError):
    pass


class BudgetExceeded(LabError):
    pass


class CleanupAdapter(Protocol):
    def delete(self, resource_id: str) -> None: ...

    def exists(self, resource_id: str) -> bool: ...

    def inventory_contains(self, resource_id: str) -> bool: ...


class LabDatabase:
    """SQLite safety kernel. Scientific conclusions never live here."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=30000")
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS coordinator_leases (
                program_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS budgets (
                campaign_id TEXT PRIMARY KEY,
                authorized_micros INTEGER NOT NULL,
                settled_micros INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL REFERENCES budgets(campaign_id),
                program_id TEXT NOT NULL,
                owner TEXT NOT NULL,
                lease_epoch INTEGER NOT NULL,
                amount_micros INTEGER NOT NULL,
                cleanup_micros INTEGER NOT NULL,
                admission_sha256 TEXT NOT NULL,
                expires_at REAL NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('active','settled','released')),
                actual_micros INTEGER,
                settlement_evidence_sha256 TEXT
            );
            CREATE TABLE IF NOT EXISTS allocations (
                allocation_id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL REFERENCES reservations(reservation_id),
                program_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_resource_id TEXT NOT NULL,
                setup_key TEXT NOT NULL,
                owner TEXT NOT NULL,
                lease_epoch INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('active','retained','cleanup_required','cleaned')),
                absolute_deadline REAL NOT NULL,
                heartbeat_at REAL NOT NULL,
                resident_manifest_sha256 TEXT,
                teardown_verified INTEGER NOT NULL DEFAULT 0,
                cleanup_evidence_sha256 TEXT,
                UNIQUE(provider, provider_resource_id)
            );
            CREATE INDEX IF NOT EXISTS reservations_campaign_state
                ON reservations(campaign_id, state);
            CREATE INDEX IF NOT EXISTS allocations_cleanup
                ON allocations(state, absolute_deadline);
            CREATE UNIQUE INDEX IF NOT EXISTS one_allocation_per_reservation
                ON allocations(reservation_id);
            """
        )
        reservation_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(reservations)")
        }
        if "actual_micros" not in reservation_columns:
            self.connection.execute("ALTER TABLE reservations ADD COLUMN actual_micros INTEGER")
        if "settlement_evidence_sha256" not in reservation_columns:
            self.connection.execute("ALTER TABLE reservations ADD COLUMN settlement_evidence_sha256 TEXT")
        allocation_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(allocations)")
        }
        if "cleanup_evidence_sha256" not in allocation_columns:
            self.connection.execute("ALTER TABLE allocations ADD COLUMN cleanup_evidence_sha256 TEXT")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except Exception:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    @staticmethod
    def _assert_lease(connection: sqlite3.Connection, program_id: str, owner: str, epoch: int, now: float) -> None:
        row = connection.execute(
            "SELECT owner, epoch, expires_at FROM coordinator_leases WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if row is None or row["owner"] != owner or row["epoch"] != epoch or row["expires_at"] <= now:
            raise Fenced("coordinator lease is absent, expired, or fenced")

    def acquire_coordinator(self, program_id: str, owner: str, *, ttl_seconds: int, now: float) -> dict[str, Any]:
        require_id("program_id", program_id)
        require_id("owner", owner)
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValidationError("ttl_seconds must be a positive integer")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT owner, epoch, expires_at FROM coordinator_leases WHERE program_id = ?",
                (program_id,),
            ).fetchone()
            if row is None:
                epoch = 1
                connection.execute(
                    "INSERT INTO coordinator_leases(program_id, owner, epoch, expires_at) VALUES (?, ?, ?, ?)",
                    (program_id, owner, epoch, now + ttl_seconds),
                )
            elif row["owner"] == owner and row["expires_at"] > now:
                epoch = row["epoch"]
                connection.execute(
                    "UPDATE coordinator_leases SET expires_at = ? WHERE program_id = ?",
                    (now + ttl_seconds, program_id),
                )
            elif row["expires_at"] <= now:
                epoch = row["epoch"] + 1
                connection.execute(
                    "UPDATE coordinator_leases SET owner = ?, epoch = ?, expires_at = ? WHERE program_id = ?",
                    (owner, epoch, now + ttl_seconds, program_id),
                )
            else:
                raise LeaseBusy(f"program {program_id} is leased by {row['owner']}")
        return {"program_id": program_id, "owner": owner, "epoch": epoch, "expires_at": now + ttl_seconds}

    def heartbeat_coordinator(self, program_id: str, owner: str, epoch: int, *, ttl_seconds: int, now: float) -> None:
        with self._transaction() as connection:
            self._assert_lease(connection, program_id, owner, epoch, now)
            connection.execute(
                "UPDATE coordinator_leases SET expires_at = ? WHERE program_id = ?",
                (now + ttl_seconds, program_id),
            )

    def relinquish_coordinator(self, program_id: str, owner: str, *, now: float) -> dict[str, Any]:
        """End an explicitly stopped lease after proving provider state is clean."""
        require_id("program_id", program_id)
        require_id("owner", owner)
        with self._transaction() as connection:
            lease = connection.execute(
                "SELECT * FROM coordinator_leases WHERE program_id = ?",
                (program_id,),
            ).fetchone()
            if lease is None:
                return {"program_id": program_id, "released": False, "reason": "lease_absent"}
            if lease["owner"] != owner:
                raise Fenced("only the current coordinator owner can relinquish its lease")
            active_reservations = connection.execute(
                "SELECT COUNT(*) AS count FROM reservations WHERE program_id = ? AND state = 'active'",
                (program_id,),
            ).fetchone()["count"]
            unclean_allocations = connection.execute(
                "SELECT COUNT(*) AS count FROM allocations WHERE program_id = ? AND state != 'cleaned'",
                (program_id,),
            ).fetchone()["count"]
            if active_reservations or unclean_allocations:
                raise LabError(
                    "cannot relinquish a lease while active reservations or unclean allocations remain"
                )
            connection.execute(
                "UPDATE coordinator_leases SET expires_at = ? WHERE program_id = ? AND owner = ? AND epoch = ?",
                (now, program_id, owner, lease["epoch"]),
            )
            return {
                "program_id": program_id,
                "owner": owner,
                "epoch": lease["epoch"],
                "released": True,
                "released_at": now,
            }

    def ensure_budget(
        self,
        campaign_id: str,
        *,
        authorized_usd: Any,
        already_spent_usd: Any = 0,
    ) -> None:
        require_id("campaign_id", campaign_id)
        authorized = usd_to_micros("authorized_usd", authorized_usd, positive=True)
        already_spent = usd_to_micros("already_spent_usd", already_spent_usd)
        if already_spent > authorized:
            raise ValidationError("already-spent cost cannot exceed budget authority")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT authorized_micros, settled_micros FROM budgets WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO budgets(campaign_id, authorized_micros, settled_micros) VALUES (?, ?, ?)",
                    (campaign_id, authorized, already_spent),
                )
            elif authorized != row["authorized_micros"] or already_spent != row["settled_micros"]:
                raise LabError("budget authority cannot change implicitly")

    def amend_budget(self, campaign_id: str, *, authorized_usd: Any) -> None:
        require_id("campaign_id", campaign_id)
        authorized = usd_to_micros("authorized_usd", authorized_usd, positive=True)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT authorized_micros FROM budgets WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if row is None:
                raise LabError("campaign budget does not exist")
            if authorized < row["authorized_micros"]:
                raise LabError("budget authority amendments cannot reduce the campaign ceiling")
            if authorized == row["authorized_micros"]:
                return
            connection.execute(
                "UPDATE budgets SET authorized_micros = ? WHERE campaign_id = ?",
                (authorized, campaign_id),
            )

    def release_expired_unused_reservation(
        self,
        reservation_id: str,
        *,
        owner: str,
        epoch: int,
        now: float,
    ) -> bool:
        require_id("reservation_id", reservation_id)
        with self._transaction() as connection:
            reservation = connection.execute(
                "SELECT * FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if reservation is None or reservation["state"] != "active":
                return False
            self._assert_lease(connection, reservation["program_id"], owner, epoch, now)
            if reservation["expires_at"] > now:
                raise LabError("an unexpired reservation cannot be released by the recovery sweep")
            allocation_count = connection.execute(
                "SELECT COUNT(*) AS count FROM allocations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()["count"]
            if allocation_count:
                raise LabError("a reservation with allocation history requires cleanup and settlement")
            connection.execute(
                "UPDATE reservations SET state = 'released' WHERE reservation_id = ?",
                (reservation_id,),
            )
            return True

    def reserve(
        self,
        *,
        reservation_id: str,
        campaign_id: str,
        program_id: str,
        owner: str,
        epoch: int,
        amount_usd: Any,
        cleanup_reserve_usd: Any,
        expires_at: float,
        admission_sha256: str,
        now: float,
    ) -> dict[str, Any]:
        for name, value in (("reservation_id", reservation_id), ("campaign_id", campaign_id), ("program_id", program_id), ("owner", owner)):
            require_id(name, value)
        require_sha256("admission_sha256", admission_sha256)
        amount = usd_to_micros("amount_usd", amount_usd, positive=True)
        cleanup = usd_to_micros("cleanup_reserve_usd", cleanup_reserve_usd, positive=True)
        if cleanup > amount:
            raise ValidationError("cleanup reserve cannot exceed the reservation")
        if expires_at <= now:
            raise ValidationError("reservation expiry must be in the future")
        with self._transaction() as connection:
            self._assert_lease(connection, program_id, owner, epoch, now)
            existing = connection.execute(
                "SELECT * FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if existing is not None:
                expected = {
                    "campaign_id": campaign_id,
                    "program_id": program_id,
                    "amount_micros": amount,
                    "cleanup_micros": cleanup,
                    "admission_sha256": admission_sha256,
                    "expires_at": expires_at,
                }
                changed = sorted(name for name, value in expected.items() if existing[name] != value)
                if existing["state"] != "active" or changed:
                    detail = ", ".join(changed) if changed else existing["state"]
                    raise LabError(f"reservation identity was reused after changing: {detail}")
                if existing["owner"] != owner or existing["lease_epoch"] != epoch:
                    connection.execute(
                        "UPDATE reservations SET owner = ?, lease_epoch = ? WHERE reservation_id = ?",
                        (owner, epoch, reservation_id),
                    )
                return {
                    "reservation_id": reservation_id,
                    "reserved_usd": micros_to_usd(amount),
                    "expires_at": expires_at,
                }
            budget = connection.execute(
                "SELECT authorized_micros, settled_micros FROM budgets WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if budget is None:
                raise LabError("campaign budget does not exist")
            reserved = connection.execute(
                "SELECT COALESCE(SUM(amount_micros), 0) AS total FROM reservations WHERE campaign_id = ? AND state = 'active'",
                (campaign_id,),
            ).fetchone()["total"]
            available = budget["authorized_micros"] - budget["settled_micros"] - reserved
            if amount > available:
                raise BudgetExceeded("reservation exceeds remaining campaign authority")
            connection.execute(
                """
                INSERT INTO reservations(
                    reservation_id, campaign_id, program_id, owner, lease_epoch,
                    amount_micros, cleanup_micros, admission_sha256, expires_at, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (reservation_id, campaign_id, program_id, owner, epoch, amount, cleanup, admission_sha256, expires_at),
            )
        return {"reservation_id": reservation_id, "reserved_usd": micros_to_usd(amount), "expires_at": expires_at}

    def register_allocation(
        self,
        *,
        allocation_id: str,
        reservation_id: str,
        provider: str,
        provider_resource_id: str,
        setup_key: str,
        owner: str,
        epoch: int,
        absolute_deadline: float,
        now: float,
    ) -> None:
        for name, value in (("allocation_id", allocation_id), ("reservation_id", reservation_id), ("provider", provider), ("provider_resource_id", provider_resource_id), ("owner", owner)):
            require_id(name, value)
        require_text("setup_key", setup_key)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM allocations WHERE allocation_id = ?",
                (allocation_id,),
            ).fetchone()
            if existing is not None:
                expected = {
                    "reservation_id": reservation_id,
                    "provider": provider,
                    "provider_resource_id": provider_resource_id,
                    "setup_key": setup_key,
                    "owner": owner,
                    "lease_epoch": epoch,
                    "absolute_deadline": absolute_deadline,
                }
                if any(existing[name] != value for name, value in expected.items()):
                    raise LabError("allocation identity was reused with different content")
                return
            attached = connection.execute(
                "SELECT allocation_id FROM allocations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if attached is not None:
                raise LabError(
                    f"reservation {reservation_id} already funds allocation {attached['allocation_id']}"
                )
            reservation = connection.execute(
                "SELECT program_id, owner, lease_epoch, expires_at, state FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if reservation is None or reservation["state"] != "active":
                raise LabError("allocation requires an active reservation")
            self._assert_lease(connection, reservation["program_id"], owner, epoch, now)
            if reservation["owner"] != owner or reservation["lease_epoch"] != epoch:
                raise Fenced("reservation belongs to another coordinator epoch")
            if not now < absolute_deadline <= reservation["expires_at"]:
                raise ValidationError("allocation deadline must fit inside its reservation")
            connection.execute(
                """
                INSERT INTO allocations(
                    allocation_id, reservation_id, program_id, provider, provider_resource_id,
                    setup_key, owner, lease_epoch, state, absolute_deadline, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    allocation_id,
                    reservation_id,
                    reservation["program_id"],
                    provider,
                    provider_resource_id,
                    setup_key,
                    owner,
                    epoch,
                    absolute_deadline,
                    now,
                ),
            )

    def _allocation_owned(self, connection: sqlite3.Connection, allocation_id: str, owner: str, epoch: int) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM allocations WHERE allocation_id = ?", (allocation_id,)).fetchone()
        if row is None:
            raise LabError("allocation does not exist")
        if row["owner"] != owner or row["lease_epoch"] != epoch:
            raise Fenced("allocation is fenced by another owner or epoch")
        return row

    def heartbeat_allocation(self, allocation_id: str, *, owner: str, epoch: int, now: float) -> None:
        with self._transaction() as connection:
            row = self._allocation_owned(connection, allocation_id, owner, epoch)
            self._assert_lease(connection, row["program_id"], owner, epoch, now)
            connection.execute("UPDATE allocations SET heartbeat_at = ? WHERE allocation_id = ?", (now, allocation_id))

    def mark_retained(
        self,
        allocation_id: str,
        *,
        owner: str,
        epoch: int,
        resident_manifest_sha256: str,
        now: float,
    ) -> None:
        require_sha256("resident_manifest_sha256", resident_manifest_sha256)
        with self._transaction() as connection:
            row = self._allocation_owned(connection, allocation_id, owner, epoch)
            self._assert_lease(connection, row["program_id"], owner, epoch, now)
            connection.execute(
                "UPDATE allocations SET state = 'retained', resident_manifest_sha256 = ?, heartbeat_at = ? WHERE allocation_id = ?",
                (resident_manifest_sha256, now, allocation_id),
            )

    def adopt_allocation(self, allocation_id: str, *, owner: str, epoch: int, now: float) -> None:
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM allocations WHERE allocation_id = ?", (allocation_id,)).fetchone()
            if row is None or row["state"] not in {"active", "retained"}:
                raise LabError("only an active or retained allocation can be adopted")
            if row["absolute_deadline"] <= now:
                raise LabError("an expired allocation requires cleanup, not adoption")
            self._assert_lease(connection, row["program_id"], owner, epoch, now)
            connection.execute(
                "UPDATE allocations SET owner = ?, lease_epoch = ?, heartbeat_at = ? WHERE allocation_id = ?",
                (owner, epoch, now, allocation_id),
            )

    def request_cleanup(self, allocation_id: str, *, owner: str, epoch: int, now: float) -> None:
        with self._transaction() as connection:
            self._allocation_owned(connection, allocation_id, owner, epoch)
            connection.execute(
                "UPDATE allocations SET state = 'cleanup_required', heartbeat_at = ? WHERE allocation_id = ?",
                (now, allocation_id),
            )

    def due_cleanup(self, *, now: float) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT a.*
            FROM allocations a
            LEFT JOIN coordinator_leases l ON l.program_id = a.program_id
            WHERE a.state != 'cleaned'
              AND (
                a.state = 'cleanup_required'
                OR a.absolute_deadline <= ?
                OR l.program_id IS NULL
                OR l.owner != a.owner
                OR l.epoch != a.lease_epoch
                OR l.expires_at <= ?
              )
            ORDER BY a.absolute_deadline, a.allocation_id
            """,
            (now, now),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_cleanup_verified(
        self,
        allocation_id: str,
        *,
        owner: str,
        epoch: int,
        now: float,
        get_absent: bool,
        inventory_absent: bool,
        verification_sha256: str,
    ) -> None:
        require_sha256("cleanup verification_sha256", verification_sha256)
        if not get_absent or not inventory_absent:
            raise LabError("cleanup requires both direct lookup and inventory absence")
        with self._transaction() as connection:
            self._allocation_owned(connection, allocation_id, owner, epoch)
            connection.execute(
                "UPDATE allocations SET state = 'cleaned', teardown_verified = 1, cleanup_evidence_sha256 = ?, heartbeat_at = ? WHERE allocation_id = ?",
                (verification_sha256, now, allocation_id),
            )

    def sweep_due(self, adapters: dict[str, CleanupAdapter], *, now: float) -> list[dict[str, Any]]:
        results = []
        for allocation in self.due_cleanup(now=now):
            adapter = adapters.get(allocation["provider"])
            if adapter is None:
                results.append({"allocation_id": allocation["allocation_id"], "status": "missing_adapter"})
                continue
            try:
                adapter.delete(allocation["provider_resource_id"])
                get_absent = not adapter.exists(allocation["provider_resource_id"])
                inventory_absent = not adapter.inventory_contains(allocation["provider_resource_id"])
                verification_sha256 = content_hash(
                    {
                        "allocation_id": allocation["allocation_id"],
                        "provider": allocation["provider"],
                        "provider_resource_id": allocation["provider_resource_id"],
                        "checked_at": now,
                        "get_absent": get_absent,
                        "inventory_absent": inventory_absent,
                    }
                )
                self.mark_cleanup_verified(
                    allocation["allocation_id"],
                    owner=allocation["owner"],
                    epoch=allocation["lease_epoch"],
                    now=now,
                    get_absent=get_absent,
                    inventory_absent=inventory_absent,
                    verification_sha256=verification_sha256,
                )
                results.append({"allocation_id": allocation["allocation_id"], "status": "cleaned"})
            except Exception as error:
                results.append({"allocation_id": allocation["allocation_id"], "status": "failed", "error": repr(error)})
        return results

    def settle_session(
        self,
        reservation_id: str,
        *,
        actual_cost_usd: Any,
        cost_evidence_sha256: str,
    ) -> None:
        require_sha256("cost_evidence_sha256", cost_evidence_sha256)
        actual = usd_to_micros("actual_cost_usd", actual_cost_usd)
        with self._transaction() as connection:
            reservation = connection.execute("SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,)).fetchone()
            if reservation is None or reservation["state"] != "active":
                raise LabError("reservation is absent or not active")
            if actual > reservation["amount_micros"]:
                raise BudgetExceeded("settled session cost exceeds its reservation")
            unclean = connection.execute(
                "SELECT COUNT(*) AS count FROM allocations WHERE reservation_id = ? AND state != 'cleaned'",
                (reservation_id,),
            ).fetchone()["count"]
            if unclean:
                raise LabError("session cannot settle before every allocation is cleaned")
            connection.execute(
                "UPDATE budgets SET settled_micros = settled_micros + ? WHERE campaign_id = ?",
                (actual, reservation["campaign_id"]),
            )
            connection.execute(
                "UPDATE reservations SET state = 'settled', actual_micros = ?, settlement_evidence_sha256 = ? WHERE reservation_id = ?",
                (actual, cost_evidence_sha256, reservation_id),
            )

    def snapshot(self) -> dict[str, Any]:
        leases = [dict(row) for row in self.connection.execute("SELECT * FROM coordinator_leases ORDER BY program_id")]
        budgets = []
        for row in self.connection.execute("SELECT * FROM budgets ORDER BY campaign_id"):
            reserved = self.connection.execute(
                "SELECT COALESCE(SUM(amount_micros), 0) AS total FROM reservations WHERE campaign_id = ? AND state = 'active'",
                (row["campaign_id"],),
            ).fetchone()["total"]
            budgets.append({
                "campaign_id": row["campaign_id"],
                "authorized_usd": micros_to_usd(row["authorized_micros"]),
                "settled_usd": micros_to_usd(row["settled_micros"]),
                "reserved_usd": micros_to_usd(reserved),
                "available_usd": micros_to_usd(row["authorized_micros"] - row["settled_micros"] - reserved),
            })
        reservations = []
        for row in self.connection.execute("SELECT * FROM reservations ORDER BY reservation_id"):
            item = dict(row)
            item["amount_usd"] = micros_to_usd(item.pop("amount_micros"))
            item["cleanup_reserve_usd"] = micros_to_usd(item.pop("cleanup_micros"))
            actual_micros = item.pop("actual_micros")
            item["actual_cost_usd"] = None if actual_micros is None else micros_to_usd(actual_micros)
            reservations.append(item)
        allocations = [dict(row) for row in self.connection.execute("SELECT * FROM allocations ORDER BY allocation_id")]
        return {"leases": leases, "budgets": budgets, "reservations": reservations, "allocations": allocations}
