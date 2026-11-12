"""Select product checks from changed paths and workspace dependencies."""

from __future__ import annotations

import json
import os
import subprocess
from lockfiles import expand_lockfile
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMMON = (
    ".github/workflows/tests.yml",
    ".github/actions/product-changes/*",
    ".github/actions/relevant/*",
    ".github/actions/rust-cache/*",
    "tools/ci/*",
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
# Model definitions and prices reach other services through the database at
# deploy time, not through code or fixtures, so they need only the TypeScript
# checks of control and its consumers.
CATALOG_MODELS = (
    "product/packages/control/src/catalog/models/*",
    "product/packages/control/test/catalog-models.test.ts",
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
    "native_kev": ("product/inference/runtimes/kev/*", "product/inference/runtimes/decider/*"),
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
        "tools/browser/website_screenshots.py",
    ),
    "tooling": (
        "product/scripts/*",
        "product/mprocs.yaml",
        "product/tsconfig.scripts.json",
        "tools/deployment/*",
        "tools/docs-refresh/*",
        "tools/github-apps/*",
        "tools/images/*",
        "tools/model-radar/*",
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


def unit_matrix(packages):
    rust = {"@gradiated/credentials", "@gradiated/gateway", "@gradiated/proxy", "@gradiated/collector"}
    groups = [{"name": name.rsplit("/", 1)[-1], "packages": [name], "rust": True, "target_minutes": 10}
              for name in packages if name in rust]
    remaining = [name for name in packages if name not in rust]
    for name in ("@gradiated/temporal-worker", "@gradiated/control"):
        if name in remaining:
            groups.append({"name": name.rsplit("/", 1)[-1], "packages": [name], "rust": False, "target_minutes": 5})
            remaining.remove(name)
    for index in range(min(2, len(remaining))):
        groups.append({"name": f"typescript-{index + 1}", "packages": remaining[index::2], "rust": False, "target_minutes": 5})
    return {"include": groups}


def plan(paths: list[str], root: Path = ROOT, force: bool = False) -> dict:
    formatting = any(path.startswith("product/") and "/screenshots/" not in path for path in paths)
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
    cross_service = [path for path in paths if not matches(path, CATALOG_MODELS)]
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
        if any(matches(path, scopes) for path in cross_service):
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
        job: all_checks or any(matches(path, scopes) for path in cross_service)
        for job, scopes in JOB_PATHS.items()
    }
    result["format"] = formatting or all_checks
    result["packages"] = checked
    result["unit_matrix"] = unit_matrix(checked) if checked else {}
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
    result["console_build"] = "@gradiated/console" in selected or "tools/deployment/console-artifact.mjs" in paths
    result["website"] |= "gradiated-com" in selected
    result["inference_native"] = any(
        result[key] for key in ("native_cpp", "native_kev")
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


def plan_changed_paths(paths, base=None, root=ROOT, force=False):
    result = plan(expand_lockfile(paths, base, root), root=root, force=force)
    # The production console artifact includes the entire frozen lockfile.
    # Other checks still use importer closures to avoid unrelated backend/GPU work.
    result["console_build"] |= "product/pnpm-lock.yaml" in paths
    return result


def main() -> None:
    paths, force = changed_paths()
    result = plan_changed_paths(paths, os.environ.get("BASE"), force=force)
    print(json.dumps(result, indent=2))
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in result.items():
            output.write(f"{key}={json.dumps(value, separators=(',', ':'))}\n")


if __name__ == "__main__":
    main()
