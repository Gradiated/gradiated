#!/usr/bin/env python3
"""Enroll a registered GPU host without changing provider settings or model processes."""

import argparse
import ipaddress
import json
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST = ROOT / "product/inference/tailscale"


def request(url, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode()
    with urllib.request.urlopen(
        urllib.request.Request(url, data=data, headers=headers), timeout=30
    ) as r:
        return json.load(r)


def egress_service(instance, address):
    instance = str(uuid.UUID(instance))
    address = ipaddress.IPv4Address(address)
    if address not in ipaddress.IPv4Network("100.64.0.0/10"):
        raise ValueError("Expected a Tailscale IPv4 address")
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": "gpu-" + instance,
            "namespace": "tailscale-inference",
            "annotations": {
                "tailscale.com/tailnet-ip": str(address),
                "tailscale.com/proxy-group": "inference-egress",
            },
        },
        "spec": {
            "type": "ExternalName",
            "externalName": "unused",
            "ports": [{"name": "inference", "port": 8888, "protocol": "TCP"}],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--key", required=True)
    parser.add_argument("--known-hosts", required=True)
    parser.add_argument("--auth-key-file")
    parser.add_argument("--profile", default="gradiated-admin")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    instance = str(uuid.UUID(args.instance_id))
    token = None
    key_id = None
    if args.auth_key_file:
        auth_path = Path(args.auth_key_file).resolve()
        if auth_path.is_relative_to(ROOT):
            raise ValueError("Keep enrollment credentials outside the checkout")
        auth_key = auth_path.read_text().strip()
    else:
        secret = json.loads(
            subprocess.check_output(
                [
                    "aws",
                    "secretsmanager",
                    "get-secret-value",
                    "--profile",
                    args.profile,
                    "--region",
                    "us-east-1",
                    "--secret-id",
                    "gradiated/prod/platform/tailscale-gpu-enrollment",
                    "--query",
                    "SecretString",
                    "--output",
                    "text",
                ],
                text=True,
                timeout=30,
            )
        )
        data = urllib.parse.urlencode(
            {**secret, "grant_type": "client_credentials"}
        ).encode()
        with urllib.request.urlopen(
            urllib.request.Request(
                "https://api.tailscale.com/api/v2/oauth/token", data=data
            ),
            timeout=30,
        ) as r:
            token = json.load(r)["access_token"]
        key = request(
            "https://api.tailscale.com/api/v2/tailnet/-/keys",
            {
                "capabilities": {
                    "devices": {
                        "create": {
                            "reusable": False,
                            "ephemeral": False,
                            "preauthorized": True,
                            "tags": ["tag:gpu-inference"],
                        }
                    }
                },
                "expirySeconds": 3600,
                "description": "GPU " + instance,
            },
            token,
        )
        auth_key, key_id = key["key"], key["id"]
    if not auth_key.startswith("tskey-auth-"):
        raise ValueError(
            "A scoped auth key is required; OAuth credentials must not reach GPU hosts"
        )
    payload = {
        "instance_id": instance,
        "auth_key": auth_key,
        "scripts": {
            "run-tailscale": (HOST / "run-tailscale.sh").read_text(),
            "start-tailscale": (HOST / "start-tailscale.sh").read_text(),
        },
    }
    script = (HOST / "install-tailscale.py").read_text()
    try:
        result = subprocess.run(
            [
                "ssh",
                "-i",
                args.key,
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "UserKnownHostsFile=" + args.known_hosts,
                "-o",
                "ConnectTimeout=10",
                "-p",
                str(args.port),
                "root@" + args.host,
                "python3 -c " + shlex.quote(script),
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("Pinned SSH installation failed; remote output withheld")
        metadata = json.loads(result.stdout)
        if metadata["instance_id"] != instance:
            raise ValueError("Installed identity mismatch")
        manifest = egress_service(instance, metadata["tailscale_ip"])
        Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
        Path(args.manifest).write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({**metadata, "manifest": args.manifest}))
    finally:
        if token and key_id:
            req = urllib.request.Request(
                "https://api.tailscale.com/api/v2/tailnet/-/keys/" + key_id,
                method="DELETE",
                headers={"Authorization": "Bearer " + token},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    r.read()
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise RuntimeError("GPU enrollment key revocation failed") from None


if __name__ == "__main__":
    main()
