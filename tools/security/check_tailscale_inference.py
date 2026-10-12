#!/usr/bin/env python3
"""Validate egress and relay resources against the pinned operator CRDs."""

import subprocess
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]


def strict_schema(value):
    if isinstance(value, list):
        return [strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    result = {key: strict_schema(item) for key, item in value.items()}
    if (
        result.get("type") == "object"
        and "properties" in result
        and "additionalProperties" not in result
        and not result.get("x-kubernetes-preserve-unknown-fields")
    ):
        result["additionalProperties"] = False
    return result


def main():
    applications = yaml.safe_load_all(
        (
            ROOT
            / "infra/environments/prod/us-east-1/kubernetes/platform/tailscale-operator.yaml"
        ).read_text()
    )
    operator = next(
        app for app in applications if app["metadata"]["name"] == "tailscale-operator"
    )
    source = next(source for source in operator["spec"]["sources"] if "chart" in source)
    rendered = subprocess.check_output(
        [
            "helm",
            "template",
            "schema-check",
            source["chart"],
            "--repo",
            source["repoURL"],
            "--version",
            source["targetRevision"],
            "--include-crds",
        ],
        text=True,
        timeout=120,
    )
    schemas = {
        resource["spec"]["names"]["kind"]: strict_schema(
            resource["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
        )
        for resource in yaml.safe_load_all(rendered)
        if resource and resource.get("kind") == "CustomResourceDefinition"
    }
    for directory in ("tailscale-inference", "tailscale-relays"):
        manifests = (
            ROOT
            / f"infra/environments/prod/us-east-1/kubernetes/{directory}/proxies.yaml"
        )
        for resource in yaml.safe_load_all(manifests.read_text()):
            if resource and resource["kind"] in schemas:
                jsonschema.validate(resource, schemas[resource["kind"]])
    print(
        "Egress and relay CRDs match the pinned operator, including unknown-field checks"
    )


if __name__ == "__main__":
    main()
