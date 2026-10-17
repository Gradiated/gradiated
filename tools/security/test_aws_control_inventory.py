import json
import subprocess
import unittest
from unittest.mock import patch

import aws_control_inventory as inventory


class InventorySafetyTests(unittest.TestCase):
    def test_rejects_mutation_and_secret_reads_before_invoking_cli(self):
        with patch.object(inventory.subprocess, "run") as run:
            for service, operation in [("ec2", "delete-vpc"), ("secretsmanager", "get-secret-value"), ("s3api", "get-object")]:
                with self.assertRaises(inventory.AuditError):
                    inventory.aws(service, operation)
            run.assert_not_called()

    def test_permission_denial_stops_collection_and_hides_cli_stderr(self):
        replies = [subprocess.CompletedProcess([], 0, json.dumps({"Account": inventory.ACCOUNT}), ""),
                   subprocess.CompletedProcess([], 254, "", "An error occurred (AccessDeniedException): sensitive-value-that-must-stay-hidden")]
        with patch.object(inventory.subprocess, "run", side_effect=replies) as run:
            with self.assertRaises(inventory.AuditError) as error:
                inventory.collect()
            self.assertEqual(run.call_count, 2)
            self.assertIn("ec2 describe-regions: AccessDeniedException", str(error.exception))
            self.assertNotIn("sensitive-value", str(error.exception))

    def test_wrong_account_stops_before_resource_reads(self):
        reply = subprocess.CompletedProcess([], 0, json.dumps({"Account": "000000000000"}), "")
        with patch.object(inventory.subprocess, "run", return_value=reply) as run:
            with self.assertRaisesRegex(inventory.AuditError, "Wrong AWS account"):
                inventory.collect()
            self.assertEqual(run.call_count, 1)

    def test_missing_password_policy_is_absence_not_denial(self):
        reply = subprocess.CompletedProcess([], 254, "", "An error occurred (NoSuchEntity): policy absent")
        with patch.object(inventory.subprocess, "run", return_value=reply):
            self.assertIsNone(inventory.aws("iam", "get-account-password-policy", missing=("NoSuchEntity",)))

    def test_permission_denial_cannot_be_classified_as_missing(self):
        reply = subprocess.CompletedProcess([], 254, "", "An error occurred (AccessDeniedException): denied")
        with patch.object(inventory.subprocess, "run", return_value=reply):
            with self.assertRaisesRegex(inventory.AuditError, "AccessDeniedException"):
                inventory.aws("iam", "get-account-password-policy", missing=("AccessDeniedException",))

    def test_empty_s3_optional_configuration_is_disabled(self):
        reply = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(inventory.subprocess, "run", return_value=reply):
            for operation in ["get-bucket-logging", "get-bucket-versioning"]:
                self.assertEqual(inventory.aws("s3api", operation, "--bucket", "example"), {})

    def test_unexpected_empty_metadata_does_not_masquerade_as_absent_resources(self):
        reply = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(inventory.subprocess, "run", return_value=reply):
            with self.assertRaisesRegex(inventory.AuditError, "empty metadata response"):
                inventory.collect()

    def test_invalid_metadata_does_not_echo_response_content(self):
        reply = subprocess.CompletedProcess([], 0, "sensitive-response-must-not-appear", "")
        with patch.object(inventory.subprocess, "run", return_value=reply):
            with self.assertRaises(inventory.AuditError) as error:
                inventory.aws("sts", "get-caller-identity")
            self.assertIn("invalid metadata JSON", str(error.exception))
            self.assertNotIn("sensitive-response", str(error.exception))

    def test_guardduty_route_distinguishes_findings_from_api_events(self):
        self.assertTrue(inventory.has_guardduty_findings({"$or": [{"source": ["aws.guardduty"], "detail-type": ["GuardDuty Finding"]}]}))
        self.assertFalse(inventory.has_guardduty_findings({"source": ["aws.guardduty"], "detail-type": ["AWS API Call via CloudTrail"]}))

    def test_non_primary_region_workloads_and_alb_children_keep_region(self):
        responses = {
            ("ec2", "describe-instances"): [{"id": "i-regional", "state": "running", "tags": [{"Key": "eks:cluster-name", "Value": "example"}]}],
            ("rds", "describe-db-instances"): {"DBInstances": [{"DBInstanceIdentifier": "regional-db", "MultiAZ": False}]},
            ("elbv2", "describe-load-balancers"): {"LoadBalancers": [{"Type": "application", "LoadBalancerArn": "regional-alb"}]},
            ("elbv2", "describe-target-groups"): {"TargetGroups": [{"TargetGroupArn": "regional-target", "TargetGroupName": "target"}]},
            ("elbv2", "describe-tags"): {"TagDescriptions": [{"Tags": []}]},
            ("elbv2", "describe-listeners"): {"Listeners": [{"Port": 80, "Protocol": "HTTP", "DefaultActions": [{"Type": "redirect"}]}]},
        }

        def read(service, operation, *args, **kwargs):
            self.assertEqual(kwargs["region"], "eu-west-1")
            return responses[(service, operation)]

        with patch.object(inventory, "aws", side_effect=read) as read_mock:
            facts = inventory.regional_workloads("eu-west-1")
        self.assertEqual(read_mock.call_count, 6)
        self.assertTrue(facts["instances"][0]["eks"])
        for kind in ("instances", "databases", "albs"):
            self.assertEqual(facts[kind][0]["region"], "eu-west-1")
        self.assertEqual(facts["albs"][0]["target_groups"][0]["arn"], "regional-target")
        self.assertEqual(facts["albs"][0]["listeners"][0]["default_actions"], ["redirect"])

    def test_collects_central_bus_and_human_confirmation_without_endpoint_values(self):
        topic = "arn:aws:sns:us-east-1:873716897517:gradiated-security-alerts"
        calls = []

        def read(service, operation, *args, **kwargs):
            calls.append((service, operation, args, kwargs))
            if (service, operation) == ("events", "list-rules"):
                if "gradiated-security-events" in args:
                    return {"Rules": [{"Name": "gradiated-security-notify", "State": "ENABLED", "EventPattern": "{}"}]}
                return {"Rules": []}
            responses = {
                ("sts", "get-caller-identity"): {"Account": inventory.ACCOUNT},
                ("ec2", "describe-regions"): {"Regions": [{"RegionName": "us-east-1"}, {"RegionName": "eu-west-1"}]},
                ("guardduty", "list-detectors"): {"DetectorIds": []},
                ("sns", "list-topics"): {"Topics": [{"TopicArn": topic}]},
                ("sns", "list-subscriptions-by-topic"): {"Subscriptions": [
                    {"SubscriptionArn": topic + ":confirmed", "Protocol": "email", "Endpoint": "security@gradiated.com"},
                    {"SubscriptionArn": "PendingConfirmation", "Protocol": "https", "Endpoint": "sensitive-endpoint-must-not-appear"}]},
                ("events", "list-targets-by-rule"): {"Targets": [{"Arn": topic}]},
                ("cloudwatch", "describe-alarms"): {"MetricAlarms": []},
                ("ec2", "describe-network-interfaces"): [], ("ec2", "describe-instances"): [],
                ("ec2", "describe-security-groups"): {"SecurityGroups": []},
                ("ec2", "describe-vpcs"): {"Vpcs": []}, ("ec2", "describe-flow-logs"): {"FlowLogs": []},
                ("ec2", "describe-network-acls"): {"NetworkAcls": []},
                ("ec2", "get-ebs-encryption-by-default"): {"EbsEncryptionByDefault": True},
                ("rds", "describe-db-instances"): {"DBInstances": []},
                ("iam", "get-account-summary"): {"SummaryMap": {"AccountMFAEnabled": 1}},
                ("iam", "get-account-password-policy"): None, ("iam", "list-users"): {"Users": []},
                ("iam", "list-roles"): {"Roles": []},
                ("cloudtrail", "describe-trails"): {"trailList": []},
                ("s3api", "list-buckets"): {"Buckets": []},
                ("elbv2", "describe-load-balancers"): {"LoadBalancers": []},
            }
            return responses[(service, operation)]

        with patch.object(inventory, "aws", side_effect=read):
            snapshot = inventory.collect()
        facts = snapshot["regions"]["us-east-1"]
        self.assertTrue(facts["topics"][0]["security_email_confirmed"])
        self.assertEqual(facts["topics"][0]["pending"], 1)
        self.assertEqual(facts["rules"][0]["bus"], "gradiated-security-events")
        self.assertNotIn("sensitive-endpoint", json.dumps(snapshot))
        for service, operation in [("ec2", "describe-instances"), ("rds", "describe-db-instances"), ("elbv2", "describe-load-balancers"), ("cloudtrail", "describe-trails")]:
            self.assertEqual({kwargs.get("region") for s, o, args, kwargs in calls if (s, o) == (service, operation)}, {"us-east-1", "eu-west-1"})
        self.assertTrue(any(service == "events" and operation == "list-targets-by-rule" and "gradiated-security-events" in args for service, operation, args, kwargs in calls))


if __name__ == "__main__":
    unittest.main()
