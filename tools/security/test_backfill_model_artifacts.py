import contextlib
from datetime import datetime, timezone
import io
import json
import unittest

import backfill_model_artifacts as backfill

KEY_ARN = "arn:aws:kms:us-east-1:873716897517:key/model-artifacts"
RUN = "runs/01900000-0000-7000-8000-000000000001"
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def options(args):
    parsed = {}
    for index, arg in enumerate(args):
        if arg.startswith("--"):
            value = args[index + 1] if index + 1 < len(args) else None
            parsed[arg] = None if value is None or value.startswith("--") else value
    return parsed


def head(encryption="AES256", key_id=None, **extra):
    reply = {"ETag": '"etag"', "ServerSideEncryption": encryption, **extra}
    if key_id:
        reply["SSEKMSKeyId"] = key_id
    return reply


class FakeAws(backfill.Aws):
    def __init__(self, objects, apply=False, account=backfill.ACCOUNT):
        super().__init__(apply=apply)
        self.objects = objects
        self.account = account
        self.writes = []

    def invoke(self, service, operation, args):
        option = options(args)
        key = option.get("--key")
        if operation == "get-caller-identity":
            return {"Account": self.account}
        if operation == "describe-key":
            return {"KeyMetadata": {"Arn": KEY_ARN}}
        if operation == "list-objects-v2":
            return {"Contents": [{"Key": key, "Size": item["size"], "LastModified": item["created"]}
                                 for key, item in self.objects.items()]}
        if operation == "list-object-versions":
            return {"Versions": [{"Key": "bundles/old.tar.gz", "IsLatest": False}]}
        if operation == "head-object":
            return self.objects[key]["head"]
        if operation == "get-object-tagging":
            return {"TagSet": [{"Key": k, "Value": v} for k, v in self.objects[key].get("tags", {}).items()]}
        if operation == "create-multipart-upload":
            self.writes.append((operation, key, args))
            return {"UploadId": "upload"}
        if operation == "upload-part-copy":
            self.writes.append((operation, key, args))
            return {"CopyPartResult": {"ETag": f'"part-{option["--part-number"]}"'}}
        self.writes.append((operation, key, args))
        return {}


