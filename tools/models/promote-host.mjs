import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { bundles, shared } from "./release.mjs";
import { catalog } from "../images/catalog.mjs";

export const hostPins =
  "infra/environments/prod/us-east-1/kubernetes/gpu-inference/pins.json";
export const hostReleasePaths = [
  hostPins,
  "infra/environments/prod/us-east-1/kubernetes/gpu-inference/gpu-fleet-pins.yaml",
  "infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml",
];
const inputs = [...shared, ...bundles.host];
const gatewayManifest =
  "infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml";
const hostBuildInputs = [
  ...inputs.filter((file) => file !== gatewayManifest),
  ...catalog["gpu-base"].paths,
  "tools/images/catalog.mjs",
];
const hostPayloadInputs = [
  "product/inference/bundles/package.sh",
  "product/inference/images/gpu-base/base-id",
  "product/inference/CMakeLists.txt",
  "product/inference/desmond/CMakeLists.txt",
  "product/inference/desmond/src",
  "product/inference/desmond/include",
  "product/inference/engine/src",
  "product/inference/engine/include",
  "product/inference/gpu/host-agent.py",
  "product/inference/gpu/host_state.py",
  "product/inference/gpu/host_bundle.py",
  "product/inference/gpu/supervise.py",
  "product/inference/gpu/fetch-runtime.sh",
  "product/inference/gpu/download-runtime.py",
  "product/inference/runtime-launcher/CMakeLists.txt",
  "product/inference/runtime-launcher/main.cpp",
  "product/inference/runtime-launcher/supervise.cpp",
  "product/inference/runtime-launcher/supervise.h",
];
const sha = (value) => /^[0-9a-f]{40}$/.test(value ?? "");

