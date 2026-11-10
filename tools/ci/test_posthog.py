import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from posthog import REQUIRED_WORKFLOWS, build_event, build_step_events, collect_events, github_get, github_jobs, github_runs, revision_runs, main, send_events

ROOT = Path(__file__).resolve().parents[2]
RUN = {
    "id": 123, "run_attempt": 1, "workflow_id": 45, "name": "Product tests", "path": ".github/workflows/tests.yml",
    "run_number": 6, "event": "pull_request", "status": "completed", "conclusion": "success", "head_sha": "a" * 40,
    "head_branch": "test", "html_url": "https://github.com/owner/repo/actions/runs/123",
    "created_at": "2026-10-13T10:00:00Z", "run_started_at": "2026-10-13T10:00:00Z",
    "updated_at": "2026-10-13T10:05:10Z", "pull_requests": [{"number": 8}],
    "actor": {"email": "private@example.com"}, "head_commit": {"message": "private commit text"},
}
JOB = {
    "id": 1, "run_attempt": 1, "name": "Unit tests", "conclusion": "success", "labels": ["ubuntu-latest"],
    "created_at": "2026-10-13T10:00:01Z", "started_at": "2026-10-13T10:00:10Z", "completed_at": "2026-10-13T10:05:00Z",
    "steps": [{"number": 1, "name": "Test", "status": "completed", "conclusion": "success", "started_at": "2026-10-13T10:01:00Z", "completed_at": "2026-10-13T10:04:00Z", "output": "private output"}],
}


class Response(io.BytesIO):
    status = 200


class EventTest(unittest.TestCase):
    def test_parallel_jobs_do_not_inflate_workflow_wall_time(self):
        event = build_event("owner/repo", RUN, [JOB, {**JOB, "id": 2, "name": "Integration tests"}])
        properties = event["properties"]
        self.assertEqual(properties["duration_seconds"], 310)
        self.assertEqual(properties["execution_span_seconds"], 290)
        self.assertEqual(properties["job_duration_sum_seconds"], 580)
        self.assertEqual(properties["initial_queue_seconds"], 10)
        self.assertEqual(properties["job_queue_sum_seconds"], 18)
        self.assertEqual(properties["slowest_step_seconds"], 180)
        self.assertEqual(properties["pr_numbers"], [8])

    def test_skipped_jobs_have_zero_work_and_no_impact_on_execution_span(self):
        skipped = {**JOB, "id": 2, "name": "Skipped", "conclusion": "skipped", "started_at": "1970-01-01T00:00:00Z"}
        properties = build_event("owner/repo", RUN, [JOB, skipped])["properties"]
        self.assertEqual(properties["skipped_job_count"], 1)
        self.assertEqual(properties["job_duration_sum_seconds"], 290)
        self.assertEqual(properties["jobs"][1]["duration_seconds"], 0)
        self.assertEqual(properties["initial_queue_seconds"], 10)

    def test_failed_and_cancelled_workflows_retain_their_outcomes(self):
        for conclusion in ("failure", "cancelled", "timed_out"):
            properties = build_event("owner/repo", {**RUN, "conclusion": conclusion}, [{**JOB, "conclusion": conclusion}])["properties"]
            self.assertEqual(properties["conclusion"], conclusion)
            self.assertEqual(properties["jobs"][0]["conclusion"], conclusion)

    def test_retry_identity_is_stable_and_rerun_is_a_separate_event(self):
        first = build_event("owner/repo", RUN, [JOB])
        self.assertEqual(first["uuid"], build_event("owner/repo", RUN, [JOB])["uuid"])
        rerun = {**RUN, "run_attempt": 2, "run_started_at": "2026-10-13T10:04:00Z"}
        second = build_event("owner/repo", rerun, [JOB, {**JOB, "run_attempt": 2}])
        self.assertNotEqual(first["uuid"], second["uuid"])
        self.assertEqual(second["properties"]["job_count"], 1)
        self.assertEqual(second["properties"]["duration_seconds"], 70)

    def test_identity_is_fixed_and_raw_payload_fields_are_not_transmitted(self):
        event = build_event("owner/repo", RUN, [JOB])
        self.assertEqual(event["distinct_id"], "github-ci")
        self.assertFalse(event["properties"]["$process_person_profile"])
        self.assertNotIn("private", json.dumps(event))
        self.assertEqual(event["timestamp"], RUN["updated_at"])

    def test_unstarted_cancelled_job_has_unknown_duration(self):
        properties = build_event("owner/repo", RUN, [{**JOB, "started_at": None, "completed_at": None}])["properties"]
        self.assertIsNone(properties["jobs"][0]["duration_seconds"])
        self.assertIsNone(properties["initial_queue_seconds"])

    def test_unstarted_cancelled_jobs_do_not_count_as_executed_work(self):
        job = {**JOB, "conclusion": "cancelled", "started_at": None}
        properties = build_event("owner/repo", {**RUN, "conclusion": "cancelled"}, [job])["properties"]
        self.assertEqual(properties["executed_job_count"], 0)
        self.assertEqual(properties["substantive_job_count"], 0)
        self.assertEqual(properties["cancelled_job_count"], 1)
        self.assertIsNone(properties["slowest_job_name"])
        self.assertEqual(properties["job_duration_sum_seconds"], 0)

    def test_gate_only_runs_can_be_excluded_from_heavy_work_insights(self):
        jobs = [{**JOB, "name": "Relevant changes"}, {**JOB, "id": 2, "name": "Product tests passed"}]
        self.assertEqual(build_event("owner/repo", RUN, jobs)["properties"]["substantive_job_count"], 0)


