import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "nebius"))
from observer_dependency_contract import (
    ContractError, INPUT_ARTIFACT_REFS, binding, canonical, fixture,
    package_partial_evidence, validate,
)


class ObserverDependencyContractTests(unittest.TestCase):
  def test_fixture_is_identity_bound_and_union_not_sum(self):
    result = validate(fixture())
    self.assertGreaterEqual(result.coverage, 0.95)
    self.assertEqual(result.covered_ns, 900)
    self.assertLess(result.covered_ns, 920)
    self.assertEqual(canonical(fixture()), canonical(fixture()))


  def test_required_mutations_fail_closed(self):
    cases = {"request_id": ("req", "request_id"), "scheduler_iteration_id": ("iter", "scheduler_iteration_id"), "clock": ("cal", "offset_ns"), "stream": ("k1", "cuda_stream_id"), "graph": ("k1", "graph_node_id"), "interval": ("k1", "end_ns"), "dependency": ("dep", "target_event_id")}
    for name, (event_id, field) in cases.items():
        events = copy.deepcopy(fixture())
        event = next(item for item in events if item["event_id"] == event_id)
        if name == "clock":
            events.remove(event)
        elif name == "dependency":
            event[field] = "foreign"
        elif name == "interval":
            event[field] = event["start_ns"]
        else:
            event[field] = "foreign"
        try:
            validate(events)
        except ContractError:
            pass
        else:
            self.fail(f"mutation accepted: {name}")


  def test_forbidden_scored_fields_fail_closed(self):
    events = fixture()
    events[0]["stdout"] = "never score this"
    try:
        validate(events)
    except ContractError:
        pass
    else:
        self.fail("forbidden field accepted")

  def test_binding_is_versioned_and_content_addressed(self):
    contract = binding()
    self.assertEqual(contract["contract_id"], "observer-dependency-attribution-v1")
    self.assertEqual(contract["input_artifact_refs"], list(INPUT_ARTIFACT_REFS))
    self.assertTrue(contract["fail_closed"])
    self.assertEqual(contract["attribution"], "union_of_non_overlapping_dependency_linked_intervals")

  def test_partial_packaging_retains_exact_raw_rows_and_manifest(self):
    requests = [{"request_id": "req-47022401", "raw": "request-row"}]
    events = fixture()
    manifest = {"raw_requests": "a" * 64, "raw_events": "b" * 64}
    packaged = package_partial_evidence(requests, events, manifest)
    self.assertEqual(packaged["raw_request_rows"], requests)
    self.assertEqual(packaged["raw_event_rows"], events)
    self.assertEqual(packaged["manifest"], manifest)
    with self.assertRaises(ContractError):
      package_partial_evidence(requests, [], manifest)
