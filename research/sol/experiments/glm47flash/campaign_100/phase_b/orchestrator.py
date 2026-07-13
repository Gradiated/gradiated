import hashlib
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path


try:
    from validate_contracts import admit_budget, validate_watchdog
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "specs"))
    from validate_contracts import admit_budget, validate_watchdog


class ControlError(RuntimeError):
    pass


class ProviderNotFound(Exception):
    pass


ACTIVE_STATUSES = {"RUNNING", "CREATED", "RESTARTING"}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _status(item):
    return item.get("status", item.get("desiredStatus"))


class PhaseBOrchestrator:
    def __init__(
        self,
        *,
        provider,
        baseline_path,
        inventory_snapshot_path,
        watchdog_contract_path,
        gate_a_manifest_path,
        expected_gate_a_manifest_sha256,
        watchdog_factory,
    ):
        self.provider = provider
        self.baseline_path = Path(baseline_path)
        self.inventory_snapshot_path = Path(inventory_snapshot_path)
        self.watchdog_contract_path = Path(watchdog_contract_path)
        self.gate_a_manifest_path = Path(gate_a_manifest_path)
        self.expected_gate_a_manifest_sha256 = expected_gate_a_manifest_sha256
        self.watchdog_factory = watchdog_factory

    def _authorize(self, admission, watchdog_contract):
        if os.environ.get("CAMPAIGN_100_COORDINATOR") != "1":
            raise ControlError("only the campaign coordinator may invoke Phase B")
        try:
            baseline_bytes = self.baseline_path.read_bytes()
            baseline = json.loads(baseline_bytes)
            gate = json.loads(self.gate_a_manifest_path.read_text())
            bound_watchdog = json.loads(self.watchdog_contract_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ControlError(f"campaign authorization record is unreadable: {error}") from error
        if baseline.get("signed_off") is not True:
            raise ControlError("campaign baseline is not signed")
        if baseline.get("reconciliation_status") not in {"authoritative", "conservative"}:
            raise ControlError("campaign spend is not reconciled")
        baseline_hash = hashlib.sha256(baseline_bytes).hexdigest()
        if admission.get("baseline_sha256") != baseline_hash:
            raise ControlError("budget admission is not bound to the signed baseline")
        try:
            admission_spend = Decimal(str(admission.get("campaign_additional_spend_usd")))
            baseline_spend = Decimal(str(baseline.get("campaign_additional_spend_usd")))
        except (InvalidOperation, ValueError) as error:
            raise ControlError("campaign spend is not decimal-compatible") from error
        if admission_spend != baseline_spend:
            raise ControlError("budget admission spend differs from baseline")
        if gate.get("gate") != "A" or gate.get("status") != "passed":
            raise ControlError("Gate A is not passed")
        if _sha256(self.gate_a_manifest_path) != self.expected_gate_a_manifest_sha256:
            raise ControlError("Gate A manifest identity changed")
        if bound_watchdog != watchdog_contract:
            raise ControlError("runtime watchdog differs from its bound contract")
        try:
            validate_watchdog(watchdog_contract)
            admit_budget(
                admission,
                baseline_path=self.baseline_path,
                inventory_snapshot_path=self.inventory_snapshot_path,
                watchdog_contract_path=self.watchdog_contract_path,
            )
        except ValueError as error:
            raise ControlError(f"pre-create contract rejected: {error}") from error

    def _assert_no_active_pods(self, inventory):
        active = [item.get("id") for item in inventory if _status(item) in ACTIVE_STATUSES]
        if active:
            raise ControlError(f"active pods prevent Phase B mutation: {active}")

    def run(self, request, admission, watchdog_contract, destination):
        self._authorize(admission, watchdog_contract)
        before = self.provider.inventory()
        self._assert_no_active_pods(before)

        pod_id = None
        watchdog = None
        harvest_status = "not_started"
        harvest_error = None
        delete_status = None
        teardown_verification = "not_created"
        primary_error = None
        try:
            created = self.provider.create(request)
            pod_id = created.get("id")
            if not pod_id:
                raise ControlError("provider create response omitted pod id")
            self.provider.inventory()
            watchdog = self.watchdog_factory(watchdog_contract)
            watchdog.start(pod_id)
            try:
                self.provider.harvest(pod_id, destination)
                harvest_status = "complete"
            except Exception as error:
                harvest_status = "failed"
                harvest_error = repr(error)
        except Exception as error:
            primary_error = error
        finally:
            if pod_id:
                try:
                    self.provider.inventory()
                    delete_status = self.provider.delete(pod_id)
                    self.provider.inventory()
                    try:
                        self.provider.get(pod_id)
                        teardown_verification = "present"
                    except ProviderNotFound:
                        teardown_verification = "http_404"
                except Exception as error:
                    if primary_error is None:
                        primary_error = error
                finally:
                    if watchdog is not None:
                        watchdog.cancel()
        if primary_error is not None:
            raise ControlError(f"Phase B orchestration failed: {primary_error}") from primary_error
        if teardown_verification != "http_404":
            raise ControlError("provider deletion was not verified by a 404")
        return {
            "pod_id": pod_id,
            "harvest_status": harvest_status,
            "harvest_error": harvest_error,
            "delete_http_status": delete_status,
            "teardown_verification": teardown_verification,
        }
