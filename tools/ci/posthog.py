#!/usr/bin/env python3
"""Publish completed PR workflow timings to PostHog without fetching PR code."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

EVENT = "ci_workflow_completed"
DISTINCT_ID = "github-ci"
HOST = "https://us.i.posthog.com"
# Fast successful and skipped steps stay in the workflow event's jobs[].steps[];
# a separate step event is sent only for slow or unsuccessful steps.
MIN_STEP_EVENT_SECONDS = 5
REQUIRED_WORKFLOWS = {
    ".github/workflows/tests.yml",
    ".github/workflows/kubernetes.yml",
    ".github/workflows/terraform.yml",
    ".github/workflows/model-deployment.yml",
    ".github/workflows/wizard-publish.yml",
    ".github/workflows/agent-quality.yml",
    ".github/workflows/dependency-age.yml",
    ".github/workflows/research-lab.yml",
    ".github/workflows/virtual-kubelet.yml",
    ".github/workflows/security.yml",
}


def seconds(start, end):
    if not start or not end:
        return None
    return max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def build_event(repository, run, jobs):
    attempt = run["run_attempt"]
    jobs = [job for job in jobs if job["run_attempt"] == attempt]
    summaries = []
    for job in jobs:
        skipped = job["conclusion"] == "skipped"
        summaries.append({
            "id": job["id"], "name": job["name"], "conclusion": job["conclusion"],
            "runner_labels": job.get("labels", []),
            "queued_at": job.get("created_at"),
            "started_at": job.get("started_at"), "completed_at": job.get("completed_at"),
            "queue_seconds": 0 if skipped else seconds(job.get("created_at"), job.get("started_at")),
            "duration_seconds": 0 if skipped else seconds(job.get("started_at"), job.get("completed_at")),
            "steps": [{
                "name": step["name"], "number": step["number"], "conclusion": step["conclusion"],
                "duration_seconds": 0 if step["conclusion"] == "skipped" else seconds(step.get("started_at"), step.get("completed_at")),
            } for step in job.get("steps", [])],
        })
    executed = [job for job in summaries if job["conclusion"] != "skipped" and job["started_at"]]
    started = [job["started_at"] for job in executed if job["started_at"]]
    completed = [job["completed_at"] for job in executed if job["completed_at"]]
    # updated_at is captured by the completed webhook. Jobs bound execution;
    # the webhook timestamp also includes final workflow bookkeeping.
    end = run["updated_at"]
    start = run.get("run_started_at") or run["created_at"]
    longest_job = max(executed, key=lambda job: job["duration_seconds"] or 0, default=None)
    longest_queue = max(executed, key=lambda job: job["queue_seconds"] or 0, default=None)
    steps = [(job["name"], step) for job in executed for step in job["steps"] if step["conclusion"] != "skipped"]
    longest_step = max(steps, key=lambda item: item[1]["duration_seconds"] or 0, default=None)
    counts = Counter(job["conclusion"] for job in summaries)
    properties = {
        "schema_version": 1, "source": "ci", "$process_person_profile": False,
        "repository": repository, "workflow_name": run["name"], "workflow_id": run["workflow_id"],
        "workflow_path": run["path"], "run_id": run["id"], "run_number": run["run_number"],
        "run_attempt": attempt, "event": run["event"], "status": run["status"], "conclusion": run["conclusion"],
        "head_sha": run["head_sha"], "run_url": run["html_url"],
        "head_branch": run.get("head_branch"),
        "pr_numbers": [pr["number"] for pr in run.get("pull_requests", [])],
        "started_at": start, "completed_at": end,
        "duration_seconds": seconds(start, end),
        "initial_queue_seconds": seconds(start, min(started)) if started else None,
        "execution_span_seconds": seconds(min(started), max(completed)) if started and completed else None,
        "job_duration_sum_seconds": sum(job["duration_seconds"] or 0 for job in executed),
        "job_queue_sum_seconds": sum(job["queue_seconds"] or 0 for job in executed),
        "job_count": len(summaries), "executed_job_count": len(executed),
        "skipped_job_count": counts["skipped"], "failed_job_count": counts["failure"],
        "cancelled_job_count": counts["cancelled"],
        "substantive_job_count": sum(job["name"] != "Relevant changes" and not job["name"].endswith("passed") for job in executed),
        "slowest_job_name": longest_job["name"] if longest_job else None,
        "slowest_job_seconds": longest_job["duration_seconds"] if longest_job else None,
        "longest_queue_job_name": longest_queue["name"] if longest_queue else None,
        "longest_queue_seconds": longest_queue["queue_seconds"] if longest_queue else None,
        "slowest_step_job_name": longest_step[0] if longest_step else None,
        "slowest_step_name": longest_step[1]["name"] if longest_step else None,
        "slowest_step_seconds": longest_step[1]["duration_seconds"] if longest_step else None,
        "jobs": summaries,
    }
    return {
        "event": EVENT, "distinct_id": DISTINCT_ID, "properties": properties, "timestamp": end,
        "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"github-ci:{repository}:{run['id']}:{attempt}")),
    }


def github_get(path, token, open_url=urlopen, sleep=time.sleep):
    request = Request(
        "https://api.github.com/" + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    for attempt in range(3):
        try:
            with open_url(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            if (error.code != 429 and error.code < 500) or attempt == 2:
                raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        sleep(2 ** attempt)


def github_jobs(repository, run_id, attempt, token, open_url=urlopen):
    jobs = []
    for page in range(1, 101):
        data = github_get(
            f"repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}",
            token, open_url,
        )
        jobs.extend(data["jobs"])
        if len(jobs) >= data["total_count"]:
            return jobs
    raise RuntimeError("GitHub job pagination exceeded its bound")


def build_step_events(repository, run, jobs, pr_numbers):
    events = []
    for job in jobs:
        if job["run_attempt"] != run["run_attempt"]:
            continue
        for step in job.get("steps", []):
            skipped = step["conclusion"] == "skipped" or job["conclusion"] == "skipped"
            start, end = step.get("started_at"), step.get("completed_at")
            duration = 0 if skipped else seconds(start, end)
            if step["conclusion"] in ("success", "skipped") and (duration or 0) < MIN_STEP_EVENT_SECONDS:
                continue
            events.append({
                "event": "ci_workflow_step_completed", "distinct_id": DISTINCT_ID,
                "timestamp": end or job.get("completed_at") or run["updated_at"],
                "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"github-ci-step:{repository}:{run['id']}:{run['run_attempt']}:{job['id']}:{step['number']}")),
                "properties": {
                    "schema_version": 1, "source": "ci", "$process_person_profile": False,
                    "repository": repository, "head_sha": run["head_sha"], "head_branch": run.get("head_branch"),
                    "pr_numbers": pr_numbers, "workflow_name": run["name"], "workflow_id": run["workflow_id"],
                    "workflow_path": run["path"], "run_id": run["id"], "run_attempt": run["run_attempt"],
                    "run_number": run["run_number"], "run_url": run["html_url"],
                    "workflow_status": run["status"], "workflow_conclusion": run["conclusion"],
                    "job_id": job["id"], "job_name": job["name"], "job_conclusion": job["conclusion"],
                    "runner_labels": job.get("labels", []), "step_name": step["name"],
                    "step_number": step["number"], "status": step["status"], "conclusion": step["conclusion"],
                    "started_at": start, "completed_at": end,
                    "duration_seconds": duration,
                    "timestamp_is_fallback": end is None,
                },
            })
    return events


def github_runs(repository, head_sha, branch, token, get=github_get):
    runs = []
    for page in range(1, 11):
        query = {"head_sha": head_sha, "event": "pull_request", "per_page": 100, "page": page}
        if branch:
            query["branch"] = branch
        data = get(f"repos/{repository}/actions/runs?" + urlencode(query), token)
        runs.extend(data["workflow_runs"])
        if len(runs) >= data["total_count"]:
            return runs
    raise RuntimeError("GitHub run lookup exceeds the 1,000-result search limit")


def revision_runs(runs, head_sha):
    by_id = {}
    for run in runs:
        if run["event"] != "pull_request" or run["head_sha"] != head_sha:
            continue
        previous = by_id.get(run["id"])
        if previous is None or run["run_attempt"] > previous["run_attempt"]:
            by_id[run["id"]] = run
    return sorted(by_id.values(), key=lambda run: (run["workflow_id"], run["id"]))


def fingerprint(runs):
    return [(run["id"], run["run_attempt"], run["status"], run["conclusion"]) for run in runs]


def complete(runs):
    paths = {run["path"].split("@", 1)[0] for run in runs}
    return REQUIRED_WORKFLOWS <= paths and all(run["status"] == "completed" for run in runs)


def collect_events(repository, head_sha, branch, token, get_runs=github_runs,
                   get_jobs=github_jobs, get=github_get, sleep=time.sleep,
                   clock=time.monotonic, wait_seconds=6000, poll_seconds=30):
    deadline = clock() + wait_seconds
    previous = None
    pr_numbers = None
    while clock() < deadline:
        runs = revision_runs(get_runs(repository, head_sha, branch, token), head_sha)
        current = fingerprint(runs)
        # A second settled snapshot catches late workflow registrations and reruns.
        if complete(runs) and current == previous:
            events = []
            if pr_numbers is None:
                pr_numbers = sorted({pr["number"] for run in runs for pr in run.get("pull_requests", [])})
                if not pr_numbers:
                    prs = get(f"repos/{repository}/commits/{head_sha}/pulls?per_page=100", token)
                    pr_numbers = [pr["number"] for pr in prs]
            for run in runs:
                for attempt in range(1, run["run_attempt"] + 1):
                    metadata = run if attempt == run["run_attempt"] else get(
                        f"repos/{repository}/actions/runs/{run['id']}/attempts/{attempt}", token,
                    )
                    if metadata["status"] != "completed":
                        raise RuntimeError("A prior workflow attempt is not completed")
                    jobs = get_jobs(repository, run["id"], attempt, token)
                    event = build_event(repository, metadata, jobs)
                    event["properties"]["pr_numbers"] = pr_numbers
                    events.append(event)
                    events.extend(build_step_events(repository, metadata, jobs, pr_numbers))
            confirmed = revision_runs(get_runs(repository, head_sha, branch, token), head_sha)
            if complete(confirmed) and fingerprint(confirmed) == current:
                return events
        previous = current
        print(f"Waiting for CI: {sum(run['status'] == 'completed' for run in runs)}/{len(runs)} workflows completed", flush=True)
        sleep(poll_seconds)
    raise RuntimeError("CI did not settle within the 100-minute collection timeout; no partial batch was sent")


def send_events(events, key, open_url=urlopen, sleep=time.sleep):
    data = json.dumps({"api_key": key, "batch": events}, separators=(",", ":")).encode()
    if len(data) >= 20_000_000:
        raise RuntimeError("CI analytics batch exceeds PostHog's 20 MB limit")
    request = Request(HOST + "/batch/", data=data, headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(3):
        try:
            with open_url(request, timeout=15) as response:
                if 200 <= response.status < 300:
                    return
                raise RuntimeError("Unexpected PostHog response")
        except HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise RuntimeError(f"PostHog rejected the batch (HTTP {error.code})") from None
        except (URLError, TimeoutError):
            pass
        if attempt < 2:
            sleep(2 ** attempt)
    raise RuntimeError("PostHog delivery failed after three attempts")


def main():
    payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    run = payload.get("workflow_run", {})
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        head_sha = payload.get("inputs", {}).get("head_sha", "")
        branch = None
    elif payload.get("action") == "completed" and run.get("event") == "pull_request" and run.get("name") == "Product tests":
        head_sha, branch = run["head_sha"], run.get("head_branch")
    else:
        print("No PR CI round to report")
        return
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise RuntimeError("Collection requires a full PR head SHA")
    key = os.environ.get("POSTHOG_KEY", "")
    if not key:
        raise RuntimeError("The CONSOLE_POSTHOG_KEY repository variable is missing")
    events = collect_events(os.environ["GITHUB_REPOSITORY"], head_sha, branch, os.environ["GH_TOKEN"])
    send_events(events, key)
    print(f"Reported {sum(event['event'] == EVENT for event in events)} workflows and {sum(event['event'] == 'ci_workflow_step_completed' for event in events)} steps in one batch")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"CI analytics failed: {error}", file=sys.stderr)
        sys.exit(1)
    except HTTPError as error:
        print(f"CI analytics GitHub lookup failed (HTTP {error.code})", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # Never expose capture payloads, credentials, or HTTP response bodies.
        print(f"CI analytics failed ({type(error).__name__})", file=sys.stderr)
        sys.exit(1)