export const promoteHost = ({ source, releaseFile, root = process.cwd() }) => {
  const git = (...args) =>
    execFileSync("git", args, {
      cwd: root,
      encoding: "utf8",
      stdio: "pipe",
    }).trim();
  const run = (command, args) =>
    spawnSync(command, args, { cwd: root, encoding: "utf8", stdio: "pipe" });
  const ancestor = (before, after) => {
    const result = run("git", ["merge-base", "--is-ancestor", before, after]);
    if (result.status !== 0 && result.status !== 1)
      throw new Error("Cannot determine host release ancestry");
    return result.status === 0;
  };
  const sameInputs = (before, after, paths) =>
    git("diff", "--name-only", before, after, "--", ...paths) === "";
  const readPins = (revision) =>
    JSON.parse(git("show", `${revision}:${hostPins}`));
  // Application release commits update this image without rerunning model publication.
  const gatewayContract = (revision) =>
    git("show", `${revision}:${gatewayManifest}`).replace(
      /(image:\s+\S+\/gateway@sha256:)[0-9a-f]{64}/g,
      "$1<release>",
    );
  const packageStage = (revision) => {
    const stages = git(
      "show",
      `${revision}:product/inference/bundles/host/Dockerfile`,
    ).split(/^FROM\s+runtime-base\s+AS\s+verify\s*$/im);
    if (stages.length !== 2)
      throw new Error("Cannot identify the host package stage");
    return stages[0];
  };
  const release = JSON.parse(readFileSync(releaseFile, "utf8"));
  if (
    !sha(source) ||
    !sha(release.source) ||
    release.bundle !== "host" ||
    release.bootstrapVersion !== 1 ||
    !/^[0-9a-f]{64}$/.test(release.sha256 ?? "") ||
    !/^[A-Za-z0-9._-]{1,64}$/.test(release.baseId ?? "") ||
    !/@sha256:[0-9a-f]{64}$/.test(release.baseImage ?? "")
  )
    throw new Error("Invalid published host release");
  if (git("status", "--porcelain", "--untracked-files=no"))
    throw new Error("Host release requires a clean checkout");
  const target = { sha256: release.sha256, baseId: release.baseId };
  git("fetch", "origin", "main");
  if (
    !ancestor(source, "origin/main") ||
    !ancestor(release.source, source) ||
    !sameInputs(release.source, source, inputs)
  )
    throw new Error("Host artifact does not match the main source inputs");
  if (
    git("show", `${source}:product/inference/images/gpu-base/base-id`) !==
    release.baseId
  )
    throw new Error("Host release ABI does not match its source");

  for (let attempt = 0; attempt < 3; attempt++) {
    git("fetch", "origin", "main");
    if (
      !sameInputs(source, "origin/main", hostBuildInputs) ||
      gatewayContract(source) !== gatewayContract("origin/main")
    )
      return { promoted: false, reason: "newer host build inputs on main" };
    const current = readPins("origin/main");
    if (current.hostBundle.baseId !== release.baseId)
      throw new Error(
        "Host base ABI changed; migrate the host image explicitly",
      );
    if (JSON.stringify(current.hostBundle) === JSON.stringify(target))
      return { promoted: false, reason: "bundle already pinned" };
    const pinHistory = git(
      "log",
      "--format=%H",
      "origin/main",
      "--",
      hostPins,
    ).split("\n");
    const pinChange = pinHistory[0];
    const message = git("show", "-s", "--format=%B", pinChange);
    const previous = message.match(/^Host-Source: ([0-9a-f]{40})$/m)?.[1];
    // Verification inputs can rebuild a release without changing its payload.
    // A manual pin needs changed shipped inputs and an archive not discarded during this hold.
    const discarded = new Set();
    if (!previous) {
      for (const revision of pinHistory.slice(1)) {
        const digest = readPins(revision).hostBundle?.sha256;
        if (digest) discarded.add(digest);
        if (
          /^Host-Source: [0-9a-f]{40}$/m.test(
            git("show", "-s", "--format=%B", revision),
          )
        )
          break;
      }
    }
    const payloadChanged =
      !sameInputs(pinChange, source, hostPayloadInputs) ||
      packageStage(pinChange) !== packageStage(source);
    const supersedesPin = previous
      ? ancestor(previous, source)
      : ancestor(pinChange, source) &&
        payloadChanged &&
        !discarded.has(release.sha256);
    if (!supersedesPin)
      return {
        promoted: false,
        reason: "newer promotion or manual host pin change",
      };
    // This runs only in a pristine release checkout. Regenerate on current main
    // instead of rebasing generated YAML over concurrent application releases.
    git("checkout", "--detach", "origin/main");
    git("reset", "--hard", "origin/main");
    const pin = run("python3", [
      "tools/gpu/pin-host.py",
      path.resolve(releaseFile),
    ]);
    if (pin.status !== 0)
      throw new Error(`Host pin rendering failed: ${pin.stderr}`);
    const updated = JSON.parse(readFileSync(path.join(root, hostPins), "utf8"));
    if (
      updated.image !== current.image ||
      updated.imageDigest !== current.imageDigest ||
      JSON.stringify(updated.hostBundle) !== JSON.stringify(target)
    )
      throw new Error("Host promotion changed unexpected pins");
    const changed = git("diff", "--name-only").split("\n").filter(Boolean);
    if (
      !changed.length ||
      changed.some((file) => !hostReleasePaths.includes(file))
    )
      throw new Error(
        "Host promotion changed files outside its release manifests",
      );
    git("config", "user.name", "github-actions[bot]");
    git(
      "config",
      "user.email",
      "41898282+github-actions[bot]@users.noreply.github.com",
    );
    git("add", "--", ...hostReleasePaths);
    git(
      "commit",
      "-m",
      `deploy(prod): host bundle ${source.slice(0, 12)} [skip ci]\n\nHost-Source: ${source}`,
    );
    const pushed = run("git", ["push", "origin", "HEAD:refs/heads/main"]);
    if (pushed.status === 0)
      return { promoted: true, commit: git("rev-parse", "HEAD") };
    if (attempt === 2)
      throw new Error(
        "Could not publish the host release after three attempts",
      );
  }
};

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  console.log(
    JSON.stringify(
      promoteHost({
        source: process.env.SOURCE_SHA,
        releaseFile: process.argv[2],
      }),
    ),
  );
