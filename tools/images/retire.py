#!/usr/bin/env python3
"""Retire ECR images unused for 90 days. Defaults to a live, read-only preview."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
RESOURCES = (
    "pods", "replicationcontrollers", "deployments.apps", "replicasets.apps",
    "statefulsets.apps", "daemonsets.apps", "jobs.batch", "cronjobs.batch",
    "rollouts.argoproj.io", "applications.argoproj.io", "configmaps",
)


def run(arguments: list[str]) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=120)
    if result.returncode:
        # Commands can read secrets; never include their output in an exception.
        raise RuntimeError(f"{arguments[0]} {arguments[1]} failed (exit {result.returncode})")
    return result.stdout


def aws(*arguments: str) -> dict:
    return json.loads(run(["aws", *arguments, "--output", "json", "--no-cli-pager"]))


def timestamp(value: str | float) -> datetime:
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value, timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def runpod_images(api_key: str) -> list[str]:
    query = "query { myself { pods { id imageName templateId } podTemplates { id imageName } } }"
    request = urllib.request.Request(
        "https://api.runpod.io/graphql", data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("RunPod image inventory failed")
    owner = result["data"]["myself"]
    pods, templates = owner["pods"], owner["podTemplates"]
    if not isinstance(pods, list) or not pods or not isinstance(templates, list):
        raise RuntimeError("RunPod inventory is empty or invalid; refusing cleanup")
    template_ids = {item["id"] for item in templates}
    if any(pod.get("templateId") and pod["templateId"] not in template_ids for pod in pods):
        raise RuntimeError("A RunPod pod template is absent from the template inventory")
    references = [item["imageName"] for item in pods + templates]
    if any(not isinstance(image, str) or not image.strip() for image in references):
        raise RuntimeError("RunPod inventory contains a missing image")
    return references


def inventory(api_key: str) -> list[str]:
    references = runpod_images(api_key)
    for resource in RESOURCES:
        result = json.loads(run([
            "kubectl", "--request-timeout=30s", "get", resource, "--all-namespaces", "-o", "json",
        ]))
        if not isinstance(result.get("items"), list) or result.get("metadata", {}).get("continue"):
            raise RuntimeError(f"Incomplete Kubernetes inventory: {resource}")
        if resource == "pods" and not result["items"]:
            raise RuntimeError("Kubernetes pod inventory is empty; refusing cleanup")
        for item in result["items"]:
            references.extend(strings(item.get("spec", {})))
            if resource == "pods":
                references.extend(strings(item.get("status", {})))
            if resource == "configmaps":
                references.extend(strings(item.get("data", {})))
    paths = run(["git", "ls-files", "-z", "infra/environments/prod"]).split("\0")
    for path in filter(None, paths):
        if Path(path).suffix in {".yaml", ".yml", ".json", ".tf", ".hcl"}:
            references.append((ROOT / path).read_text())
    return references


def protected_images(images: dict, references: list[str], registry: str) -> set[tuple[str, str]]:
    protected = set()
    # Standalone digests also cover Kustomize's separate newName/digest fields.
    digests = {digest for text in references for digest in DIGEST.findall(text)}
    text = "\n".join(references)
    for repository, entries in images.items():
        for image in entries:
            digest = image["imageDigest"]
            if digest in digests or any(
                f"{registry}/{repository}:{tag}" in text for tag in image.get("imageTags", [])
            ):
                protected.add((repository, digest))
    # An unresolved production image reference can indicate a partial inventory.
    pattern = re.compile(re.escape(registry) + r"/([a-z0-9/_-]+)(?::([a-zA-Z0-9_.-]+)|@(sha256:[0-9a-f]{64}))")
    for repository, tag, digest in pattern.findall(text):
        if repository not in images:
            raise RuntimeError(f"Referenced repository is outside cleanup inventory: {repository}")
        if not any(
            digest == item["imageDigest"] or tag in item.get("imageTags", [])
            for item in images[repository]
        ):
            raise RuntimeError(f"Referenced image is missing from ECR inventory: {repository}")
    return protected


def retirement_plan(images: dict, manifests: dict, protected: set, now: datetime, days: int) -> list[dict]:
    cutoff = now - timedelta(days=days)
    keep = set(protected)
    parents = {}
    referrers = {}
    for repository, entries in images.items():
        for image in entries:
            key = (repository, image["imageDigest"])
            if key not in manifests:
                raise RuntimeError(f"Missing manifest: {key}")
            manifest = manifests[key]
            children = {entry["digest"] for entry in manifest.get("manifests", [])}
            if manifest.get("subject"):
                subject = manifest["subject"]["digest"]
                children.add(subject)
                referrers.setdefault((repository, subject), set()).add(key)
            parents[key] = {(repository, child) for child in children}
            if timestamp(image["imagePushedAt"]) >= cutoff or (
                image.get("lastRecordedPullTime") is not None
                and timestamp(image["lastRecordedPullTime"]) >= cutoff
            ):
                keep.add(key)
    pending = list(keep)
    while pending:
        key = pending.pop()
        for child in parents.get(key, set()) | referrers.get(key, set()):
            if child not in keep:
                keep.add(child)
                pending.append(child)
    candidates = set(parents) - keep
    # Delete an index before its platform/attestation manifests. ECR also rejects
    # deleting a child while a retained index references it.
    ordered = []
    while candidates:
        children = set().union(*(parents[key] for key in candidates))
        roots = sorted(candidates - children)
        if not roots:
            raise RuntimeError("Manifest reference cycle")
        ordered.extend(roots)
        candidates.difference_update(roots)
    details = {(repo, image["imageDigest"]): image for repo, entries in images.items() for image in entries}
    return [dict(repository=repo, digest=digest, tags=details[(repo, digest)].get("imageTags", []))
            for repo, digest in ordered]


def require_pull_exclusion() -> None:
    identity = aws("sts", "get-caller-identity")
    exclusions = aws("ecr", "list-pull-time-update-exclusions")["pullTimeUpdateExclusions"]
    principal = identity["Arn"]
    if ":assumed-role/" in principal:
        role = principal.split(":assumed-role/", 1)[1].split("/", 1)[0]
        excluded = any(
            arn.startswith(f"arn:aws:iam::{identity['Account']}:role/") and arn.rsplit("/", 1)[1] == role
            for arn in exclusions
        )
    else:
        excluded = principal in exclusions
    if not excluded:
        raise RuntimeError("Inventory principal must have an ECR pull-time update exclusion before reading manifests")


def ecr_inventory(repositories: list[str]) -> tuple[dict, dict]:
    require_pull_exclusion()
    images, manifests = {}, {}
    for repository in repositories:
        images[repository] = aws("ecr", "describe-images", "--repository-name", repository)["imageDetails"]
        digests = [item["imageDigest"] for item in images[repository]]
        for offset in range(0, len(digests), 100):
            response = aws("ecr", "batch-get-image", "--repository-name", repository, "--image-ids",
                           *[f"imageDigest={digest}" for digest in digests[offset:offset + 100]])
            if response.get("failures"):
                raise RuntimeError(f"Cannot read all manifests in {repository}")
            for image in response["images"]:
                manifests[(repository, image["imageId"]["imageDigest"])] = json.loads(image["imageManifest"])
    return images, manifests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--repositories", nargs="+", required=True)
    parser.add_argument("--runpod-secret", help="Secrets Manager JSON container with a runpod-api-key field")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.days < 90 or not re.fullmatch(r"\d{12}", args.account):
        parser.error("A valid AWS account and retention of at least 90 days are required")
    if any(not re.fullmatch(r"gradiated/prod/[a-z0-9-]+", repo) for repo in args.repositories):
        parser.error("Only explicitly listed gradiated/prod repositories may be retired")
    if aws("sts", "get-caller-identity")["Account"] != args.account:
        raise RuntimeError("AWS account mismatch")
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    registry = f"{args.account}.dkr.ecr.{region}.amazonaws.com"
    api_key = os.environ.get("RUNPOD_API_KEY", "")
    if args.runpod_secret:
        secret = aws("secretsmanager", "get-secret-value", "--secret-id", args.runpod_secret)
        api_key = json.loads(secret["SecretString"])["runpod-api-key"]
    if not api_key:
        raise RuntimeError("RunPod inventory credentials are required")
    references = inventory(api_key)
    images, manifests = ecr_inventory(args.repositories)
    protected = protected_images(images, references, registry)
    now = datetime.now(timezone.utc)
    plan = retirement_plan(images, manifests, protected, now, args.days)
    print(json.dumps({"apply": args.apply, "days": args.days, "protected": len(protected), "candidates": plan}, indent=2))
    if not args.apply or not plan:
        return
    # Recheck live references and pull timestamps immediately before deletion.
    references = inventory(api_key)
    fresh_images, fresh_manifests = ecr_inventory(args.repositories)
    fresh_protected = protected_images(fresh_images, references, registry)
    fresh = retirement_plan(fresh_images, fresh_manifests, fresh_protected, datetime.now(timezone.utc), args.days)
    eligible = {(item["repository"], item["digest"]) for item in fresh}
    for item in plan:
        if (item["repository"], item["digest"]) not in eligible:
            continue
        result = aws("ecr", "batch-delete-image", "--repository-name", item["repository"],
                     "--image-ids", f"imageDigest={item['digest']}")
        if result.get("failures"):
            raise RuntimeError(f"ECR refused deletion in {item['repository']}; stopping cleanup")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Image cleanup stopped: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