def run(aws, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = backfill.run(list(argv), aws=aws, now=NOW)
    return code, json.loads(out.getvalue())


def item(head_reply, size=10, created="2026-10-01T00:00:00Z", tags=None):
    return {"head": head_reply, "size": size, "created": created, "tags": tags or {}}


class BackfillTests(unittest.TestCase):
    def objects(self):
        return {
            f"{RUN}/dataset/v1/train.jsonl": item(head(), created="2026-07-01T00:00:00Z"),
            f"{RUN}/dataset/v1/dataset-manifest.json": item(head("aws:kms", KEY_ARN), tags={"retention": "90d"}),
            f"{RUN}/checkpoints/0/10.tar.gz": item(head("aws:kms", KEY_ARN), tags={"owner": "trainer"}),
            f"{RUN}/checkpoints/latest.json": item(head()),
            f"{RUN}/evaluation/result.json": item(head()),
            f"{RUN}/output/0/adapter.tar.gz": item(head("aws:kms", KEY_ARN)),
            f"{RUN}/run-manifest.json": item(head()),
            "bundles/sha256/big.tar.gz": item(head(ContentType="application/gzip", Metadata={"sha": "x"}),
                                              size=backfill.COPY_LIMIT + 1, tags={"release": "a b"}),
            "releases/other-key.json": item(head("aws:kms", "arn:aws:kms:us-east-1:873716897517:key/other")),
        }

    def test_dry_run_counts_without_writes(self):
        aws = FakeAws(self.objects())
        code, summary = run(aws)
        self.assertEqual(code, 0)
        self.assertEqual(aws.writes, [])
        self.assertEqual(summary["mode"], "dry-run")
        self.assertEqual(summary["objects"], 9)
        self.assertEqual(summary["expiring_objects"], 4)
        self.assertEqual(summary["expiring_already_tagged"], 1)
        self.assertEqual(summary["to_tag"], 3)
        self.assertEqual(summary["to_tag_older_than_90_days"], 1)
        self.assertEqual(summary["to_reencrypt"], 5)
        self.assertEqual(summary["to_reencrypt_by_kind"], {
            "bundles": 1, "runs/*/checkpoints": 1, "runs/*/dataset": 1,
            "runs/*/evaluation": 1, "runs/*/run-manifest.json": 1})
        self.assertEqual(summary["to_reencrypt_multipart"], 1)
        self.assertEqual(summary["kms_other_key_skipped"], 1)
        self.assertEqual(summary["noncurrent_versions_outside_runs"], 1)

    def test_dry_run_refuses_writes_before_invoking_cli(self):
        aws = FakeAws({})
        for operation in ["put-object-tagging", "copy-object", "delete-object", "put-bucket-lifecycle-configuration"]:
            with self.assertRaises(backfill.BackfillError):
                aws("s3api", operation)
        with self.assertRaises(backfill.BackfillError):
            FakeAws({}, apply=True)("s3api", "delete-object")
        self.assertEqual(aws.writes, [])

    def test_wrong_account_stops_before_listing(self):
        aws = FakeAws(self.objects(), account="000000000000")
        with self.assertRaisesRegex(backfill.BackfillError, "Wrong AWS account"):
            run(aws)
        self.assertEqual(aws.calls, [("sts", "get-caller-identity")])

    def test_apply_tags_expiring_objects_and_reencrypts_sse_s3_objects(self):
        aws = FakeAws(self.objects(), apply=True)
        code, summary = run(aws, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(summary["applied"], 6)
        by_key = {}
        for operation, key, args in aws.writes:
            by_key.setdefault(key, []).append((operation, options(args), args))

        tagged = by_key[f"{RUN}/checkpoints/0/10.tar.gz"]
        self.assertEqual([op for op, *_ in tagged], ["put-object-tagging"])
        self.assertEqual(json.loads(tagged[0][1]["--tagging"])["TagSet"],
                         [{"Key": "owner", "Value": "trainer"}, {"Key": "retention", "Value": "90d"}])
        for key in [f"{RUN}/dataset/v1/train.jsonl", f"{RUN}/checkpoints/latest.json"]:
            (operation, option, _), = by_key[key]
            self.assertEqual(operation, "copy-object")
            self.assertEqual(option["--tagging-directive"], "REPLACE")
            self.assertEqual(option["--tagging"], "retention=90d")
            self.assertEqual(option["--ssekms-key-id"], KEY_ARN)
        self.assertNotIn(f"{RUN}/dataset/v1/dataset-manifest.json", by_key)
        self.assertNotIn(f"{RUN}/output/0/adapter.tar.gz", by_key)
        self.assertNotIn("releases/other-key.json", by_key)

        (operation, option, args), = by_key[f"{RUN}/evaluation/result.json"]
        self.assertEqual(operation, "copy-object")
        self.assertEqual(option["--copy-source"], f"{backfill.BUCKET}/{RUN}/evaluation/result.json")
        self.assertEqual(option["--copy-source-if-match"], '"etag"')
        self.assertEqual(option["--metadata-directive"], "COPY")
        self.assertEqual(option["--tagging-directive"], "COPY")
        self.assertEqual(option["--ssekms-key-id"], KEY_ARN)
        self.assertIn("--bucket-key-enabled", args)
        self.assertNotIn("--tagging", option)

        big = by_key["bundles/sha256/big.tar.gz"]
        self.assertEqual([op for op, *_ in big], ["create-multipart-upload", "upload-part-copy", "upload-part-copy",
                                                  "upload-part-copy", "upload-part-copy", "upload-part-copy",
                                                  "upload-part-copy", "complete-multipart-upload"])
        create = big[0][1]
        self.assertEqual(create["--content-type"], "application/gzip")
        self.assertEqual(json.loads(create["--metadata"]), {"sha": "x"})
        self.assertEqual(create["--tagging"], "release=a+b")
        self.assertEqual(create["--ssekms-key-id"], KEY_ARN)
        self.assertEqual(big[-2][1]["--copy-source-range"],
                         f"bytes={5 * backfill.PART_SIZE}-{backfill.COPY_LIMIT}")
        self.assertEqual(len(json.loads(big[-1][1]["--multipart-upload"])["Parts"]), 6)

    def test_reencrypting_an_expiring_object_merges_the_retention_tag(self):
        aws = FakeAws({f"{RUN}/checkpoints/latest.json": item(head(), tags={"owner": "worker"})}, apply=True)
        run(aws, "--apply")
        (operation, key, args), = aws.writes
        option = options(args)
        self.assertEqual(operation, "copy-object")
        self.assertEqual(option["--tagging-directive"], "REPLACE")
        self.assertEqual(option["--tagging"], "owner=worker&retention=90d")

    def test_second_run_is_a_no_op(self):
        objects = {
            f"{RUN}/dataset/v1/train.jsonl": item(head("aws:kms", KEY_ARN), tags={"retention": "90d"}),
            f"{RUN}/evaluation/result.json": item(head("aws:kms", KEY_ARN)),
        }
        aws = FakeAws(objects, apply=True)
        code, summary = run(aws, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(aws.writes, [])
        self.assertEqual(summary["applied"], 0)

    def test_failed_copy_aborts_multipart_and_reports(self):
        class Failing(FakeAws):
            def invoke(self, service, operation, args):
                if operation == "upload-part-copy":
                    raise backfill.BackfillError("s3api upload-part-copy: PreconditionFailed")
                return super().invoke(service, operation, args)

        aws = Failing({"bundles/big.tar.gz": item(head(), size=backfill.COPY_LIMIT + 1)}, apply=True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, summary = run(aws, "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual([op for op, *_ in aws.writes], ["create-multipart-upload", "abort-multipart-upload"])
        self.assertIn("PreconditionFailed", err.getvalue())


if __name__ == "__main__":
    unittest.main()
