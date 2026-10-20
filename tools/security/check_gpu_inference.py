#!/usr/bin/env python3
"""Validate GPU inference manifests against Kubernetes and the pinned operator CRDs."""

import json
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

from check_tailscale_inference import strict_schema

ROOT = Path(__file__).resolve().parents[2]
KUBE = ROOT / "infra/environments/prod/us-east-1/kubernetes"
KUBERNETES_VERSION = re.search(
    r'kubernetes_version\s*=\s*"([0-9.]+)"',
    (ROOT / "infra/environments/prod/us-east-1/terraform/eks/terragrunt.hcl").read_text(),
).group(1)
# Applications whose CRDs the GPU manifests use, and the Applications that deploy them.
OPERATORS = ("argo-rollouts", "keda", "external-secrets")
APPLICATIONS = (
    "argo-rollouts",
    "external-secrets",
    "gpu-inference",
    "inference-hosts",
    "inference-network",
    "keda",
    "tailscale-operator",
    "tailscale-relays",
)


def chart(name):
    application = next(
        item
        for item in yaml.safe_load_all((KUBE / f"platform/{name}.yaml").read_text())
        if item and item["kind"] == "Application"
    )
    sources = application["spec"].get("sources") or [application["spec"]["source"]]
    source = next(source for source in sources if "chart" in source)
    return source, source.get("helm", {}).get("valuesObject", {})


def argocd_chart():
    terraform = (ROOT / "infra/modules/argocd-bootstrap/main.tf").read_text()
    version = re.search(r'chart\s*=\s*"argo-cd"\s*\n\s*version\s*=\s*"([^"]+)"', terraform)
    return {
        "chart": "argo-cd",
        "repoURL": "https://argoproj.github.io/argo-helm",
        "targetRevision": version.group(1),
    }, {}


def crds(source, values, directory):
    values_file = directory / f"{source['chart']}-values.json"
    values_file.write_text(json.dumps(values))
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
            "--values",
            str(values_file),
            "--include-crds",
        ],
        text=True,
        timeout=180,
    )
    return [
        resource
        for resource in yaml.safe_load_all(rendered)
        if resource and resource.get("kind") == "CustomResourceDefinition"
    ]


def main():
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        sources = [chart(name) for name in OPERATORS] + [argocd_chart()]
        for source, values in sources:
            for definition in crds(source, values, directory):
                group = definition["spec"]["group"]
                kind = definition["spec"]["names"]["kind"].lower()
                for version in definition["spec"]["versions"]:
                    path = directory / "schemas" / group / f"{kind}_{version['name']}.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(strict_schema(version["schema"]["openAPIV3Schema"])))
        manifests = sorted((KUBE / "gpu-inference").glob("*.yaml"))
        manifests += sorted((KUBE / "tailscale-inference/hosts").glob("*.yaml"))
        manifests += [KUBE / f"platform/{name}.yaml" for name in APPLICATIONS]
        # No -ignore-missing-schemas: every resource must match a Kubernetes or pinned CRD schema.
        result = subprocess.run(
            [
                "kubeconform",
                "-strict",
                "-summary",
                "-kubernetes-version",
                f"{KUBERNETES_VERSION}.0",
                "-schema-location",
                "default",
                "-schema-location",
                str(directory / "schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"),
                *map(str, manifests),
            ],
            timeout=300,
        )
        if result.returncode:
            raise SystemExit("GPU inference manifests do not match their schemas")
    print("GPU inference manifests match Kubernetes and the pinned operator CRDs")


if __name__ == "__main__":
    main()
