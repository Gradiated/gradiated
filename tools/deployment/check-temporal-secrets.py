#!/usr/bin/env python3
"""Read-only reconciliation check; never emit secret values or subprocess errors."""

import argparse
import base64
import json
import subprocess
import sys


def read_json(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError("Unable to read secret state; command output withheld")
    try:
        return json.loads(result.stdout)
    except Exception:
        raise ValueError("Invalid secret response; command output withheld") from None


def check(profile):
    aws = ["aws", "--profile", profile, "--region", "us-east-1"]
    kube = ["kubectl", "--request-timeout=20s", "-n", "gradiated"]
    for name, fields in {
        "temporal": {
            "TEMPORAL_ADDRESS": "address",
            "TEMPORAL_NAMESPACE": "namespace",
            "TEMPORAL_API_KEY": "apiKey",
            "TEMPORAL_PAYLOAD_KEY_ID": "payloadKeyId",
            "TEMPORAL_PAYLOAD_KEYS": "payloadKeys",
        },
        "worker": {"DATABASE_URL": "databaseUrl"},
    }.items():
        external = read_json(kube + ["get", "externalsecret", name, "-o", "json"])
        if not any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in external.get("status", {}).get("conditions", [])
        ):
            raise ValueError(f"ExternalSecret {name} is not Ready")
        secret_name = name
        source = read_json(aws + [
            "secretsmanager", "get-secret-value", "--secret-id",
            f"gradiated/prod/product/{secret_name}", "--output", "json",
        ])
        try:
            source = json.loads(source["SecretString"])
            target = read_json(kube + ["get", "secret", name, "-o", "json"])["data"]
            for field, prop in fields.items():
                actual = base64.b64decode(target[field], validate=True).decode()
                expected = source[prop]
                if prop == "payloadKeys":
                    actual = json.loads(actual)
                    expected = json.loads(expected) if isinstance(expected, str) else expected
                if not expected or actual != expected:
                    raise ValueError()
            if name == "temporal":
                keys = source["payloadKeys"]
                keys = json.loads(keys) if isinstance(keys, str) else keys
                if source["payloadKeyId"] not in keys or not all(
                    len(base64.b64decode(value, validate=True)) == 32
                    for value in keys.values()
                ):
                    raise ValueError()
        except Exception:
            raise ValueError(f"Secret {name} is missing, invalid or differs from Secrets Manager") from None
        print(f"{name}: Ready, required fields valid and reconciled")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="gradiated-admin")
    args = parser.parse_args()
    try:
        check(args.profile)
    except Exception as error:
        print(str(error) if isinstance(error, ValueError) else "Secret check failed; details withheld", file=sys.stderr)
        sys.exit(1)
