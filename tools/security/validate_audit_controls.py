"""Validate rendered audit policies/event patterns with read-only AWS APIs; sends no events."""

import argparse
import json
from pathlib import Path
import subprocess


def aws(*args):
    return json.loads(subprocess.check_output(["aws", *args, "--output", "json"], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terraform_test_log", type=Path)
    args = parser.parse_args()
    resources = []
    for line in args.terraform_test_log.read_text().splitlines():
        event = json.loads(line)
        if event.get("@testrun") == "durable_multi_region_audit_and_notifications":
            resources += event.get("test_state", {}).get("root_module", {}).get("resources", [])
    assert resources, "Missing rendered Terraform mock state"
    checked = 0
    patterns = {}
    for resource in resources:
        kind, values = resource["type"], resource["values"]
        if kind == "aws_cloudwatch_event_rule" and resource["name"] == "regional":
            patterns[resource["index"]] = values["event_pattern"]
        if kind not in {"aws_iam_role", "aws_iam_role_policy", "aws_s3_bucket_policy", "aws_sns_topic_policy", "aws_sqs_queue_policy"}:
            continue
        policy_field = "assume_role_policy" if kind == "aws_iam_role" else "policy"
        if policy_field not in values or not values[policy_field] or resource.get("mode") == "data":
            continue
        policy_type = "IDENTITY_POLICY" if kind == "aws_iam_role_policy" else "RESOURCE_POLICY"
        arguments = ["accessanalyzer", "validate-policy", "--policy-type", policy_type,
                     "--policy-document", values[policy_field]]
        if kind == "aws_iam_role":
            arguments += ["--validate-policy-resource-type", "AWS::IAM::AssumeRolePolicyDocument"]
        findings = aws(*arguments)["findings"]
        errors = [finding for finding in findings if finding["findingType"] == "ERROR"]
        assert not errors, f"{resource['address']}: {errors}"
        checked += 1

    cases = [
        ("findings", "aws.guardduty", "GuardDuty Finding", {"severity": 8}, True),
        ("findings", "aws.guardduty", "GuardDuty Finding", {"severity": 4}, True),
        ("findings", "aws.guardduty", "GuardDuty Finding", {"severity": 2}, False),
        ("control_changes", "aws.cloudtrail", "AWS API Call via CloudTrail", {"eventName": "StopLogging"}, True),
        ("control_changes", "aws.iam", "AWS API Call via CloudTrail", {"eventName": "GetRole"}, False),
        ("root_activity", "aws.signin", "AWS Console Sign In via CloudTrail", {"userIdentity": {"type": "Root"}}, True),
        ("root_activity", "aws.iam", "AWS API Call via CloudTrail", {"userIdentity": {"type": "AssumedRole"}}, False),
        ("root_activity", "aws.iam", "AWS API Call via CloudTrail", {"userIdentity": {"type": "Root"}, "eventName": "GetRole", "readOnly": True}, True),
    ]
    assert len(set(patterns.values())) == 1, "Every region must use the same combined alert pattern"
    pattern = next(iter(patterns.values()))
    for name, source, detail_type, detail, expected in cases:
        event = {"version": "0", "id": "00000000-0000-0000-0000-000000000000",
                 "account": "873716897517", "time": "2026-01-01T00:00:00Z", "region": "us-east-1",
                 "resources": [], "source": source, "detail-type": detail_type, "detail": detail}
        result = aws("events", "test-event-pattern", "--event-pattern", pattern, "--event", json.dumps(event))
        assert result["Result"] == expected, f"Unexpected match for {name}: {detail}"
    print(f"PASS: {checked} policy documents and {len(cases)} EventBridge matching cases; no events published")


if __name__ == "__main__":
    main()
