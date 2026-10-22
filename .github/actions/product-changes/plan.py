"""Select product checks from changed paths and workspace dependencies."""

from __future__ import annotations

import json
import os
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMMON = (
    ".github/workflows/tests.yml",
    ".github/actions/product-changes/*",
    ".github/actions/relevant/*",
    ".cargo/config.toml",
    "mise.toml",
    "product/package.json",
    "product/pnpm-lock.yaml",
    "product/pnpm-workspace.yaml",
    "product/tsconfig.base.json",
    "product/turbo.json",
    "product/prettier.config.mjs",
    "product/.prettierignore",
    "product/.nvmrc",
)
STORAGE = (
    "product/packages/control/*",
    "product/packages/valkey/*",
    "product/packages/contracts/*",
    "product/packages/config/*",
)
GATEWAY = ("product/services/gateway/*", *STORAGE)
PROXY = ("product/services/proxy/*", *GATEWAY, "product/packages/credentials/*")
COLLECTOR = ("product/services/collector/*", *PROXY)
RUNTIMES = ("product/inference/runtimes/kev/*", "product/inference/runtimes/vllm/*")
JOB_PATHS = {
    "integration": (*GATEWAY, "product/docker-compose.yml"),
    "native_cpp": (
        "product/inference/CMakeLists.txt",
        "product/inference/desmond/*",
        "product/inference/engine/*",
    ),
    "native_vllm": ("product/inference/runtimes/vllm/*",),
    "native_kev": ("product/inference/runtimes/kev/*",),
    "gateway_contract": (*GATEWAY, *RUNTIMES, "product/docker-compose.yml"),
    "proxy_e2e": (
        *PROXY,
        "product/docker-compose.yml",
        "infra/environments/prod/us-east-1/kubernetes/workloads/proxy.yaml",
        "infra/environments/prod/us-east-1/kubernetes/workloads/public-api.yaml",
    ),
    "backend_storage": (
        *COLLECTOR,
        "product/services/worker/*",
        "product/docker-compose.yml",
    ),
    "inference_e2e": (*GATEWAY, *RUNTIMES, "product/scripts/run-kev-gateway-e2e.mjs"),
    "playwright": (
        "product/services/api/*",
        "product/services/console/*",
        "product/services/ops-mcp/*",
        "product/packages/*",
        "product/docker-compose.yml",
    ),
    "website": (
        "product/website/*",
        "product/services/api/generated/openapi.json",
        "product/packages/contracts/*",
        ".github/workflows/website-screenshots.yml",
        "tools/browser/website_screenshots.py",
    ),
    "tooling": (
        "product/scripts/*",
        "product/mprocs.yaml",
        "product/tsconfig.scripts.json",
        "tools/deployment/*",
        "tools/github-apps/*",
        "tools/images/*",
        "product/packages/contracts/*",
        ".github/workflows/application-deployment.yml",
        ".github/workflows/build-images.yml",
        "product/Dockerfile",
        "product/.dockerignore",
        "product/services/rust-service.Dockerfile",
        "product/inference/gpu/*",
        "product/inference/images/gpu-base/*",
        "product/inference/host/*",
    ),
}


def matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def workspaces(root: Path) -> dict[str, tuple[str, dict]]:
    manifests = [
        *root.glob("product/packages/*/package.json"),
        *root.glob("product/services/*/package.json"),
        root / "product/website/package.json",
    ]
    return {
        manifest["name"]: (str(path.parent.relative_to(root)), manifest)
        for path in manifests
        for manifest in [json.loads(path.read_text())]
    }


def plan(paths: list[str], root: Path = ROOT, force: bool = False) -> dict:
    paths = [
        path
        for path in paths
        if not path.endswith(".md") and "/screenshots/" not in path
    ]
    # A leaf manifest affects its workspace and consumers, just like its source.
    # Removed workspaces cannot be recovered from the current dependency graph.
    removed_manifest = any(
        matches(path, ("product/packages/*/package.json", "product/services/*/package.json"))
        and not (root / path).exists()
        for path in paths
    )
    all_checks = force or removed_manifest or any(matches(path, COMMON) for path in paths)
    packages = workspaces(root)
    selected = {
        name
        for name, (directory, _) in packages.items()
        if all_checks or any(path.startswith(directory + "/") for path in paths)
    }
    # Cargo and cross-service test fixtures are not represented in package.json.
    for name, scopes in (
        ("@gradiated/gateway", STORAGE),
        ("@gradiated/proxy", STORAGE),
        ("@gradiated/collector", STORAGE),
        (
            "@gradiated/api",
            (
                "product/services/gateway/src/http.rs",
                "product/services/gateway/test/fixtures/systemone-request.*.json",
                "infra/environments/prod/us-east-1/kubernetes/workloads/proxy.yaml",
                "infra/environments/prod/us-east-1/kubernetes/workloads/public-api.yaml",
            ),
        ),
    ):
        if any(matches(path, scopes) for path in paths):
            selected.add(name)
    while True:
        dependents = {
            name
            for name, (_, manifest) in packages.items()
            if any(
                dependency in selected
                for section in (
                    "dependencies",
                    "devDependencies",
                    "optionalDependencies",
                )
                for dependency in manifest.get(section, {})
            )
        }
        if dependents <= selected:
            break
        selected |= dependents

    checked = sorted(
        name
        for name in selected
        if "check" in packages[name][1].get("scripts", {})
        and name != "@gradiated/wizard"
    )
    result = {
        job: all_checks or any(matches(path, scopes) for path in paths)
        for job, scopes in JOB_PATHS.items()
    }
    result["packages"] = checked
    result["unit"] = bool(checked)
    result["rust"] = bool(
        set(checked)
        & {
            "@gradiated/credentials",
            "@gradiated/gateway",
            "@gradiated/proxy",
            "@gradiated/collector",
            "@gradiated/control",
        }
    )
    result["website"] |= "gradiated-com" in selected
    result["inference_native"] = any(
        result[key] for key in ("native_cpp", "native_vllm", "native_kev")
    )
    return result


def changed_paths() -> tuple[list[str], bool]:
    event = os.environ["EVENT"]
    if event == "workflow_dispatch":
        return [], True
    if event == "pull_request":
        command = [
            "gh",
            "api",
            "--paginate",
            f"repos/{os.environ['REPOSITORY']}/pulls/{os.environ['PULL_REQUEST']}/files",
            "--jq",
            ".[] | .filename, (.previous_filename // empty)",
        ]
    elif event == "push":
        before, head = os.environ["BEFORE"], os.environ["HEAD"]
        if not before or set(before) == {"0"}:
            return [], True
        command = ["git", "diff", "--name-only", "--no-renames", before, head]
    else:
        raise ValueError(f"Unsupported event: {event}")

    return subprocess.check_output(command, text=True, cwd=ROOT).splitlines(), False


def main() -> None:
    paths, force = changed_paths()
    result = plan(paths, force=force)
    print(json.dumps(result, indent=2))
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in result.items():
            output.write(f"{key}={json.dumps(value, separators=(',', ':'))}\n")


if __name__ == "__main__":
    main()
