#!/usr/bin/env python3
"""Select an EKS AMI recommendation after seven days of regional availability."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import sys


def select_release(parameter, current, kubernetes_version, now):
    if not re.fullmatch(r"\d+\.\d+", kubernetes_version):
        raise ValueError("Invalid Kubernetes version")

    pattern = re.compile(rf"{re.escape(kubernetes_version)}\.(\d+)-(\d{{8}})")

    def release_key(value):
        match = pattern.fullmatch(value)
        if not match:
            raise ValueError("AMI release does not match the node group's Kubernetes version")
        date = datetime.strptime(match[2], "%Y%m%d")
        return int(match[1]), date

    expected_name = (
        f"/aws/service/eks/optimized-ami/{kubernetes_version}"
        "/amazon-linux-2023/x86_64/standard/recommended/release_version"
    )
    if parameter.get("Name") != expected_name or parameter.get("Type") != "String":
        raise ValueError("Unexpected EKS recommendation parameter")

    latest = parameter["Value"]
    latest_key, current_key = release_key(latest), release_key(current)
    available = datetime.fromisoformat(parameter["LastModifiedDate"].replace("Z", "+00:00"))
    if available.tzinfo is None or now.tzinfo is None or available > now:
        raise ValueError("Invalid recommendation availability timestamp")

    if latest_key <= current_key:
        return None, f"Keep {current}; recommendation {latest} is not newer."

    # The date in the release name predates regional publication. SSM's timestamp
    # is conservative: republishing the parameter restarts the waiting period.
    eligible = available + timedelta(days=7)
    if now < eligible:
        return None, f"Keep {current}; {latest} becomes eligible at {eligible.isoformat()}."

    return latest, f"Select {latest}; recommended since {available.isoformat()}."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True)
    parser.add_argument("--kubernetes-version", required=True)
    args = parser.parse_args()
    try:
        latest, reason = select_release(
            json.load(sys.stdin), args.current, args.kubernetes_version, datetime.now(timezone.utc)
        )
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Cannot select an AMI release: {error}\n")
    print(reason, file=sys.stderr)
    if latest:
        print(latest)


if __name__ == "__main__":
    main()
