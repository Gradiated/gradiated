#!/usr/bin/env python3
"""Backfill retention tags and SSE-KMS on the production model-artifacts bucket.

Dry-run by default: it only lists, heads and reads tags, so it runs with the
read-only profile. `--apply` tags training datasets and checkpoints with
`retention=90d` (lifecycle rule ExpireTrainingInputsAfter90Days) and rewrites
SSE-S3 objects in place with the bucket's KMS key, keeping metadata and tags.

A copy in place resets the object's creation date, so a re-encrypted dataset
or checkpoint expires 90 days after the backfill rather than after its run.
Every object here predates automatic deletion, which the Data Retention Policy
does not promise for them.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
import re
import subprocess
import sys
from urllib.parse import quote, urlencode

ACCOUNT = "873716897517"
REGION = "us-east-1"
BUCKET = f"gradiated-prod-model-artifacts-{ACCOUNT}"
KEY_ALIAS = "alias/gradiated/prod-model-artifacts"
RETENTION = ("retention", "90d")
EXPIRING = re.compile(r"^runs/[^/]+/(dataset|checkpoints)/")
COPY_LIMIT = 5 * 1024**3
PART_SIZE = 1024**3
CONTENT_HEADERS = ("ContentType", "ContentEncoding", "ContentDisposition", "ContentLanguage", "CacheControl")

READS = {
    ("sts", "get-caller-identity"),
    ("kms", "describe-key"),
    ("s3api", "list-objects-v2"),
    ("s3api", "list-object-versions"),
    ("s3api", "head-object"),
    ("s3api", "get-object-tagging"),
}
WRITES = {
    ("s3api", "put-object-tagging"),
    ("s3api", "copy-object"),
    ("s3api", "create-multipart-upload"),
    ("s3api", "upload-part-copy"),
    ("s3api", "complete-multipart-upload"),
    ("s3api", "abort-multipart-upload"),
}


class BackfillError(RuntimeError):
    pass


@dataclass
class Aws:
    apply: bool = False
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, service: str, operation: str, *args: str) -> dict:
        if (service, operation) not in READS and not (self.apply and (service, operation) in WRITES):
            raise BackfillError(f"Refused {service} {operation} outside --apply")
        self.calls.append((service, operation))
        return self.invoke(service, operation, args)

    def invoke(self, service: str, operation: str, args: tuple[str, ...]) -> dict:
        command = ["aws", service, operation, "--region", REGION, "--output", "json", "--no-cli-pager", *args]
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600,
                                env={**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"})
        if result.returncode:
            code = re.search(r"\(([A-Za-z]+)\)", result.stderr)
            raise BackfillError(f"{service} {operation}: {code.group(1) if code else 'exit ' + str(result.returncode)}")
        return json.loads(result.stdout) if result.stdout.strip() else {}


@dataclass
class Plan:
    key: str
    size: int
    etag: str
    created: datetime
    expiring: bool
    encryption: str  # "kms", "kms-other-key" or "sse-s3"
    head: dict
    tags: dict[str, str] | None
    tag: bool = False
    reencrypt: bool = False


def plan_object(obj: dict, head: dict, tags: dict[str, str] | None, key_arn: str) -> Plan:
    if head.get("ServerSideEncryption") == "aws:kms":
        encryption = "kms" if head.get("SSEKMSKeyId") == key_arn else "kms-other-key"
    else:
        encryption = "sse-s3"
    expiring = bool(EXPIRING.match(obj["Key"]))
    plan = Plan(obj["Key"], obj["Size"], head["ETag"],
                datetime.fromisoformat(obj["LastModified"].replace("Z", "+00:00")),
                expiring, encryption, head, tags)
    plan.tag = expiring and (tags or {}).get(RETENTION[0]) != RETENTION[1]
    plan.reencrypt = encryption == "sse-s3"
    return plan


def inspect(aws: Aws, bucket: str, obj: dict, key_arn: str) -> Plan:
    head = aws("s3api", "head-object", "--bucket", bucket, "--key", obj["Key"], "--checksum-mode", "ENABLED")
    tags = None
    if EXPIRING.match(obj["Key"]):
        reply = aws("s3api", "get-object-tagging", "--bucket", bucket, "--key", obj["Key"])
        tags = {tag["Key"]: tag["Value"] for tag in reply.get("TagSet", [])}
    return plan_object(obj, head, tags, key_arn)


def merged_tags(plan: Plan) -> dict[str, str]:
    return {**(plan.tags or {}), **({RETENTION[0]: RETENTION[1]} if plan.tag else {})}


def kms_args(plan: Plan, key_arn: str) -> list[str]:
    args = ["--server-side-encryption", "aws:kms", "--ssekms-key-id", key_arn, "--bucket-key-enabled"]
    if plan.head.get("StorageClass"):
        args += ["--storage-class", plan.head["StorageClass"]]
    return args


def reencrypt(aws: Aws, bucket: str, plan: Plan, key_arn: str) -> None:
    source = f"{bucket}/{quote(plan.key, safe='/')}"
    if plan.tag:
        tagging = ["--tagging", urlencode(merged_tags(plan))]
    else:
        tagging = []

    if plan.size <= COPY_LIMIT:
        args = ["--bucket", bucket, "--key", plan.key, "--copy-source", source,
                "--copy-source-if-match", plan.etag, "--metadata-directive", "COPY",
                *kms_args(plan, key_arn)]
        args += ["--tagging-directive", "REPLACE", *tagging] if tagging else ["--tagging-directive", "COPY"]
        if plan.head.get("ChecksumSHA256") and plan.head.get("ChecksumType") == "FULL_OBJECT":
            args += ["--checksum-algorithm", "SHA256"]
        aws("s3api", "copy-object", *args)
        return

    # CopyObject stops at 5 GiB; a multipart copy carries headers and tags explicitly.
    if not tagging:
        tags = plan.tags
        if tags is None:
            reply = aws("s3api", "get-object-tagging", "--bucket", bucket, "--key", plan.key)
            tags = {tag["Key"]: tag["Value"] for tag in reply.get("TagSet", [])}
        tagging = ["--tagging", urlencode(tags)] if tags else []
    headers = []
    for name in CONTENT_HEADERS:
        if plan.head.get(name):
            headers += ["--" + re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower(), plan.head[name]]
    if plan.head.get("Metadata"):
        headers += ["--metadata", json.dumps(plan.head["Metadata"])]
    upload = aws("s3api", "create-multipart-upload", "--bucket", bucket, "--key", plan.key,
                 *headers, *tagging, *kms_args(plan, key_arn))["UploadId"]
    try:
        parts = []
        for number, start in enumerate(range(0, plan.size, PART_SIZE), 1):
            end = min(start + PART_SIZE, plan.size) - 1
            reply = aws("s3api", "upload-part-copy", "--bucket", bucket, "--key", plan.key,
                        "--upload-id", upload, "--part-number", str(number), "--copy-source", source,
                        "--copy-source-if-match", plan.etag, "--copy-source-range", f"bytes={start}-{end}")
            parts.append({"ETag": reply["CopyPartResult"]["ETag"], "PartNumber": number})
        aws("s3api", "complete-multipart-upload", "--bucket", bucket, "--key", plan.key,
            "--upload-id", upload, "--multipart-upload", json.dumps({"Parts": parts}))
    except BaseException:
        aws("s3api", "abort-multipart-upload", "--bucket", bucket, "--key", plan.key, "--upload-id", upload)
        raise


def execute(aws: Aws, bucket: str, plan: Plan, key_arn: str) -> None:
    if plan.reencrypt:
        reencrypt(aws, bucket, plan, key_arn)
    elif plan.tag:
        tag_set = [{"Key": key, "Value": value} for key, value in merged_tags(plan).items()]
        aws("s3api", "put-object-tagging", "--bucket", bucket, "--key", plan.key,
            "--tagging", json.dumps({"TagSet": tag_set}))


def kind(key: str) -> str:
    parts = key.split("/")
    if parts[0] == "runs" and len(parts) > 2:
        return "runs/*/" + parts[2]
    return parts[0]


def summarize(plans: list[Plan], now: datetime) -> dict:
    cutoff = now - timedelta(days=90)
    tag = [plan for plan in plans if plan.tag]
    reencrypt = [plan for plan in plans if plan.reencrypt]
    return {
        "objects": len(plans),
        "by_kind": dict(sorted(Counter(kind(plan.key) for plan in plans).items())),
        "encryption": dict(sorted(Counter(plan.encryption for plan in plans).items())),
        "expiring_objects": sum(plan.expiring for plan in plans),
        "expiring_already_tagged": sum(plan.expiring and not plan.tag for plan in plans),
        "to_tag": len(tag),
        "to_tag_older_than_90_days": sum(plan.created < cutoff for plan in tag),
        "to_reencrypt": len(reencrypt),
        "to_reencrypt_bytes": sum(plan.size for plan in reencrypt),
        "to_reencrypt_multipart": sum(plan.size > COPY_LIMIT for plan in reencrypt),
        "to_reencrypt_by_kind": dict(sorted(Counter(kind(plan.key) for plan in reencrypt).items())),
        "kms_other_key_skipped": sum(plan.encryption == "kms-other-key" for plan in plans),
    }


def run(argv: list[str], aws: Aws | None = None, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write tags and re-encrypt; default is a dry run")
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--key-alias", default=KEY_ALIAS)
    parser.add_argument("--prefix", default="", help="limit the backfill to keys under this prefix")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    aws = aws or Aws(apply=args.apply)
    now = now or datetime.now(timezone.utc)

    account = aws("sts", "get-caller-identity")["Account"]
    if account != ACCOUNT:
        raise BackfillError(f"Wrong AWS account {account}; expected {ACCOUNT}")
    key_arn = aws("kms", "describe-key", "--key-id", args.key_alias)["KeyMetadata"]["Arn"]
    listing = aws("s3api", "list-objects-v2", "--bucket", args.bucket, "--prefix", args.prefix)
    objects = listing.get("Contents") or []
    versions = aws("s3api", "list-object-versions", "--bucket", args.bucket, "--prefix", args.prefix)
    noncurrent = [version for version in versions.get("Versions") or [] if not version["IsLatest"]]

    with ThreadPoolExecutor(args.workers) as pool:
        plans = list(pool.map(lambda obj: inspect(aws, args.bucket, obj, key_arn), objects))
    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "bucket": args.bucket,
        "prefix": args.prefix,
        "kms_key": key_arn,
        **summarize(plans, now),
        "noncurrent_versions": len(noncurrent),
        "noncurrent_versions_outside_runs": sum(not version["Key"].startswith("runs/") for version in noncurrent),
    }

    failures: list[str] = []
    if args.apply:
        def apply(plan: Plan) -> str | None:
            try:
                execute(aws, args.bucket, plan, key_arn)
            except BackfillError as error:
                return f"{plan.key}: {error}"
            return None

        pending = [plan for plan in plans if plan.tag or plan.reencrypt]
        with ThreadPoolExecutor(args.workers) as pool:
            failures = [failure for failure in pool.map(apply, pending) if failure]
        summary["applied"] = len(pending) - len(failures)
        summary["failed"] = len(failures)

    print(json.dumps(summary, indent=2))
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1:]))
    except BackfillError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
