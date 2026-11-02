"""Test the rendered unauthorized-call filter using AWS's read-only filter engine."""

import argparse
import json
from pathlib import Path
import subprocess


def denial_cases():
    """Return (event, should_alert) cases for the bounded scanner exemption."""
    scanner = {
        "errorCode": "AccessDenied", "readOnly": True,
        "userIdentity": {"type": "AssumedRole", "sessionContext": {"sessionIssuer": {
            "arn": "arn:aws:iam::873716897517:role/gradiated-security-prowler"}}},
    }
    cases = [({"errorCode": "AccessDeniedException"}, True),
             ({"errorCode": "Client.UnauthorizedOperation"}, True),
             ({"eventName": "DescribeInstances", "readOnly": True}, False)]
    for source, operations in {
        "glue.amazonaws.com": ["GetMLTransforms", "SearchTables", "GetDevEndpoints", "GetConnections"],
        "codebuild.amazonaws.com": ["ListReportGroups"],
    }.items():
        for operation in operations:
            expected = {**scanner, "eventSource": source, "eventName": operation}
            cases.append((expected, False))
            # Other identities, sources, denial codes and writes must still alert.
            for difference in [
                {"userIdentity": {"type": "Root"}},
                {"userIdentity": {"sessionContext": {"sessionIssuer": {
                    "arn": "arn:aws:iam::873716897517:role/other"}}}},
                {"eventSource": "other.amazonaws.com"},
                {"readOnly": False}, {"readOnly": "false"},
                {"errorCode": "AccessDeniedException"},
            ]:
                cases.append(({**expected, **difference}, True))
            for missing in ("eventSource", "eventName", "readOnly", "userIdentity"):
                cases.append(({key: value for key, value in expected.items() if key != missing}, True))
    cases.extend([
        ({**scanner, "eventSource": "glue.amazonaws.com", "eventName": "DeleteConnection", "readOnly": False}, True),
        ({**scanner, "eventSource": "s3.amazonaws.com", "eventName": "GetObject"}, True),
    ])
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terraform_test_log", type=Path,
                        help="Output of terraform test -json -verbose in security-audit")
    args = parser.parse_args()
    pattern = None
    with args.terraform_test_log.open() as lines:
        for line in lines:
            event = json.loads(line)
            if event.get("@testrun") != "durable_multi_region_audit_and_notifications":
                continue
            for resource in event.get("test_state", {}).get("root_module", {}).get("resources", []):
                if resource["address"] == 'aws_cloudwatch_log_metric_filter.audit["unauthorized_calls"]':
                    pattern = resource["values"]["pattern"]
    assert pattern, "Missing rendered unauthorized-call metric filter"
    cases = denial_cases()
    for offset in range(0, len(cases), 50):
        batch = cases[offset:offset + 50]
        messages = [json.dumps(event) for event, _ in batch]
        result = json.loads(subprocess.check_output([
            "aws", "logs", "test-metric-filter", "--filter-pattern", pattern,
            "--log-event-messages", *messages, "--output", "json",
        ], text=True))
        actual = [match["eventMessage"] for match in result["matches"]]
        expected = [message for message, (_, alerts) in zip(messages, batch) if alerts]
        assert actual == expected, f"Unexpected denial filter matches in batch {offset}: {actual}"
    print(f"PASS: {len(cases)} unauthorized-call cases through AWS; no events published")


if __name__ == "__main__":
    main()
