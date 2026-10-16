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
    recovery_policy = None
    backup_policy = None
    for resource in resources:
        kind, values = resource["type"], resource["values"]
        if kind == "aws_iam_role_policy" and resource["name"] == "recovery":
            recovery_policy = values["policy"]
        if kind == "aws_iam_role_policy" and resource["name"] == "monitoring_backup":
            backup_policy = values["policy"]
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

    if recovery_policy:
        target = "arn:aws:rds:us-east-1:873716897517:db:gradiated-recovery-pg-test"
        owned = [{"ContextKeyName": "aws:ResourceTag/Purpose", "ContextKeyType": "string", "ContextKeyValues": ["weekly-recovery-verification"]}]
        create = [
            {"ContextKeyName": "aws:RequestTag/Purpose", "ContextKeyType": "string", "ContextKeyValues": ["weekly-recovery-verification"]},
            {"ContextKeyName": "rds:DatabaseClass", "ContextKeyType": "string", "ContextKeyValues": ["db.t4g.small"]},
            {"ContextKeyName": "rds:PubliclyAccessible", "ContextKeyType": "boolean", "ContextKeyValues": ["false"]},
            {"ContextKeyName": "rds:MultiAz", "ContextKeyType": "boolean", "ContextKeyValues": ["false"]},
        ]
        checks = [("rds:RestoreDBInstanceFromDBSnapshot", target, True, create),
                  ("rds:DeleteDBInstance", target, True, owned), ("rds:DeleteDBInstance", target, False, []),
                  ("rds:ModifyDBInstance", target, False, owned)]
        for source in ["gradiated-prod", "gradiated-prod-metabase"]:
            for action in ["rds:DeleteDBInstance", "rds:ModifyDBInstance"]:
                checks.append((action, f"arn:aws:rds:us-east-1:873716897517:db:{source}", False, owned))
        for key, value in [("rds:PubliclyAccessible", "true"), ("rds:MultiAz", "true"), ("rds:DatabaseClass", "db.r7g.16xlarge")]:
            context = [{**entry, "ContextKeyValues": [value]} if entry["ContextKeyName"] == key else entry for entry in create]
            checks.append(("rds:RestoreDBInstanceFromDBSnapshot", target, False, context))
        for action in ["CreateSecret", "PutSecretValue", "UpdateSecret", "RotateSecret", "DeleteSecret"]:
            checks.append(("secretsmanager:" + action, "*", False, []))
        for action, resource, expected, context in checks:
            arguments = ["iam", "simulate-custom-policy", "--policy-input-list", recovery_policy,
                         "--action-names", action, "--resource-arns", resource]
            if context:
                arguments += ["--context-entries", json.dumps(context)]
            decision = aws(*arguments)["EvaluationResults"][0]["EvalDecision"]
            assert (decision == "allowed") == expected, f"Recovery {action} {resource}: {decision}"
        print(f"PASS: {len(checks)} AWS IAM recovery safety cases")

    assert backup_policy, "Missing monitoring backup policy"
    # Ask IAM to evaluate positive selections and realistic near misses, rather
    # than trusting that a syntactically valid tag condition enforces the scope.
    tags = {"KubernetesCluster": "gradiated-prod", "kubernetes.io/created-for/pvc/namespace": "observability", "kubernetes.io/created-for/pvc/name": "observability-grafana"}
    selection_cases = [("grafana", tags, True)]
    for key, value in [("KubernetesCluster", "another-cluster"), ("kubernetes.io/created-for/pvc/namespace", "another-namespace"), ("kubernetes.io/created-for/pvc/name", "ops-mcp-sessions"), ("kubernetes.io/created-for/pvc/name", "storage-loki-0")]:
        selection_cases.append((value, {**tags, key: value}, False))
    selection_cases.append(("untagged-node-disk", {}, False))
    for name, selected_tags, expected in selection_cases:
        context = [{"ContextKeyName": "aws:ResourceTag/" + key, "ContextKeyType": "string", "ContextKeyValues": [value]} for key, value in selected_tags.items()]
        arguments = ["iam", "simulate-custom-policy", "--policy-input-list", backup_policy,
                     "--action-names", "ec2:CreateSnapshot", "--resource-arns",
                     "arn:aws:ec2:us-east-1:873716897517:volume/vol-0123456789abcdef0"]
        if context:
            arguments += ["--context-entries", json.dumps(context)]
        decision = aws(*arguments)["EvaluationResults"][0]["EvalDecision"]
        assert (decision == "allowed") == expected, f"Backup selection {name}: {decision}"
    print(f"PASS: {len(selection_cases)} AWS IAM backup-volume selection cases")

    cases = [
        ("monitoring_backup_failure", "aws.backup", "Backup Job State Change", {"state": "FAILED", "backupVaultName": "gradiated-security-monitoring"}, True),
        ("monitoring_backup_partial", "aws.backup", "Backup Job State Change", {"state": "PARTIAL", "backupVaultName": "gradiated-security-monitoring"}, True),
        ("monitoring_backup_success", "aws.backup", "Backup Job State Change", {"state": "COMPLETED", "backupVaultName": "gradiated-security-monitoring"}, False),
        ("other_backup_failure", "aws.backup", "Backup Job State Change", {"state": "FAILED", "backupVaultName": "other-vault"}, False),
        ("external_access", "aws.access-analyzer", "Access Analyzer Finding", {"status": "ACTIVE", "isPublic": True}, True),
        ("external_cross_account", "aws.access-analyzer", "Access Analyzer Finding", {"status": "ACTIVE", "isPublic": False}, True),
        ("external_analysis_error", "aws.access-analyzer", "Access Analyzer Finding", {"status": "ACTIVE", "error": "ACCESS_DENIED"}, True),
        ("external_resolved", "aws.access-analyzer", "Access Analyzer Finding", {"status": "RESOLVED"}, False),
        ("external_archived", "aws.access-analyzer", "Access Analyzer Finding", {"status": "ARCHIVED"}, False),
        ("external_preview", "aws.access-analyzer", "Access Preview State Change", {"status": "COMPLETED"}, False),
        ("external_deleted", "aws.access-analyzer", "AWS API Call via CloudTrail", {"eventName": "DeleteAnalyzer"}, True),
        ("external_suppressed", "aws.access-analyzer", "AWS API Call via CloudTrail", {"eventName": "UpdateFindings"}, True),
        ("external_archive_rule", "aws.access-analyzer", "AWS API Call via CloudTrail", {"eventName": "CreateArchiveRule"}, True),
        ("external_read", "aws.access-analyzer", "AWS API Call via CloudTrail", {"eventName": "ListFindings"}, False),
        ("findings", "aws.guardduty", "GuardDuty Finding", {"severity": 8}, True),
        ("findings", "aws.guardduty", "GuardDuty Finding", {"severity": 4}, True),
        ("findings", "aws.guardduty", "GuardDuty Finding", {"severity": 2}, False),
        ("vulnerabilities", "aws.inspector2", "Inspector2 Finding", {"severity": "CRITICAL", "status": "ACTIVE"}, True),
        ("vulnerabilities", "aws.inspector2", "Inspector2 Finding", {"severity": "HIGH", "status": "ACTIVE"}, True),
        ("vulnerabilities", "aws.inspector2", "Inspector2 Finding", {"severity": "MEDIUM", "status": "ACTIVE"}, False),
        ("vulnerabilities", "aws.inspector2", "Inspector2 Finding", {"severity": "CRITICAL", "status": "CLOSED"}, False),
        ("scanning_changes", "aws.inspector2", "AWS API Call via CloudTrail", {"eventName": "Disable"}, True),
        ("scanning_changes", "aws.ecr", "AWS API Call via CloudTrail", {"eventName": "PutRegistryScanningConfiguration"}, True),
        ("scanning_changes", "aws.inspector2", "AWS API Call via CloudTrail", {"eventName": "ListFindings"}, False),
        ("control_changes", "aws.cloudtrail", "AWS API Call via CloudTrail", {"eventName": "StopLogging"}, True),
        ("control_changes", "aws.iam", "AWS API Call via CloudTrail", {"eventName": "GetRole"}, False),
        ("root_activity", "aws.signin", "AWS Console Sign In via CloudTrail", {"userIdentity": {"type": "Root"}}, True),
        ("root_activity", "aws.iam", "AWS API Call via CloudTrail", {"userIdentity": {"type": "AssumedRole"}}, False),
        ("root_activity", "aws.iam", "AWS API Call via CloudTrail", {"userIdentity": {"type": "Root"}, "eventName": "GetRole", "readOnly": True}, False),
        ("root_console_noise", "aws.notifications", "AWS API Call via CloudTrail", {"userIdentity": {"type": "Root"}, "eventName": "ListManagedNotificationEvents", "readOnly": True}, False),
        ("root_write", "aws.iam", "AWS API Call via CloudTrail", {"userIdentity": {"type": "Root"}, "eventName": "CreateRole", "readOnly": False}, True),
        ("root_failed_read", "aws.iam", "AWS API Call via CloudTrail", {"userIdentity": {"type": "Root"}, "eventName": "GetRole", "readOnly": True, "errorCode": "AccessDenied"}, True),
        ("root_login", "aws.signin", "AWS Console Sign In via CloudTrail", {"userIdentity": {"type": "Root"}, "eventName": "ConsoleLogin", "readOnly": True}, True),
        ("root_missing_read_only", "aws.iam", "AWS API Call via CloudTrail", {"userIdentity": {"type": "Root"}, "eventName": "CreateRole"}, True),
    ]
    assert len(set(patterns.values())) == 1, "Every region must use the same combined alert pattern"
    pattern = next(iter(patterns.values()))
    for name, source, detail_type, detail, expected in cases:
        event = {"version": "0", "id": "00000000-0000-0000-0000-000000000000",
                 "account": "873716897517", "time": "2026-01-01T00:00:00Z", "region": "us-east-1",
                 "resources": [], "source": source, "detail-type": detail_type, "detail": detail}
        result = aws("events", "test-event-pattern", "--event-pattern", pattern, "--event", json.dumps(event))
        assert result["Result"] == expected, f"Unexpected match for {name}: {detail}"
    # Validate semantics with the AWS parser: Terraform accepts filter strings
    # that are syntactically valid but never match the intended CloudTrail event.
    metric_cases = {
        "root_usage": {"userIdentity": {"type": "Root"}, "eventType": "AwsApiCall"},
        "unauthorized_calls": {"errorCode": "AccessDeniedException"},
        "iam_policy_changes": {"eventSource": "iam.amazonaws.com", "eventName": "AttachRolePolicy", "readOnly": False},
        "cloudtrail_changes": {"eventSource": "cloudtrail.amazonaws.com", "eventName": "StopLogging"},
        "security_group_changes": {"eventSource": "ec2.amazonaws.com", "eventName": "AuthorizeSecurityGroupIngress"},
        "console_authentication_failures": {"eventName": "ConsoleLogin", "responseElements": {"ConsoleLogin": "Failure"}},
        "iam_trust_changes": {"eventSource": "iam.amazonaws.com", "eventName": "UpdateAssumeRolePolicy"},
        "identity_credential_changes": {"eventSource": "iam.amazonaws.com", "eventName": "DeactivateMFADevice"},
        "s3_policy_changes": {"eventSource": "s3.amazonaws.com", "eventName": "PutBucketPublicAccessBlock"},
        "network_changes": {"eventSource": "ec2.amazonaws.com", "eventName": "ReplaceRoute"},
        "organizations_changes": {"eventSource": "organizations.amazonaws.com", "eventName": "LeaveOrganization"},
        "security_pipeline_changes": {"eventSource": "logs.amazonaws.com", "eventName": "DeleteMetricFilter"},
    }
    additional_metric_cases = {
        "iam_trust_changes": [
            {"eventSource": "iam.amazonaws.com", "eventName": "CreateRole"},
        ],
        "iam_policy_changes": [
            {"eventSource": "iam.amazonaws.com", "eventName": "AddUserToGroup"},
            {"eventSource": "iam.amazonaws.com", "eventName": "RemoveUserFromGroup"},
        ],
        "identity_credential_changes": [
            {"eventSource": "iam.amazonaws.com", "eventName": "CreateAccessKey"},
            {"eventSource": "iam.amazonaws.com", "eventName": "CreateServiceSpecificCredential"},
            {"eventSource": "iam.amazonaws.com", "eventName": "ResetServiceSpecificCredential"},
            {"eventSource": "iam.amazonaws.com", "eventName": "UpdateServiceSpecificCredential"},
            {"eventSource": "iam.amazonaws.com", "eventName": "DeleteServiceSpecificCredential"},
            {"eventSource": "iam.amazonaws.com", "eventName": "UploadSigningCertificate"},
            {"eventSource": "iam.amazonaws.com", "eventName": "UploadSSHPublicKey"},
        ],
        "s3_policy_changes": [
            {"eventSource": "s3.amazonaws.com", "eventName": "DeleteBucketPolicy"},
            {"eventSource": "s3.amazonaws.com", "eventName": "PutBucketEncryption"},
            {"eventSource": "s3.amazonaws.com", "eventName": "DeleteBucketEncryption"},
            {"eventSource": "s3control.amazonaws.com", "eventName": "PutAccessPointPolicy"},
            {"eventSource": "s3control.amazonaws.com", "eventName": "DeletePublicAccessBlock"},
        ],
        "network_changes": [
            {"eventSource": "ec2.amazonaws.com", "eventName": "ReplaceNetworkAclAssociation"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "DetachInternetGateway"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "ModifyVpcAttribute"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "CreateVpcPeeringConnection"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "AcceptVpcPeeringConnection"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "RejectVpcPeeringConnection"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "DeleteVpcPeeringConnection"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "ModifyVpcPeeringConnectionOptions"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "ModifyVpcEndpoint"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "CreateVpcEndpoint"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "DeleteVpcEndpoints"},
            {"eventSource": "ec2.amazonaws.com", "eventName": "ModifyVpcEndpointServicePermissions"},
        ],
        "organizations_changes": [
            {"eventSource": "organizations.amazonaws.com", "eventName": "EnableAWSServiceAccess"},
            {"eventSource": "organizations.amazonaws.com", "eventName": "RegisterDelegatedAdministrator"},
            {"eventSource": "organizations.amazonaws.com", "eventName": "EnablePolicyType"},
            {"eventSource": "organizations.amazonaws.com", "eventName": "CreateAccount"},
            {"eventSource": "organizations.amazonaws.com", "eventName": "CreateGovCloudAccount"},
            {"eventSource": "organizations.amazonaws.com", "eventName": "CloseAccount"},
            {"eventSource": "organizations.amazonaws.com", "eventName": "InviteAccountToOrganization"},
            {"eventSource": "organizations.amazonaws.com", "eventName": "AcceptHandshake"},
        ],
        "security_pipeline_changes": [
            {"eventSource": "config.amazonaws.com", "eventName": "StopConfigurationRecorder"},
            {"eventSource": "config.amazonaws.com", "eventName": "StartConfigurationRecorder"},
            {"eventSource": "config.amazonaws.com", "eventName": "DeleteDeliveryChannel"},
            {"eventSource": "config.amazonaws.com", "eventName": "PutDeliveryChannel"},
            {"eventSource": "config.amazonaws.com", "eventName": "PutConfigurationRecorder"},
            {"eventSource": "config.amazonaws.com", "eventName": "DeleteConformancePack"},
            {"eventSource": "monitoring.amazonaws.com", "eventName": "DisableAlarmActions"},
            {"eventSource": "kms.amazonaws.com", "eventName": "ScheduleKeyDeletion"},
            {"eventSource": "kms.amazonaws.com", "eventName": "TagResource", "readOnly": False},
            {"eventSource": "kms.amazonaws.com", "eventName": "UntagResource", "readOnly": False},
            {"eventSource": "sns.amazonaws.com", "eventName": "Unsubscribe"},
            {"eventSource": "sns.amazonaws.com", "eventName": "SetSubscriptionAttributes"},
            {"eventSource": "events.amazonaws.com", "eventName": "RemoveTargets"},
            {"eventSource": "events.amazonaws.com", "eventName": "DisableRule"},
            {"eventSource": "events.amazonaws.com", "eventName": "DeleteRule"},
            {"eventSource": "events.amazonaws.com", "eventName": "PutTargets"},
            {"eventSource": "events.amazonaws.com", "eventName": "PutRule"},
            {"eventSource": "sqs.amazonaws.com", "eventName": "DeleteQueue"},
            {"eventSource": "sqs.amazonaws.com", "eventName": "PurgeQueue"},
            {"eventSource": "sqs.amazonaws.com", "eventName": "SetQueueAttributes"},
            {"eventSource": "sqs.amazonaws.com", "eventName": "AddPermission"},
            {"eventSource": "sqs.amazonaws.com", "eventName": "RemovePermission"},
        ],
    }
    benign = {"eventSource": "ec2.amazonaws.com", "eventName": "DescribeInstances", "readOnly": True,
              "userIdentity": {"type": "AssumedRole"}}
    metric_checked = 0
    for resource in resources:
        if resource["type"] != "aws_cloudwatch_log_metric_filter" or resource["name"] != "audit":
            continue
        name = resource["index"]
        positive_events = [metric_cases[name], *additional_metric_cases.get(name, [])]
        negative_messages = [json.dumps(benign), json.dumps({"eventName": "ConsoleLogin", "responseElements": {"ConsoleLogin": "Success"}})]
        if "eventSource" in metric_cases[name]:
            negative_messages.append(json.dumps({**metric_cases[name], "eventSource": "unrelated.amazonaws.com"}))
        if name in {"iam_policy_changes", "iam_trust_changes", "identity_credential_changes", "s3_policy_changes", "network_changes", "organizations_changes", "security_pipeline_changes"}:
            for value in (False, "false"):
                event = {**metric_cases[name], "readOnly": value}
                if event not in positive_events:
                    positive_events.append(event)
            for value in (True, "true"):
                negative_messages.append(json.dumps({**metric_cases[name], "readOnly": value}))
        if name == "security_pipeline_changes":
            negative_messages.append(json.dumps({"eventSource": "config.amazonaws.com", "eventName": "DescribeConfigurationRecorders", "readOnly": True}))
        positive_messages = [json.dumps(event) for event in positive_events]
        result = aws("logs", "test-metric-filter", "--filter-pattern", resource["values"]["pattern"],
                     "--log-event-messages", *positive_messages, *negative_messages)
        # Verify the matching payload itself; avoid relying on event-number
        # conventions in API examples or implementations.
        assert [match["eventMessage"] for match in result["matches"]] == positive_messages, f"Unexpected metric matches: {name}: {result}"
        metric_checked += 1
    assert metric_checked == len(metric_cases), "Missing audit metric filters"
    print(f"PASS: {checked} policies, {len(cases)} EventBridge cases, {metric_checked} metric filters; no events published")


if __name__ == "__main__":
    main()
