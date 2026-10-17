#!/usr/bin/env python3
"""Read AWS control metadata; never read secrets, object contents, or log events."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ACCOUNT = "873716897517"
REGION = "us-east-1"
READS = {
    "sts": {"get-caller-identity"},
    "ec2": {"describe-regions", "describe-vpcs", "describe-network-interfaces", "describe-security-groups", "describe-network-acls", "describe-flow-logs", "describe-instances", "get-ebs-encryption-by-default"},
    "guardduty": {"list-detectors", "get-detector"},
    "sns": {"list-topics", "list-subscriptions-by-topic"},
    "events": {"list-rules", "list-targets-by-rule"},
    "cloudwatch": {"describe-alarms"},
    "rds": {"describe-db-instances"},
    "cloudtrail": {"describe-trails", "get-trail-status", "get-event-selectors"},
    "iam": {"get-account-summary", "get-account-password-policy", "list-users", "list-roles", "get-role", "list-attached-role-policies", "get-policy", "get-policy-version", "list-role-policies", "get-role-policy"},
    "s3api": {"list-buckets", "get-bucket-location", "get-bucket-versioning", "get-bucket-logging", "get-bucket-encryption", "get-bucket-lifecycle-configuration"},
    "elbv2": {"describe-load-balancers", "describe-target-groups", "describe-listeners", "describe-tags"},
}


class AuditError(RuntimeError):
    pass


def aws(service, operation, *args, region=REGION, missing=()):
    if operation not in READS.get(service, set()):
        raise AuditError(f"Refused non-inventory operation: {service} {operation}")
    command = ["aws", service, operation, "--region", region, "--output", "json", "--no-cli-pager", "--cli-connect-timeout", "10", "--cli-read-timeout", "20", *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45,
                                env={**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off", "AWS_MAX_ATTEMPTS": "1"})
    except subprocess.TimeoutExpired:
        raise AuditError(f"{service} {operation}: timeout ({region}); inventory stopped") from None
    if result.returncode:
        match = re.search(r"An error occurred \(([A-Za-z0-9_.-]+)\)", result.stderr)
        code = match.group(1) if match else "CLIError"
        if code in missing and code in {"NoSuchEntity", "ResourceNotFoundException", "NoSuchLifecycleConfiguration", "ServerSideEncryptionConfigurationNotFoundError"}:
            return None
        # Do not echo CLI stderr: it is not needed to identify a denied operation.
        raise AuditError(f"{service} {operation}: {code} ({region}); inventory stopped")
    if not result.stdout.strip():
        if (service, operation) in {("s3api", "get-bucket-logging"), ("s3api", "get-bucket-versioning")}:
            # AWS CLI emits no JSON for these legitimate empty configurations.
            return {}
        raise AuditError(f"{service} {operation}: empty metadata response ({region}); inventory stopped")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AuditError(f"{service} {operation}: invalid metadata JSON ({region}); inventory stopped") from None


def select(record, *fields):
    return {field: record.get(field) for field in fields}


def has_guardduty_findings(pattern):
    if isinstance(pattern, dict):
        if "aws.guardduty" in pattern.get("source", []) and "GuardDuty Finding" in pattern.get("detail-type", []):
            return True
        return any(has_guardduty_findings(value) for value in pattern.values())
    return isinstance(pattern, list) and any(has_guardduty_findings(value) for value in pattern)


def regional_workloads(region):
    instances_result = []
    instances = aws("ec2", "describe-instances", "--filters", "Name=instance-state-name,Values=running,stopped", "--query", "Reservations[].Instances[].{id:InstanceId,tags:Tags,state:State.Name}", region=region)
    for instance in instances:
        tags = {t["Key"]: t["Value"] for t in instance.get("tags") or []}
        instances_result.append({"region": region, "id": instance["id"], "state": instance["state"], "eks": "eks:cluster-name" in tags or "aws:eks:cluster-name" in tags,
                                    "asg": tags.get("aws:autoscaling:groupName")})
    databases_result = [{"region": region, **select(d, "DBInstanceIdentifier", "DBInstanceClass", "MultiAZ", "AvailabilityZone", "AllocatedStorage", "StorageType", "Iops", "StorageThroughput", "StorageEncrypted", "PubliclyAccessible", "BackupRetentionPeriod")}
                           for d in aws("rds", "describe-db-instances", region=region)["DBInstances"]]
    albs_result = []
    for lb in aws("elbv2", "describe-load-balancers", region=region)["LoadBalancers"]:
        if lb["Type"] != "application":
            continue
        targets = aws("elbv2", "describe-target-groups", "--load-balancer-arn", lb["LoadBalancerArn"], region=region)["TargetGroups"]
        groups = []
        for group in targets:
            tags = aws("elbv2", "describe-tags", "--resource-arns", group["TargetGroupArn"], region=region)["TagDescriptions"][0]["Tags"]
            groups.append({"arn": group["TargetGroupArn"], "name": group["TargetGroupName"], "tracking_tags": {t["Key"]: t["Value"] for t in tags if t["Key"] in ("elbv2.k8s.aws/cluster", "gateway.k8s.aws.alb/stack", "gateway.k8s.aws.alb/resource")}})
        listeners = aws("elbv2", "describe-listeners", "--load-balancer-arn", lb["LoadBalancerArn"], region=region)["Listeners"]
        albs_result.append({"region": region, **select(lb, "LoadBalancerName", "LoadBalancerArn", "SecurityGroups", "VpcId"), "target_groups": groups,
                                "listeners": [{"port": listener["Port"], "protocol": listener["Protocol"], "default_actions": [a["Type"] for a in listener["DefaultActions"]]} for listener in listeners]})
    return {"instances": instances_result, "databases": databases_result, "albs": albs_result}


def policy_action_summary(documents):
    """Summarize action namespaces, never policy resources or condition values.

    This is an input to a service-boundary review, not effective IAM evaluation.
    In particular an Allow/NotAction statement permits unlisted services.
    """
    services, not_actions = set(), set()
    for document in documents:
        if isinstance(document, str):
            try:
                document = json.loads(unquote(document))
            except (json.JSONDecodeError, TypeError):
                raise AuditError("Invalid IAM policy metadata; inventory stopped") from None
        if not isinstance(document, dict):
            raise AuditError("Invalid IAM policy metadata; inventory stopped")
        statements = document.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        for statement in statements:
            if statement.get("Effect") != "Allow":
                continue
            actions = statement.get("Action", [])
            exclusions = statement.get("NotAction", [])
            services.update(a.split(":", 1)[0] for a in ([actions] if isinstance(actions, str) else actions))
            not_actions.update([exclusions] if isinstance(exclusions, str) else exclusions)
    return {"allow_action_services": sorted(services), "allow_not_actions": sorted(not_actions)}


def role_permission_inputs(name, attached_policies, boundary_arn, policy_cache):
    def managed(arn):
        if arn not in policy_cache:
            version = aws("iam", "get-policy", "--policy-arn", arn)["Policy"]["DefaultVersionId"]
            document = aws("iam", "get-policy-version", "--policy-arn", arn, "--version-id", version)["PolicyVersion"]["Document"]
            policy_cache[arn] = policy_action_summary([document])
        return policy_cache[arn]

    identity = [managed(p["PolicyArn"]) for p in attached_policies]
    inline = aws("iam", "list-role-policies", "--role-name", name)["PolicyNames"]
    inline_documents = [aws("iam", "get-role-policy", "--role-name", name, "--policy-name", policy)["PolicyDocument"] for policy in inline]
    identity.append(policy_action_summary(inline_documents))
    return {
        "name": name,
        "identity_allow_action_services": sorted({service for p in identity for service in p["allow_action_services"]}),
        "identity_allow_not_actions": sorted({action for p in identity for action in p["allow_not_actions"]}),
        "boundary_arn": boundary_arn,
        "boundary_actions": managed(boundary_arn) if boundary_arn else None,
    }


def collect():
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != ACCOUNT:
        raise AuditError("Wrong AWS account; inventory stopped before resource reads")
    names = sorted(r["RegionName"] for r in aws("ec2", "describe-regions", "--filters", "Name=opt-in-status,Values=opt-in-not-required,opted-in")["Regions"])
    result = {"account": ACCOUNT, "collected_at": datetime.now(timezone.utc).isoformat(), "regions": {}}
    for region in names:
        workloads = regional_workloads(region)
        detectors = [select(aws("guardduty", "get-detector", "--detector-id", detector, region=region), "Status", "FindingPublishingFrequency", "Features")
                     for detector in aws("guardduty", "list-detectors", region=region)["DetectorIds"]]
        topics = []
        for topic in aws("sns", "list-topics", region=region)["Topics"]:
            arn = topic["TopicArn"]
            if not arn.rsplit(":", 1)[-1].startswith("gradiated-security-"):
                continue
            subscriptions = aws("sns", "list-subscriptions-by-topic", "--topic-arn", arn, region=region)["Subscriptions"]
            topics.append({"arn": arn, "confirmed": sum(s["SubscriptionArn"].startswith("arn:") for s in subscriptions),
                           "pending": sum(s["SubscriptionArn"] == "PendingConfirmation" for s in subscriptions),
                           "confirmed_protocols": sorted({s["Protocol"] for s in subscriptions if s["SubscriptionArn"].startswith("arn:")}),
                           "security_email_confirmed": any(s["SubscriptionArn"].startswith("arn:") and s["Protocol"] == "email" and s["Endpoint"].lower() == "security@gradiated.com" for s in subscriptions)})
        rules = []
        buses = ["default", "gradiated-security-events"] if region == REGION else ["default"]
        for bus in buses:
            found = aws("events", "list-rules", "--event-bus-name", bus, "--name-prefix", "gradiated-security-", region=region, missing=("ResourceNotFoundException",))
            for rule in (found or {}).get("Rules", []):
                if has_guardduty_findings(json.loads(rule.get("EventPattern", "{}"))) or rule["Name"] == "gradiated-security-notify":
                    targets = aws("events", "list-targets-by-rule", "--event-bus-name", bus, "--rule", rule["Name"], region=region)["Targets"]
                    rules.append({"name": rule["Name"], "bus": bus, "state": rule["State"], "targets": [t["Arn"] for t in targets]})
        alarms = [select(a, "AlarmName", "Namespace", "MetricName", "Dimensions", "AlarmActions", "ActionsEnabled", "StateValue", "Threshold", "ComparisonOperator")
                  for a in aws("cloudwatch", "describe-alarms", region=region)["MetricAlarms"] if a["AlarmName"].startswith("gradiated-")]
        interfaces = aws("ec2", "describe-network-interfaces", "--query", "NetworkInterfaces[].{id:NetworkInterfaceId,vpc:VpcId,groups:Groups[].GroupId}", region=region)
        groups = aws("ec2", "describe-security-groups", region=region)["SecurityGroups"]
        defaults = []
        http = []
        for group in groups:
            if group["GroupName"] == "default":
                defaults.append({"id": group["GroupId"], "vpc": group["VpcId"], "ingress_rules": len(group["IpPermissions"]), "egress_rules": len(group["IpPermissionsEgress"]),
                                 "attached_interfaces": sum(group["GroupId"] in interface["groups"] for interface in interfaces)})
            for permission in group["IpPermissions"]:
                if permission["IpProtocol"] == "-1" or (permission["IpProtocol"] in ("tcp", "6") and permission.get("FromPort", 65536) <= 80 <= permission.get("ToPort", -1)):
                    if any(r.get("CidrIp") == "0.0.0.0/0" for r in permission.get("IpRanges", [])) or any(r.get("CidrIpv6") == "::/0" for r in permission.get("Ipv6Ranges", [])):
                        http.append(select(group, "GroupId", "GroupName", "VpcId"))
                        break
        vpcs = [{**select(v, "VpcId", "IsDefault", "CidrBlock"), "interfaces": sum(i["vpc"] == v["VpcId"] for i in interfaces)}
                for v in aws("ec2", "describe-vpcs", region=region)["Vpcs"]]
        flow = [select(f, "ResourceId", "TrafficType", "FlowLogStatus", "DeliverLogsStatus", "LogDestinationType")
                for f in aws("ec2", "describe-flow-logs", region=region)["FlowLogs"]]
        acls = [select(a, "NetworkAclId", "VpcId", "IsDefault", "Entries") for a in aws("ec2", "describe-network-acls", region=region)["NetworkAcls"]]
        result["regions"][region] = {**workloads, "guardduty": detectors, "topics": topics, "rules": rules, "alarms": alarms, "vpcs": vpcs,
                                     "default_security_groups": defaults, "public_http_security_groups": http, "flow_logs": flow, "network_acls": acls,
                                     "default_ebs_encryption": aws("ec2", "get-ebs-encryption-by-default", region=region)["EbsEncryptionByDefault"]}
    for kind in ("instances", "databases", "albs"):
        result[kind] = [item for facts in result["regions"].values() for item in facts[kind]]
    result["root_mfa_enabled"] = aws("iam", "get-account-summary")["SummaryMap"].get("AccountMFAEnabled")
    result["password_policy"] = aws("iam", "get-account-password-policy", missing=("NoSuchEntity",))
    result["iam_users"] = [u["UserName"] for u in aws("iam", "list-users")["Users"]]
    result["broad_managed_roles"] = []
    result["role_permission_inputs"] = []
    policy_cache = {}
    for role in aws("iam", "list-roles")["Roles"]:
        if role.get("Path", "").startswith("/aws-service-role/"):
            continue
        policies = aws("iam", "list-attached-role-policies", "--role-name", role["RoleName"])["AttachedPolicies"]
        broad = [p["PolicyArn"] for p in policies if p["PolicyName"] in ("AdministratorAccess", "PowerUserAccess", "IAMFullAccess")]
        relevant = role["RoleName"].startswith("gradiated-prod-") or role["RoleName"] == "gradiated-terraform-apply"
        if broad or relevant:
            details = aws("iam", "get-role", "--role-name", role["RoleName"])["Role"]
        if broad:
            result["broad_managed_roles"].append({"name": role["RoleName"], "policies": broad, "boundary": details.get("PermissionsBoundary")})
        if relevant:
            boundary = details.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
            result["role_permission_inputs"].append(role_permission_inputs(role["RoleName"], policies, boundary, policy_cache))
    result["trails"] = []
    for region in names:
        for trail in aws("cloudtrail", "describe-trails", "--no-include-shadow-trails", region=region)["trailList"]:
            status = aws("cloudtrail", "get-trail-status", "--name", trail["TrailARN"], region=region)
            result["trails"].append({"region": region, **select(trail, "Name", "TrailARN", "IsMultiRegionTrail", "KmsKeyId", "S3BucketName"),
                                      "status": select(status, "IsLogging", "LatestDeliveryTime", "LatestCloudWatchLogsDeliveryTime"),
                                      "delivery_errors": {"s3": bool(status.get("LatestDeliveryError")), "cloudwatch": bool(status.get("LatestCloudWatchLogsDeliveryError"))},
                                      "selectors": aws("cloudtrail", "get-event-selectors", "--trail-name", trail["TrailARN"], region=region)})
    result["buckets"] = []
    for bucket in aws("s3api", "list-buckets")["Buckets"]:
        name = bucket["Name"]
        location = aws("s3api", "get-bucket-location", "--bucket", name).get("LocationConstraint")
        region = "eu-west-1" if location == "EU" else location or REGION
        versioning = aws("s3api", "get-bucket-versioning", "--bucket", name, region=region)
        logging = aws("s3api", "get-bucket-logging", "--bucket", name, region=region)
        encryption = aws("s3api", "get-bucket-encryption", "--bucket", name, region=region, missing=("ServerSideEncryptionConfigurationNotFoundError",))
        lifecycle = aws("s3api", "get-bucket-lifecycle-configuration", "--bucket", name, region=region, missing=("NoSuchLifecycleConfiguration",))
        result["buckets"].append({"name": name, "region": region, "versioning": versioning.get("Status", "Disabled"), "log_target": logging.get("LoggingEnabled", {}).get("TargetBucket"),
                                  "encryption": encryption, "lifecycle": [{"id": r.get("ID"), "status": r["Status"], "noncurrent_expiration": r.get("NoncurrentVersionExpiration"), "expiration": r.get("Expiration")} for r in (lifecycle or {}).get("Rules", [])]})
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


def summary(inventory):
    lines = ["### Read-only AWS control inventory", "", f"Account: `{inventory['account']}`; collected: `{inventory['collected_at']}`.",
             "", "This is AWS configuration metadata, not a Drata result or proof of notification delivery. Root MFA metadata does not establish hardware MFA. Broad managed policies require effective-policy review; the list is not an exhaustive least-privilege assessment.",
             "", "| Region | Enabled detectors | Confirmed/pending security subscriptions | VPCs | Default groups with rules / attached | Alarms |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for region, facts in inventory["regions"].items():
        groups = facts["default_security_groups"]
        lines.append(f"| {region} | {sum(d['Status'] == 'ENABLED' for d in facts['guardduty'])} | {sum(t['confirmed'] for t in facts['topics'])}/{sum(t['pending'] for t in facts['topics'])} | {len(facts['vpcs'])} | {sum(bool(g['ingress_rules'] or g['egress_rules']) for g in groups)}/{sum(bool(g['attached_interfaces']) for g in groups)} | {len(facts['alarms'])} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    try:
        inventory = collect()
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.summary:
        with args.summary.open("a") as stream:
            stream.write(summary(inventory))
    print("AWS_CONTROL_INVENTORY_JSON=" + json.dumps(inventory, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
