#!/usr/bin/env python3
"""Small, dependency-free GitHub CLI helpers for Codex agents."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


INSTALL_URL = "https://github.com/cli/cli/blob/trunk/docs/install_linux.md"


def require_gh() -> None:
    if shutil.which("gh") is None:
        raise SystemExit(f"gh is required; install it from {INSTALL_URL}")


def run(args: list[str], *, capture: bool = False, env: dict[str, str] | None = None) -> str:
    require_gh()
    result = subprocess.run(["gh", *args], text=True, capture_output=capture, env=env)
    if result.returncode:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise SystemExit(result.returncode)
    return result.stdout if capture else ""


def gh_json(args: list[str], *, env: dict[str, str] | None = None) -> object:
    output = run(args + ["--format", "json"], capture=True, env=env)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"expected JSON from gh, received: {output[:200]!r}") from exc


def add_repo(args: argparse.ArgumentParser) -> None:
    args.add_argument("--repo", help="OWNER/REPO; defaults to the current checkout")


def repo_args(namespace: argparse.Namespace) -> list[str]:
    return ["--repo", namespace.repo] if namespace.repo else []


def project_env() -> dict[str, str] | None:
    """Use a separate personal-Project token when configured."""
    token = os.environ.get("GH_PROJECT_TOKEN")
    if not token:
        return None
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    return env


def project_run(args: list[str], *, capture: bool = False) -> str:
    return run(args, capture=capture, env=project_env())


def project_json(args: list[str]) -> object:
    return gh_json(args, env=project_env())


def project_fields(project: str, owner: str) -> list[dict[str, object]]:
    payload = project_json(["project", "field-list", project, "--owner", owner])
    return payload.get("fields", []) if isinstance(payload, dict) else []


def project_items(project: str, owner: str, limit: int = 1000) -> list[dict[str, object]]:
    payload = project_json(["project", "item-list", project, "--owner", owner, "--limit", str(limit)])
    return payload.get("items", []) if isinstance(payload, dict) else []


def issue_url(issue: str, repo: list[str]) -> str:
    payload = gh_json(["issue", "view", issue, *repo, "--json", "url"])
    if not isinstance(payload, dict) or not payload.get("url"):
        raise SystemExit(f"could not resolve issue URL for {issue}")
    return str(payload["url"])


def find_project_item(project: str, owner: str, url: str) -> dict[str, object]:
    for item in project_items(project, owner):
        content = item.get("content") if isinstance(item, dict) else None
        if isinstance(content, dict) and content.get("url") == url:
            return item
    raise SystemExit(f"issue or PR is not in project {project}: {url}")


def set_status(project: str, owner: str, url: str, status: str) -> None:
    item = find_project_item(project, owner, url)
    item_id = item.get("id")
    fields = project_fields(project, owner)
    status_field = next((field for field in fields if str(field.get("name", "")).lower() == "status"), None)
    if not status_field:
        raise SystemExit(f"project {project} has no Status field")
    options = status_field.get("options", [])
    option = next((option for option in options if str(option.get("name", "")).lower() == status.lower()), None)
    if not option:
        available = ", ".join(str(option.get("name")) for option in options)
        raise SystemExit(f"unknown status {status!r}; available: {available}")
    project_run([
        "project", "item-edit", "--id", str(item_id), "--project-id", project,
        "--field-id", str(status_field["id"]),
        "--single-select-option-id", str(option["id"]),
        "--format", "json",
    ])


def issue_create(args: argparse.Namespace) -> None:
    command = ["issue", "create", "--title", args.title, *repo_args(args)]
    if args.body_file:
        command += ["--body-file", args.body_file]
    elif args.body:
        command += ["--body", args.body]
    for label in args.label:
        command += ["--label", label]
    if args.assignee:
        command += ["--assignee", args.assignee]
    url = run(command, capture=True).strip()
    if args.project:
        project_run(["project", "item-add", args.project, "--owner", args.owner, "--url", url, "--format", "json"])
        if args.status:
            set_status(args.project, args.owner, url, args.status)
    print(url)


def issue_start(args: argparse.Namespace) -> None:
    repo = repo_args(args)
    run(["issue", "edit", args.issue, "--add-assignee", "@me", *repo])
    url = issue_url(args.issue, repo)
    if args.project:
        project_run(["project", "item-add", args.project, "--owner", args.owner, "--url", url, "--format", "json"])
        if args.status:
            set_status(args.project, args.owner, url, args.status)
    print(url)


def project_set_status_command(args: argparse.Namespace) -> None:
    url = issue_url(args.issue, repo_args(args)) if args.issue else args.url
    set_status(args.project, args.owner, url, args.status)


def pr_create(args: argparse.Namespace) -> None:
    command = ["pr", "create", "--title", args.title, *repo_args(args)]
    if not args.ready:
        command.append("--draft")
    body = Path(args.body_file).read_text() if args.body_file else (args.body or "")
    if args.issue:
        body = f"Closes #{args.issue}\n\n{body}"
    if body:
        command += ["--body", body]
    print(run(command, capture=True), end="")


def bootstrap_labels(args: argparse.Namespace) -> None:
    labels = (
        ("lane:product", "1D76DB", "Product and user-facing work"),
        ("lane:research", "7057FF", "Technical, market, or product research"),
        ("lane:ops", "FBCA04", "Operations, quality, and maintenance"),
        ("type:bug", "D73A4A", "Reproducible defect"),
        ("type:task", "0E8A16", "Implementation task"),
        ("priority:p0", "B60205", "Immediate"),
        ("priority:p1", "D93F0B", "High"),
        ("priority:p2", "FBCA04", "Normal"),
        ("priority:p3", "0E8A16", "Later"),
    )
    for name, color, description in labels:
        run(["label", "create", name, "--color", color, "--description", description, "--force", *repo_args(args)])


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth-check")
    auth.set_defaults(func=lambda args: run(["auth", "status"]))

    create = sub.add_parser("issue-create")
    create.add_argument("--title", required=True)
    create.add_argument("--body-file")
    create.add_argument("--body")
    create.add_argument("--label", action="append", default=[])
    create.add_argument("--assignee")
    create.add_argument("--project")
    create.add_argument("--owner", default="@me")
    create.add_argument("--status", default="Ready")
    add_repo(create)
    create.set_defaults(func=issue_create)

    listing = sub.add_parser("issue-list")
    listing.add_argument("--state", default="open")
    listing.add_argument("--limit", type=int, default=50)
    listing.add_argument("--label")
    listing.add_argument("--assignee")
    listing.add_argument("--search")
    add_repo(listing)
    listing.set_defaults(func=lambda args: run(["issue", "list", "--state", args.state, "--limit", str(args.limit), *(["--label", args.label] if args.label else []), *(["--assignee", args.assignee] if args.assignee else []), *(["--search", args.search] if args.search else []), *repo_args(args)]))

    start = sub.add_parser("issue-start")
    start.add_argument("issue")
    start.add_argument("--project")
    start.add_argument("--owner", default="@me")
    start.add_argument("--status", default="In Progress")
    add_repo(start)
    start.set_defaults(func=issue_start)

    projects = sub.add_parser("project-list")
    projects.add_argument("--owner", default="@me")
    projects.set_defaults(func=lambda args: project_run(["project", "list", "--owner", args.owner]))

    items = sub.add_parser("project-items")
    items.add_argument("--project", required=True)
    items.add_argument("--owner", default="@me")
    items.set_defaults(func=lambda args: project_run(["project", "item-list", args.project, "--owner", args.owner, "--limit", "1000"]))

    fields = sub.add_parser("project-fields")
    fields.add_argument("--project", required=True)
    fields.add_argument("--owner", default="@me")
    fields.set_defaults(func=lambda args: project_run(["project", "field-list", args.project, "--owner", args.owner]))

    status = sub.add_parser("project-set-status")
    status.add_argument("--project", required=True)
    status.add_argument("--owner", default="@me")
    status.add_argument("--status", required=True)
    status_group = status.add_mutually_exclusive_group(required=True)
    status_group.add_argument("--issue")
    status_group.add_argument("--url")
    add_repo(status)
    status.set_defaults(func=project_set_status_command)

    pr = sub.add_parser("pr-create")
    pr.add_argument("--title", required=True)
    pr.add_argument("--body-file")
    pr.add_argument("--body")
    pr.add_argument("--issue")
    pr.add_argument("--ready", action="store_true", help="create ready for review; default is draft")
    add_repo(pr)
    pr.set_defaults(func=pr_create)

    labels = sub.add_parser("bootstrap-labels")
    add_repo(labels)
    labels.set_defaults(func=bootstrap_labels)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
