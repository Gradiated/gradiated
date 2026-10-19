"""Read-only AWS IAM simulations against policies rendered by terraform test -json -verbose."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terraform_test_log", type=Path)
    args = parser.parse_args()
    policies = {}
    for line in args.terraform_test_log.read_text().splitlines():
        event = json.loads(line)
        if event.get("@testrun") != "prepare_boundaries_without_enforcement":
            continue
        for resource in event.get("test_plan", {}).get("resource_changes", []):
            if resource["address"] in ("aws_iam_policy.ci_boundary", "aws_iam_policy.workload_boundary"):
                policies[resource["name"]] = resource["change"]["after"]["policy"]
    assert set(policies) == {"ci_boundary", "workload_boundary"}, "Missing rendered policies"
    for name, policy in policies.items():
        assert len(policy) <= 6144, f"{name} exceeds the IAM managed-policy size limit"
        validation = json.loads(subprocess.check_output([
            "aws", "accessanalyzer", "validate-policy", "--policy-type", "IDENTITY_POLICY",
            "--policy-document", policy, "--output", "json"], text=True))
        errors = [finding for finding in validation["findings"] if finding["findingType"] == "ERROR"]
        assert not errors, f"{name}: {errors}"

    account = "873716897517"
    role = f"arn:aws:iam::{account}:role/"
    policy = f"arn:aws:iam::{account}:policy/"
    boundary = [{"ContextKeyName": "iam:PermissionsBoundary", "ContextKeyType": "string",
                 "ContextKeyValues": [policy + "gradiated-workload-boundary"]}]
    allow_all = json.dumps({"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "*", "Resource": "*"}]})
    cases = [
        ("ci_boundary", "iam:AttachRolePolicy", role + "gradiated-terraform-apply", False, []),
        ("ci_boundary", "iam:PutRolePolicy", role + "gradiated-terraform-apply", False, []),
        ("ci_boundary", "iam:UpdateAssumeRolePolicy", role + "gradiated-terraform-plan", False, []),
        ("ci_boundary", "iam:PassRole", role + "gradiated-security-event-forwarder", False, []),
        ("ci_boundary", "iam:CreatePolicyVersion", policy + "gradiated-terraform-iam", False, []),
        ("ci_boundary", "iam:SetDefaultPolicyVersion", policy + "gradiated-ci-boundary", False, []),
        ("ci_boundary", "iam:DeletePolicy", policy + "gradiated-workload-boundary", False, []),
        ("ci_boundary", "iam:CreateRole", role + "gradiated-prod-new", False, []),
        ("ci_boundary", "iam:CreateRole", role + "gradiated-prod-new", True, boundary),
        ("ci_boundary", "iam:PutRolePermissionsBoundary", role + "gradiated-prod-new", True, boundary),
        ("ci_boundary", "iam:DeleteRolePermissionsBoundary", role + "gradiated-prod-api", False, []),
        ("ci_boundary", "iam:PutRolePolicy", role + "gradiated-prod-api", True, []),
        ("ci_boundary", "iam:CreateUser", f"arn:aws:iam::{account}:user/gradiated-prod-runtime-new", False, []),
        ("ci_boundary", "iam:CreateUser", f"arn:aws:iam::{account}:user/gradiated-prod-runtime-new", True, boundary),
        ("ci_boundary", "s3:PutObject", f"arn:aws:s3:::gradiated-terraform-state-{account}/prod/us-east-1/eks/terraform.tfstate", True, []),
        ("ci_boundary", "s3:PutObject", f"arn:aws:s3:::gradiated-terraform-state-{account}/bootstrap/github-oidc/terraform.tfstate", False, []),
        ("ci_boundary", "s3:PutBucketPolicy", f"arn:aws:s3:::gradiated-terraform-state-{account}", False, []),
        ("ci_boundary", "eks:UpdateClusterVersion", f"arn:aws:eks:us-east-1:{account}:cluster/gradiated-prod", True, []),
        ("workload_boundary", "iam:CreateRole", role + "gradiated-prod-new", False, boundary),
        ("workload_boundary", "iam:PutRolePolicy", role + "gradiated-prod-api", False, []),
        ("workload_boundary", "iam:CreateAccessKey", f"arn:aws:iam::{account}:user/gradiated-prod-runtime-hosts", False, []),
        ("workload_boundary", "iam:GetServerCertificate", f"arn:aws:iam::{account}:server-certificate/example", True, []),
        ("workload_boundary", "ecr:PutImage", f"arn:aws:ecr:us-east-1:{account}:repository/gradiated/prod/product", True, []),
        ("workload_boundary", "s3:GetObject", f"arn:aws:s3:::gradiated-prod-model-artifacts-{account}/example", True, []),
    ]
    cases.extend([
        ("ci_boundary", "iam:PassRole", role + "gradiated-prod-system-node", True,
         [{"ContextKeyName": "iam:PassedToService", "ContextKeyType": "string", "ContextKeyValues": ["ec2.amazonaws.com"]}]),
        ("ci_boundary", "iam:PassRole", role + "Administrator", False,
         [{"ContextKeyName": "iam:PassedToService", "ContextKeyType": "string", "ContextKeyValues": ["ec2.amazonaws.com"]}]),
        ("ci_boundary", "iam:PassRole", role + "gradiated-prod-api", True,
         [{"ContextKeyName": "iam:PassedToService", "ContextKeyType": "string", "ContextKeyValues": ["cloudformation.amazonaws.com"]}]),
        ("workload_boundary", "iam:CreateServiceLinkedRole", "*", True,
         [{"ContextKeyName": "iam:AWSServiceName", "ContextKeyType": "string", "ContextKeyValues": ["elasticloadbalancing.amazonaws.com"]}]),
    ])
    for service in ["sagemaker.amazonaws.com", "batch.amazonaws.com", "lambda.amazonaws.com"]:
        cases.append(("ci_boundary", "iam:PassRole", role + "gradiated-prod-inference", True,
                      [{"ContextKeyName": "iam:PassedToService", "ContextKeyType": "string", "ContextKeyValues": [service]}]))
    for name in policies:
        for action in ["DeleteStack", "ContinueUpdateRollback", "RollbackStack", "CancelUpdateStack", "SignalResource"]:
            cases.append((name, "cloudformation:" + action, f"arn:aws:cloudformation:us-east-1:{account}:stack/example/id", False, []))
        cases.extend([
            (name, "iam:CreateServiceLinkedRole", "*", True,
             [{"ContextKeyName": "iam:AWSServiceName", "ContextKeyType": "string", "ContextKeyValues": ["batch.amazonaws.com"]}]),
            (name, "iam:DeleteServiceLinkedRole", role + "aws-service-role/guardduty.amazonaws.com/AWSServiceRoleForAmazonGuardDuty", False, []),
            (name, "cloudformation:DescribeStacks", f"arn:aws:cloudformation:us-east-1:{account}:stack/example/id", True, []),
            (name, "sts:AssumeRole", role + "gradiated-prod-inference", True, []),
            (name, "sts:AssumeRole", "arn:aws:iam::111122223333:role/gradiated-prod-inference", False, []),
            (name, "kms:UpdateAlias", f"arn:aws:kms:us-east-1:{account}:alias/gradiated-terraform-state", False, []),
            (name, "kms:DeleteAlias", f"arn:aws:kms:us-east-1:{account}:alias/gradiated-terraform-state", False, []),
            (name, "sts:AssumeRole", role + "Administrator", False, []),
            (name, "sso:CreateAccountAssignment", "*", False, []),
            (name, "cloudformation:ExecuteChangeSet", "*", False, []),
            (name, "cloudtrail:StopLogging", f"arn:aws:cloudtrail:us-east-1:{account}:trail/gradiated-security-audit", False, []),
            (name, "guardduty:UpdateDetector", f"arn:aws:guardduty:us-east-1:{account}:detector/example", False, []),
            (name, "inspector2:Disable", "*", False, []),
            (name, "inspector2:CreateFilter", "*", False, []),
            (name, "inspector2:UpdateConfiguration", "*", False, []),
            (name, "inspector2:ListFindings", "*", True, []),
            (name, "ecr:PutRegistryScanningConfiguration", "*", False, []),
            (name, "ecr:PutImageScanningConfiguration", f"arn:aws:ecr:us-east-1:{account}:repository/gradiated/prod/product", True, []),
            (name, "iam:DeleteServiceLinkedRole", role + "aws-service-role/inspector2.amazonaws.com/AWSServiceRoleForAmazonInspector2", False, []),
            (name, "s3:DeleteObjectVersion", f"arn:aws:s3:::gradiated-security-audit-{account}/AWSLogs/example", False, []),
            (name, "events:RemoveTargets", f"arn:aws:events:us-east-1:{account}:rule/gradiated-security-events/gradiated-security-notify", False, []),
            (name, "ec2:DisableEbsEncryptionByDefault", "*", False, []),
            (name, "ec2:ModifyEbsDefaultKmsKeyId", "*", False, []),
            (name, "ec2:ResetEbsDefaultKmsKeyId", "*", False, []),
            (name, "ec2:EnableEbsEncryptionByDefault", "*", True, []),
            (name, "cloudwatch:PutMetricData", "*", False,
             [{"ContextKeyName": "cloudwatch:namespace", "ContextKeyType": "string", "ContextKeyValues": ["Gradiated/Security"]}]),
            (name, "cloudwatch:PutMetricData", "*", True,
             [{"ContextKeyName": "cloudwatch:namespace", "ContextKeyType": "string", "ContextKeyValues": ["Gradiated/Application"]}]),
            (name, "logs:DeleteLogGroup", f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/security/cloudtrail", False, []),
            (name, "logs:DeleteMetricFilter", f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/security/cloudtrail:*", False, []),
            (name, "logs:AssociateKmsKey", f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/security/cloudtrail", False, []),
            (name, "logs:DisassociateKmsKey", f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/security/cloudtrail", False, []),
            (name, "logs:AssociateKmsKey", f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/prod/application", True, []),
            (name, "logs:PutRetentionPolicy", f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/security/cloudtrail", False, []),
            # IAM's simulator returns implicitDeny even for allow-all on a
            # concrete log-stream ARN; use an action-level positive.
            (name, "logs:PutLogEvents", "*", True, []),
            (name, "logs:DeleteLogGroup", f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/prod/application", True, []),
            (name, "sns:Publish", f"arn:aws:sns:us-east-1:{account}:gradiated-security-alerts", False, []),
            (name, "sns:Publish", f"arn:aws:sns:eu-west-1:{account}:gradiated-security-alerts", False, []),
            (name, "sns:Publish", f"arn:aws:sns:us-east-1:{account}:gradiated-prod-application", True, []),
            (name, "cloudwatch:SetAlarmState", f"arn:aws:cloudwatch:us-east-1:{account}:alarm:gradiated-security-root-usage", False, []),
            (name, "cloudwatch:PutMetricAlarm", f"arn:aws:cloudwatch:us-east-1:{account}:alarm:gradiated-security-root-usage", False, []),
            (name, "cloudwatch:SetAlarmState", f"arn:aws:cloudwatch:us-east-1:{account}:alarm:gradiated-prod-example-cpu", True, []),
            (name, "cloudwatch:PutMetricAlarm", f"arn:aws:cloudwatch:us-east-1:{account}:alarm:gradiated-prod-example-cpu", True, []),
            (name, "sns:Unsubscribe", f"arn:aws:sns:us-east-1:{account}:gradiated-security-alerts:example", False, []),
        ])

    for name in policies:
        for action in ["backup:DeleteRecoveryPoint", "backup:UpdateRecoveryPointLifecycle", "backup:DeleteBackupPlan", "backup:DeleteBackupSelection", "backup:PutBackupVaultAccessPolicy", "backup:StartBackupJob", "backup:StartRestoreJob"]:
            cases.append((name, action, "*", False, []))
        cases.append((name, "iam:DeleteServiceLinkedRole", role + "aws-service-role/backup.amazonaws.com/AWSServiceRoleForBackup", False, []))

    for name in policies:
        rule = f"arn:aws:events:us-east-1:{account}:rule/gradiated-prod-example"
        application = f"arn:aws:lambda:us-east-1:{account}:function:gradiated-prod-example"
        security_log = f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/security/cloudtrail"
        for targets, expected in [
            ([security_log], False),
            ([f"arn:aws:sns:us-east-1:{account}:gradiated-security-alerts"], False),
            ([f"arn:aws:events:us-east-1:{account}:event-bus/gradiated-security-events"], False),
            ([application, security_log], False),
            ([application], True),
        ]:
            context = [{"ContextKeyName": "events:TargetArn", "ContextKeyType": "stringList", "ContextKeyValues": targets}]
            cases.append((name, "events:PutTargets", rule, expected, context))

    security_key = f"arn:aws:kms:us-east-1:{account}:key/00000000-0000-0000-0000-000000000002"
    security_tag = [{"ContextKeyName": "aws:ResourceTag/SecurityControl", "ContextKeyType": "string",
                     "ContextKeyValues": ["gradiated-security-alerts"]}]
    for name in policies:
        for action in ["kms:DisableKey", "kms:DisableKeyRotation", "kms:ScheduleKeyDeletion", "kms:PutKeyPolicy", "kms:TagResource", "kms:UntagResource"]:
            cases.append((name, action, security_key, False, security_tag))
        cases.append((name, "kms:GenerateDataKey", security_key, True, security_tag))
        cases.append((name, "kms:DisableKey", security_key, True,
                      [{"ContextKeyName": "aws:ResourceTag/SecurityControl", "ContextKeyType": "string", "ContextKeyValues": ["application"]}]))

    def simulate(case):
        name, action, resource, expected, context = case
        command = ["aws", "iam", "simulate-custom-policy", "--policy-input-list", allow_all,
                   "--permissions-boundary-policy-input-list", policies[name],
                   "--action-names", action, "--resource-arns", resource, "--output", "json"]
        if context:
            command += ["--context-entries", json.dumps(context)]
        result = json.loads(subprocess.check_output(command, text=True))["EvaluationResults"][0]
        allowed = result["EvalDecision"] == "allowed"
        assert allowed == expected, f"{name} {action} {resource}: {result['EvalDecision']} (expected allowed={expected})"
        if not expected and (action.startswith("logs:") or action in ("cloudwatch:PutMetricData", "sns:Publish", "cloudwatch:SetAlarmState", "cloudwatch:PutMetricAlarm", "events:PutTargets") or (action.startswith("kms:") and context)):
            assert result["EvalDecision"] == "explicitDeny", f"Expected a matching security deny, not an unrelated implicit denial: {result}"
        return name, action, allowed

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(simulate, cases))
    # Access Analyzer evaluates stream ARNs that IAM's simulator rejects even with allow-all.
    log_checks = 0
    for name, document in policies.items():
        for namespace, expected in [("security", "PASS"), ("prod", "FAIL")]:
            group = f"arn:aws:logs:us-east-1:{account}:log-group:/gradiated/{namespace}/example"
            for action in ("logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"):
                resource = group if action == "logs:CreateLogGroup" else group + ":log-stream:example"
                access = json.dumps([{"actions": [action], "resources": [resource]}])
                result = json.loads(subprocess.check_output([
                    "aws", "accessanalyzer", "check-access-not-granted", "--policy-type", "IDENTITY_POLICY",
                    "--policy-document", document, "--access", access, "--output", "json"], text=True))
                assert result["result"] == expected, f"{name} {action} {resource}: {result}"
                log_checks += 1
    print(f"PASS: {len(results)} AWS IAM simulations and {log_checks} Access Analyzer log-isolation checks, including malicious AdministratorAccess on workload identities")


if __name__ == "__main__":
    main()