class TransportTest(unittest.TestCase):
    def test_github_server_and_rate_limit_errors_retry(self):
        for status in (429, 503):
            calls, sleeps = [], []
            def open_url(request, timeout):
                calls.append(request.full_url)
                if len(calls) == 1:
                    raise HTTPError(request.full_url, status, "Transient", {}, None)
                return Response(b'{"jobs": []}')
            self.assertEqual(github_get("repos/owner/repo/actions/runs", "test-token", open_url, sleeps.append), {"jobs": []})
            self.assertEqual(len(calls), 2)
            self.assertEqual(sleeps, [1])

    def test_github_permanent_error_is_not_retried(self):
        calls, sleeps = [], []
        def open_url(request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        with self.assertRaises(HTTPError):
            github_get("repos/owner/repo/actions/runs", "test-token", open_url, sleeps.append)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_github_network_errors_have_bounded_retries(self):
        for error in (URLError("network"), TimeoutError("timeout"), ConnectionResetError("reset")):
            calls, sleeps = [], []
            def open_url(request, timeout):
                calls.append(request)
                raise error
            with self.assertRaises(type(error)):
                github_get("repos/owner/repo/actions/runs", "test-token", open_url, sleeps.append)
            self.assertEqual(len(calls), 3)
            self.assertEqual(sleeps, [1, 2])

    def test_github_persistent_server_error_has_bounded_retries(self):
        calls, sleeps = [], []
        def open_url(request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 503, "Unavailable", {}, None)
        with self.assertRaises(HTTPError):
            github_get("repos/owner/repo/actions/runs", "test-token", open_url, sleeps.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [1, 2])

    def test_job_lookup_paginates_the_exact_run_attempt(self):
        requests = []
        def open_url(request, timeout):
            requests.append(request.full_url)
            return Response(json.dumps({"jobs": [JOB], "total_count": 2}).encode())
        jobs = github_jobs("owner/repo", 123, 2, "test-token", open_url)
        self.assertEqual(len(jobs), 2)
        self.assertIn("/runs/123/attempts/2/jobs?", requests[0])
        self.assertTrue(requests[1].endswith("page=2"))

    def test_transient_delivery_retries_identical_payload(self):
        payloads = []
        def open_url(request, timeout):
            payloads.append(request.data)
            if len(payloads) == 1:
                raise HTTPError(request.full_url, 503, "Unavailable", {}, None)
            return Response(b'{}')
        sleep = []
        send_events([build_event("owner/repo", RUN, [JOB])], "test-key", open_url, sleep.append)
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(sleep, [1])

    def test_permanent_rejection_is_not_retried(self):
        calls = []
        def open_url(request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 400, "Bad request", {}, None)
        with self.assertRaises(RuntimeError):
            send_events([build_event("owner/repo", RUN, [JOB])], "test-key", open_url)
        self.assertEqual(len(calls), 1)

    def test_network_failure_has_bounded_retries(self):
        calls = []
        def open_url(request, timeout):
            calls.append(request)
            raise URLError("network failure")
        with self.assertRaises(RuntimeError):
            send_events([build_event("owner/repo", RUN, [JOB])], "test-key", open_url, lambda _: None)
        self.assertEqual(len(calls), 3)

    def run_main(self, run, key="test-key", event_name="workflow_run", inputs=None):
        with tempfile.TemporaryDirectory() as temporary:
            event = Path(temporary) / "event.json"
            event.write_text(json.dumps({"action": "completed", "workflow_run": run, "inputs": inputs or {}}))
            events = [build_event("owner/repo", RUN, [JOB])]
            with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": event_name, "GITHUB_REPOSITORY": "owner/repo", "GH_TOKEN": "test-token", "POSTHOG_KEY": key}), patch("posthog.collect_events", return_value=events) as collect, patch("posthog.send_events") as send, patch("sys.stdout", new_callable=io.StringIO):
                main()
                return collect, send

    def test_single_anchor_collects_revision_and_sends_one_batch(self):
        collect, send = self.run_main(RUN)
        collect.assert_called_once_with("owner/repo", RUN["head_sha"], "test", "test-token")
        self.assertEqual(send.call_count, 1)

    def test_other_workflow_completions_and_non_pr_runs_do_not_collect(self):
        for run in ({**RUN, "name": "Terraform"}, *[{**RUN, "event": source} for source in ("push", "workflow_run", "workflow_dispatch")]):
            collect, send = self.run_main(run)
            self.assertFalse(collect.called)
            self.assertFalse(send.called)

    def test_manual_dispatch_can_collect_isolated_workflow_reruns(self):
        collect, send = self.run_main({}, event_name="workflow_dispatch", inputs={"head_sha": RUN["head_sha"]})
        collect.assert_called_once_with("owner/repo", RUN["head_sha"], None, "test-token")
        self.assertTrue(send.called)

    def test_dispatch_rejects_invalid_revision(self):
        with self.assertRaises(RuntimeError):
            self.run_main({}, event_name="workflow_dispatch", inputs={"head_sha": "main"})

    def test_missing_project_key_is_visible(self):
        with self.assertRaises(RuntimeError):
            self.run_main(RUN, key="")


class WorkflowTest(unittest.TestCase):
    def test_only_product_completion_triggers_the_collector(self):
        observer = (ROOT / ".github/workflows/ci-analytics.yml").read_text()
        self.assertIn("workflows: [Product tests]", observer)
        self.assertNotIn("      - Terraform", observer)

    def test_unfiltered_pr_workflows_are_required_for_collection(self):
        observer = (ROOT / ".github/workflows/ci-analytics.yml").read_text()
        required = set()
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            text = path.read_text()
            pr = re.search(r"^  pull_request:\n(.*)", text, re.M)
            if pr and not pr.group(1).startswith("    "):
                required.add(".github/workflows/" + path.name)
        self.assertEqual(required, REQUIRED_WORKFLOWS)

    def test_privileged_collector_checks_out_default_branch_code(self):
        observer = (ROOT / ".github/workflows/ci-analytics.yml").read_text()
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", observer)
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", observer)
        self.assertNotIn("download-artifact", observer)
        self.assertIn("pull_request", observer)


def ci_runs():
    return [{**RUN, "id": index, "workflow_id": index, "path": path}
            for index, path in enumerate(sorted(REQUIRED_WORKFLOWS), 1)]


class StepEventTest(unittest.TestCase):
    def test_step_event_has_original_timestamp_status_and_dimensions(self):
        event = build_step_events("owner/repo", RUN, [JOB], [8])[0]
        self.assertEqual(event["event"], "ci_workflow_step_completed")
        self.assertEqual(event["timestamp"], "2026-10-13T10:04:00Z")
        self.assertEqual(event["properties"]["duration_seconds"], 180)
        for key, value in (("workflow_name", "Product tests"), ("job_name", "Unit tests"), ("step_name", "Test"), ("status", "completed"), ("conclusion", "success"), ("workflow_conclusion", "success")):
            self.assertEqual(event["properties"][key], value)
        self.assertNotIn("private", json.dumps(event))

    def test_unstarted_cancelled_step_has_unknown_duration_with_labelled_fallback(self):
        job = {**JOB, "steps": [{**JOB["steps"][0], "conclusion": "cancelled", "started_at": None, "completed_at": None}]}
        event = build_step_events("owner/repo", RUN, [job], [8])[0]
        self.assertIsNone(event["properties"]["duration_seconds"])
        self.assertTrue(event["properties"]["timestamp_is_fallback"])
        self.assertIsNone(event["properties"]["completed_at"])
        self.assertEqual(event["timestamp"], JOB["completed_at"])

    def test_fast_successful_and_skipped_steps_are_not_sent_as_step_events(self):
        step = JOB["steps"][0]
        fast = {**step, "number": 2, "completed_at": "2026-10-13T10:01:04Z"}
        skipped = {**step, "number": 3, "conclusion": "skipped"}
        fast_failure = {**fast, "number": 4, "conclusion": "failure"}
        events = build_step_events("owner/repo", RUN, [{**JOB, "steps": [step, fast, skipped, fast_failure]}], [8])
        self.assertEqual([event["properties"]["step_number"] for event in events], [1, 4])
        steps = build_event("owner/repo", RUN, [{**JOB, "steps": [step, fast, skipped, fast_failure]}])["properties"]["jobs"][0]["steps"]
        self.assertEqual([step["number"] for step in steps], [1, 2, 3, 4])

    def test_step_identity_is_unique_per_job_and_attempt_and_stable_on_retry(self):
        first = build_step_events("owner/repo", RUN, [JOB], [8])[0]
        self.assertEqual(first["uuid"], build_step_events("owner/repo", RUN, [JOB], [8])[0]["uuid"])
        other_job = build_step_events("owner/repo", RUN, [{**JOB, "id": 2}], [8])[0]
        rerun = build_step_events("owner/repo", {**RUN, "run_attempt": 2}, [{**JOB, "run_attempt": 2}], [8])[0]
        self.assertEqual(len({first["uuid"], other_job["uuid"], rerun["uuid"]}), 3)


class CollectionTest(unittest.TestCase):
    def collect(self, snapshots, get=None, jobs=None, wait_seconds=8):
        now = [0]
        calls = []
        snapshots = iter(snapshots)
        last = [None]
        def get_runs(*args):
            last[0] = next(snapshots, last[0])
            return last[0]
        def get_jobs(repository, run_id, attempt, token):
            calls.append((run_id, attempt))
            return [{**JOB, "run_attempt": attempt}]
        def sleep(seconds):
            now[0] += seconds
        def get_metadata(path, token):
            if "/attempts/" in path:
                run_id = int(path.split("/runs/", 1)[1].split("/", 1)[0])
                attempt = int(path.rsplit("/", 1)[1])
                return {**next(run for run in ci_runs() if run["id"] == run_id), "run_attempt": attempt, "conclusion": "failure"}
            return [{"number": 8}]
        with patch("sys.stdout", new_callable=io.StringIO):
            events = collect_events("owner/repo", RUN["head_sha"], "test", "test-token", get_runs=get_runs, get_jobs=jobs or get_jobs, get=get or get_metadata, sleep=sleep, clock=lambda: now[0], wait_seconds=wait_seconds, poll_seconds=1)
        return events, calls, now[0]

    def test_all_workflows_and_steps_are_reported_after_two_settled_snapshots(self):
        runs = ci_runs()
        events, calls, elapsed = self.collect([runs])
        self.assertEqual(len(events), 2 * len(runs))
        self.assertEqual(len(calls), len(runs))
        self.assertEqual(elapsed, 1)
        self.assertEqual(sum(event["event"] == "ci_workflow_completed" for event in events), len(runs))

    def test_running_workflow_blocks_collection_until_completed(self):
        runs = ci_runs()
        active = [{**runs[0], "status": "in_progress", "conclusion": None}, *runs[1:]]
        events, _, elapsed = self.collect([active, runs, runs, runs])
        self.assertEqual(len(events), 2 * len(runs))
        self.assertEqual(elapsed, 2)

    def test_failures_and_cancellations_are_terminal_and_reported(self):
        runs = ci_runs()
        runs[0] = {**runs[0], "conclusion": "failure"}
        runs[1] = {**runs[1], "conclusion": "cancelled"}
        events, _, _ = self.collect([runs])
        outcomes = {event["properties"]["conclusion"] for event in events if event["event"] == "ci_workflow_completed"}
        self.assertTrue({"failure", "cancelled"} <= outcomes)

    def test_missing_required_workflow_times_out_without_partial_collection(self):
        with self.assertRaises(RuntimeError):
            self.collect([ci_runs()[:-1]], wait_seconds=3)

    def test_optional_path_filtered_workflow_does_not_have_to_exist(self):
        events, _, _ = self.collect([ci_runs()])
        self.assertTrue(events)

    def test_late_optional_workflow_is_waited_for_and_included(self):
        runs = ci_runs()
        extra = {**RUN, "id": 200, "workflow_id": 200, "path": ".github/workflows/storybook.yml", "name": "Storybook"}
        active = [*runs, {**extra, "status": "queued", "conclusion": None}]
        done = [*runs, extra]
        events, _, elapsed = self.collect([runs, active, done, done, done])
        self.assertEqual(sum(event["event"] == "ci_workflow_completed" for event in events), len(done))
        self.assertEqual(elapsed, 3)

    def test_new_rerun_during_metadata_fetch_requires_another_settled_round(self):
        runs = ci_runs()
        rerun = [{**runs[0], "run_attempt": 2}, *runs[1:]]
        active = [{**rerun[0], "status": "in_progress", "conclusion": None}, *runs[1:]]
        events, calls, _ = self.collect([runs, runs, active, rerun, rerun, rerun])
        workflows = [event for event in events if event["event"] == "ci_workflow_completed" and event["properties"]["run_id"] == runs[0]["id"]]
        self.assertEqual({event["properties"]["run_attempt"] for event in workflows}, {1, 2})
        self.assertEqual(len(calls), 2 * len(runs) + 1)

    def test_missing_pr_associations_have_one_lookup_for_the_batch(self):
        runs = [{**run, "pull_requests": []} for run in ci_runs()]
        lookup = []
        def get(path, token):
            lookup.append(path)
            return [{"number": 8}]
        events, _, _ = self.collect([runs], get=get)
        self.assertEqual(len(lookup), 1)
        self.assertTrue(all(event["properties"]["pr_numbers"] == [8] for event in events))

    def test_revision_lookup_paginates_without_status_filter(self):
        requests = []
        def get(path, token):
            requests.append(path)
            return {"workflow_runs": [RUN], "total_count": 2}
        runs = github_runs("owner/repo", RUN["head_sha"], "branch/name", "test-token", get)
        self.assertEqual(len(runs), 2)
        self.assertIn("branch=branch%2Fname", requests[0])
        self.assertNotIn("status=", requests[0])
        self.assertIn("page=2", requests[1])

    def test_other_commits_and_non_pr_runs_do_not_enter_the_round(self):
        rows = [RUN, {**RUN, "id": 124, "head_sha": "b" * 40}, {**RUN, "id": 125, "event": "workflow_run"}]
        self.assertEqual(revision_runs(rows, RUN["head_sha"]), [RUN])

    def test_repeated_workflow_runs_on_one_revision_are_all_preserved(self):
        rows = [RUN, {**RUN, "id": 124}]
        self.assertEqual(len(revision_runs(rows, RUN["head_sha"])), 2)

    def test_prior_failed_attempts_are_reported_with_the_successful_rerun(self):
        runs = ci_runs()
        runs[0] = {**runs[0], "run_attempt": 2}
        events, _, _ = self.collect([runs])
        workflow_events = [event for event in events if event["event"] == "ci_workflow_completed"]
        self.assertEqual(len(workflow_events), len(runs) + 1)
        self.assertIn("failure", {event["properties"]["conclusion"] for event in workflow_events})
        self.assertEqual(len({event["uuid"] for event in events}), len(events))


if __name__ == "__main__":
    unittest.main()
