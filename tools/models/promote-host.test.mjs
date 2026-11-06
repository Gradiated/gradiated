import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import test from "node:test";
import { hostPins, hostReleasePaths, promoteHost } from "./promote-host.mjs";
import { releaseKey } from "./release.mjs";

const fixture = (t) => {
  const runtime = path.resolve(".agents/runtime");
  mkdirSync(runtime, { recursive: true });
  const root = mkdtempSync(path.join(runtime, "host-promotion-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const checkout = path.join(root, "checkout");
  const remote = path.join(root, "origin.git");
  const git = (cwd, ...args) =>
    execFileSync("git", args, { cwd, encoding: "utf8", stdio: "pipe" }).trim();
  git(root, "init", "--bare", "--initial-branch=main", remote);
  git(root, "clone", remote, checkout);
  const archive = execFileSync(
    "git",
    [
      "archive",
      "HEAD",
      "--",
      "tools/gpu/render-config.py",
      "tools/gpu/pin-host.py",
      "tools/images/catalog.mjs",
      "tools/models/release.mjs",
      ".github/workflows/model-deployment.yml",
      "tools/virtual-kubelet/host_agent_test.py",
      "tools/virtual-kubelet/host_state_test.py",
      "product/inference/bundles/host/Dockerfile",
      "product/inference/gpu/runtimes.json",
      "product/inference/gpu/host-agent.py",
      // render-config.py checks GLM SGLang runtime limits against the launcher.
      "product/inference/runtimes/glm-sglang/config.py",
      "product/inference/images/gpu-base/base-id",
      "infra/environments/prod/us-east-1/kubernetes/gpu-inference",
      "infra/environments/prod/us-east-1/kubernetes/platform/gpu-models.yaml",
      "infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml",
      "infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml",
      "infra/environments/prod/runpod/templates.json",
    ],
    { maxBuffer: 8 * 1024 * 1024 },
  );
  execFileSync("tar", ["-x", "-C", checkout], { input: archive });
  git(checkout, "config", "user.name", "Fixture");
  git(checkout, "config", "user.email", "fixture@example.invalid");
  git(checkout, "add", ".");
  git(checkout, "commit", "-m", "Initial manual pins");
  const host = path.join(checkout, "product/inference/gpu/host-agent.py");
  writeFileSync(
    host,
    readFileSync(host, "utf8") + "\n# New reviewed host input.\n",
  );
  git(checkout, "add", ".");
  git(checkout, "commit", "-m", "Reviewed host source");
  git(checkout, "push", "origin", "main");
  const source = git(checkout, "rev-parse", "HEAD");
  const pins = JSON.parse(readFileSync(path.join(checkout, hostPins), "utf8"));
  const releaseFile = path.join(root, "release.json");
  const release = {
    bundle: "host",
    bootstrapVersion: 1,
    source,
    sha256: "b".repeat(64),
    baseId: pins.hostBundle.baseId,
    baseImage: `registry/base@sha256:${"a".repeat(64)}`,
  };
  writeFileSync(releaseFile, JSON.stringify(release));
  const run = (revision = source) =>
    promoteHost({ source: revision, releaseFile, root: checkout });
  const writer = () => {
    const directory = path.join(root, "writer");
    git(root, "clone", remote, directory);
    git(directory, "config", "user.name", "Other writer");
    git(directory, "config", "user.email", "other@example.invalid");
    return directory;
  };
  const commit = (directory, file, contents, message = "Concurrent change") => {
    writeFileSync(path.join(directory, file), contents);
    git(directory, "add", ".");
    git(directory, "commit", "-m", message);
    git(directory, "push", "origin", "HEAD:main");
    return git(directory, "rev-parse", "HEAD");
  };
  return {
    root,
    checkout,
    remote,
    git,
    source,
    pins,
    release,
    releaseFile,
    run,
    writer,
    commit,
  };
};

test("records only the host bundle and generated copies on main, preserving provider capacity", (t) => {
  const f = fixture(t);
  const result = f.run();
  assert.equal(result.promoted, true);
  assert.equal(
    f.git(f.root, "--git-dir", f.remote, "rev-parse", "main"),
    result.commit,
  );
  const pins = JSON.parse(
    f.git(f.root, "--git-dir", f.remote, "show", `main:${hostPins}`),
  );
  assert.deepEqual(pins, {
    ...f.pins,
    hostBundle: { sha256: f.release.sha256, baseId: f.release.baseId },
  });
  const changed = f
    .git(f.checkout, "diff", "--name-only", "HEAD^", "HEAD")
    .split("\n");
  assert.deepEqual(changed.sort(), [...hostReleasePaths].sort());
  assert.match(f.git(f.checkout, "log", "-1", "--format=%B"), /\[skip ci\]/);
  assert.match(
    f.git(f.checkout, "log", "-1", "--format=%B"),
    new RegExp(`Host-Source: ${f.source}`),
  );
  assert.equal(f.run().reason, "bundle already pinned");
});

test("regenerates against concurrent application configuration without overwriting it", (t) => {
  const f = fixture(t);
  const writer = f.writer();
  const file = hostReleasePaths[2];
  const before = readFileSync(path.join(writer, file), "utf8");
  const updated = before.replace(
    /(image: \S+\/product@sha256:)[a-f0-9]{64}/g,
    `$1${"c".repeat(64)}`,
  );
  assert.notEqual(updated, before);
  const gatewayFile =
    "infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml";
  const gateway = readFileSync(path.join(writer, gatewayFile), "utf8");
  const gatewayImage = gateway.replace(
    /(image: \S+\/gateway@sha256:)[a-f0-9]{64}/g,
    `$1${"c".repeat(64)}`,
  );
  assert.notEqual(gatewayImage, gateway);
  writeFileSync(path.join(writer, gatewayFile), gatewayImage);
  f.commit(writer, file, updated);
  assert.equal(f.run().promoted, true);
  assert.ok(f.git(f.checkout, "show", `HEAD:${file}`).includes("c".repeat(64)));
  assert.ok(
    f.git(f.checkout, "show", `HEAD:${gatewayFile}`).includes("c".repeat(64)),
  );
  f.git(writer, "pull", "--ff-only", "origin", "main");
  const changedContract = gatewayImage.replace(
    'GATEWAY_GENERATION_TIMEOUT_SECONDS: "630"',
    'GATEWAY_GENERATION_TIMEOUT_SECONDS: "629"',
  );
  assert.notEqual(changedContract, gatewayImage);
  f.commit(writer, gatewayFile, changedContract);
  assert.equal(f.run().reason, "newer host build inputs on main");
});

test("skips a stale build after newer host inputs land", (t) => {
  const f = fixture(t);
  f.commit(
    f.writer(),
    "product/inference/gpu/host-agent.py",
    "newer host source\n",
  );
  assert.equal(f.run().reason, "newer host build inputs on main");
});

test("workflow changes invalidate cached releases without repinning unchanged host payload", (t) => {
  const f = fixture(t);
  assert.equal(f.run().promoted, true);
  const before = releaseKey("host", f.source, f.release.baseImage, f.checkout);
  const writer = f.writer();
  const file = ".github/workflows/model-deployment.yml";
  const contents = readFileSync(path.join(writer, file), "utf8");
  const updated = contents.replace(
    "target: artifact",
    "target: artifact\n          build-args: HOST_RELEASE_TEST=1",
  );
  assert.notEqual(updated, contents);
  const source = f.commit(writer, file, updated);
  f.git(f.checkout, "fetch", "origin", "main");
  assert.notEqual(
    releaseKey("host", source, f.release.baseImage, f.checkout),
    before,
  );
  assert.equal(f.run().reason, "newer host build inputs on main");
  assert.throws(() => f.run(source), /artifact does not match/);
  writeFileSync(
    f.releaseFile,
    JSON.stringify({ ...f.release, source, sha256: "e".repeat(64) }),
  );
  assert.deepEqual(f.run(source), {
    promoted: false,
    reason: "host payload and base inputs unchanged",
  });
});

test("accepts cached equivalent source but rejects an artifact from different host code", (t) => {
  const f = fixture(t);
  const writer = f.writer();
  const equivalent = f.commit(writer, "unrelated.txt", "unrelated\n");
  assert.equal(f.run(equivalent).promoted, true);
  f.git(writer, "pull", "--ff-only", "origin", "main");
  const changed = f.commit(
    writer,
    "product/inference/gpu/host-agent.py",
    "different host code\n",
  );
  assert.throws(() => f.run(changed), /artifact does not match/);
});

test("does not replace an automatic host pin for model-only rebuild inputs", (t) => {
  for (const file of [
    "tools/models/release.mjs",
    "product/inference/bundles/build.hcl",
  ]) {
    const f = fixture(t);
    assert.equal(f.run().promoted, true);
    const writer = f.writer();
    const source = f.commit(
      writer,
      file,
      file.endsWith(".mjs")
        ? readFileSync(path.join(writer, file), "utf8") +
            "\n// Register a model bundle.\n"
        : 'target "verify-another-model" {}\n',
    );
    writeFileSync(
      f.releaseFile,
      JSON.stringify({ ...f.release, source, sha256: "e".repeat(64) }),
    );
    const before = f.git(f.root, "--git-dir", f.remote, "rev-parse", "main");
    assert.equal(f.run(source).promoted, false);
    assert.equal(
      f.git(f.root, "--git-dir", f.remote, "rev-parse", "main"),
      before,
    );
  }
});

test("can update an automatic host pin after genuine payload or base changes", (t) => {
  for (const file of [
    "product/inference/gpu/host-agent.py",
    "product/inference/images/gpu-base/Dockerfile",
    "product/inference/bundles/host/Dockerfile",
  ]) {
    const f = fixture(t);
    assert.equal(f.run().promoted, true);
    const writer = f.writer();
    const source = f.commit(
      writer,
      file,
      file.endsWith("bundles/host/Dockerfile")
        ? readFileSync(path.join(writer, file), "utf8").replace(
            "FROM runtime-base AS verify",
            "RUN /bin/true\n\nFROM runtime-base AS verify",
          )
        : "# Changed reviewed host or base build input.\n",
    );
    writeFileSync(
      f.releaseFile,
      JSON.stringify({ ...f.release, source, sha256: "e".repeat(64) }),
    );
    assert.equal(f.run(source).promoted, true);
  }
});

test("refuses incompatible bases, invalid artifacts and source outside main", (t) => {
  const f = fixture(t);
  for (const invalid of [
    { ...f.release, baseId: "different-base" },
    { ...f.release, bundle: "training" },
    { ...f.release, sha256: "bad" },
    { ...f.release, bootstrapVersion: 2 },
  ]) {
    writeFileSync(f.releaseFile, JSON.stringify(invalid));
    assert.throws(() => f.run(), /ABI|Invalid published/);
  }
  writeFileSync(f.releaseFile, JSON.stringify(f.release));
  f.git(f.checkout, "commit", "--allow-empty", "-m", "Unmerged change");
  assert.throws(
    () => f.run(f.git(f.checkout, "rev-parse", "HEAD")),
    /main source/,
  );
});

test("preserves manual pin overrides made after the source was merged", (t) => {
  const f = fixture(t);
  f.commit(
    f.writer(),
    hostPins,
    JSON.stringify({
      ...f.pins,
      hostBundle: { ...f.pins.hostBundle, sha256: "d".repeat(64) },
    }),
  );
  assert.equal(f.run().reason, "newer promotion or manual host pin change");
});

test("retains a manual rollback across later unrelated releases until host inputs change", (t) => {
  const f = fixture(t);
  assert.equal(f.run().promoted, true);
  const writer = f.writer();
  writeFileSync(path.join(writer, hostPins), JSON.stringify(f.pins));
  execFileSync("python3", ["tools/gpu/render-config.py"], { cwd: writer });
  f.commit(
    writer,
    hostPins,
    JSON.stringify(f.pins),
    "Roll back the faulty host bundle",
  );
  const unrelated = f.commit(
    writer,
    "unrelated-model.txt",
    "unrelated model release\n",
  );
  for (let attempt = 0; attempt < 2; attempt++) {
    assert.equal(
      f.run(unrelated).reason,
      "newer promotion or manual host pin change",
    );
    assert.equal(
      f.git(f.root, "--git-dir", f.remote, "rev-parse", "main"),
      unrelated,
    );
    assert.deepEqual(
      JSON.parse(
        f.git(f.root, "--git-dir", f.remote, "show", `main:${hostPins}`),
      ),
      f.pins,
    );
  }
  const manual = {
    ...f.pins,
    hostBundle: { ...f.pins.hostBundle, sha256: "d".repeat(64) },
  };
  writeFileSync(path.join(writer, hostPins), JSON.stringify(manual));
  execFileSync("python3", ["tools/gpu/render-config.py"], { cwd: writer });
  f.commit(
    writer,
    hostPins,
    JSON.stringify(manual),
    "Select another manual fallback",
  );
  const fixed = f.commit(
    writer,
    "product/inference/gpu/host-agent.py",
    "fixed reviewed host code\n",
  );
  writeFileSync(f.releaseFile, JSON.stringify({ ...f.release, source: fixed }));
  assert.equal(
    f.run(fixed).reason,
    "newer promotion or manual host pin change",
  );
  writeFileSync(
    f.releaseFile,
    JSON.stringify({ ...f.release, source: fixed, sha256: "e".repeat(64) }),
  );
  assert.equal(f.run(fixed).promoted, true);
});

test("does not automate a host image ABI migration", (t) => {
  const f = fixture(t);
  f.commit(
    f.writer(),
    hostPins,
    JSON.stringify({
      ...f.pins,
      hostBundle: { ...f.pins.hostBundle, baseId: "new-base" },
    }),
  );
  assert.throws(() => f.run(), /migrate the host image explicitly/);
});

test("unrelated catalog and base-image changes cannot supersede a manual rollback", (t) => {
  const f = fixture(t);
  assert.equal(f.run().promoted, true);
  const writer = f.writer();
  writeFileSync(path.join(writer, hostPins), JSON.stringify(f.pins));
  execFileSync("python3", ["tools/gpu/render-config.py"], { cwd: writer });
  f.commit(writer, hostPins, JSON.stringify(f.pins), "Manual host rollback");
  const catalogFile = "tools/images/catalog.mjs";
  const before = readFileSync(path.join(writer, catalogFile), "utf8");
  const changed = before.replace(
    'context: "infra/images/falco"',
    'context: "infra/images/new-falco"',
  );
  assert.notEqual(changed, before);
  const unrelated = f.commit(writer, catalogFile, changed);
  assert.equal(
    f.run(unrelated).reason,
    "newer promotion or manual host pin change",
  );
  const baseFile = "product/inference/images/gpu-base/Dockerfile";
  const base = f.commit(writer, baseFile, "# base-image-only change\n");
  assert.equal(f.run(base).reason, "newer promotion or manual host pin change");
  assert.deepEqual(
    JSON.parse(
      f.git(f.root, "--git-dir", f.remote, "show", `main:${hostPins}`),
    ),
    f.pins,
  );
});

test("validation, release tooling and documentation changes retain a manual rollback", (t) => {
  const f = fixture(t);
  assert.equal(f.run().promoted, true);
  const writer = f.writer();
  writeFileSync(path.join(writer, hostPins), JSON.stringify(f.pins));
  execFileSync("python3", ["tools/gpu/render-config.py"], { cwd: writer });
  f.commit(writer, hostPins, JSON.stringify(f.pins), "Manual rollback");
  const paths = [
    "tools/virtual-kubelet/host_agent_test.py",
    "tools/virtual-kubelet/host_state_test.py",
    "infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml",
    "tools/models/release.mjs",
    ".github/workflows/model-deployment.yml",
    "product/inference/runtime-launcher/README.md",
    "product/inference/bundles/host/Dockerfile",
  ];
  for (const file of paths) {
    mkdirSync(path.dirname(path.join(writer, file)), { recursive: true });
    const before = file.endsWith("README.md")
      ? ""
      : readFileSync(path.join(writer, file), "utf8");
    const contents = file.endsWith("Dockerfile")
      ? before.replace(
          "FROM runtime-base AS verify",
          "FROM runtime-base AS verify\n# Verification-only change",
        )
      : `${before}\n${file.endsWith(".mjs") ? "//" : "#"} Verification or documentation-only change\n`;
    const source = f.commit(writer, file, contents);
    for (const digest of [f.release.sha256, "e".repeat(64)]) {
      writeFileSync(
        f.releaseFile,
        JSON.stringify({ ...f.release, source, sha256: digest }),
      );
      assert.equal(
        f.run(source).reason,
        "newer promotion or manual host pin change",
        file,
      );
    }
    assert.deepEqual(
      JSON.parse(
        f.git(f.root, "--git-dir", f.remote, "show", `main:${hostPins}`),
      ),
      f.pins,
    );
  }
  const restored = {
    ...f.pins,
    hostBundle: { sha256: f.release.sha256, baseId: f.release.baseId },
  };
  writeFileSync(path.join(writer, hostPins), JSON.stringify(restored));
  execFileSync("python3", ["tools/gpu/render-config.py"], { cwd: writer });
  const explicit = f.commit(
    writer,
    hostPins,
    JSON.stringify(restored),
    "Explicitly restore the old bundle",
  );
  writeFileSync(
    f.releaseFile,
    JSON.stringify({ ...f.release, source: explicit }),
  );
  assert.equal(f.run(explicit).reason, "bundle already pinned");
});

test("refuses a dirty checkout without discarding the local change", (t) => {
  const f = fixture(t);
  const file = path.join(f.checkout, "product/inference/gpu/host-agent.py");
  writeFileSync(file, "local work\n");
  assert.throws(() => f.run(), /clean checkout/);
  assert.equal(readFileSync(file, "utf8"), "local work\n");
});

test("retries rejected pushes and stops after a bounded number of failures", (t) => {
  const f = fixture(t);
  const hook = path.join(f.remote, "hooks/pre-receive");
  writeFileSync(
    hook,
    '#!/bin/sh\nmarker="$(dirname "$0")/rejected-once"\nif [ ! -f "$marker" ]; then touch "$marker"; exit 1; fi\n',
  );
  chmodSync(hook, 0o755);
  assert.equal(f.run().promoted, true);
  assert.equal(
    f.git(f.checkout, "rev-list", "--count", `${f.source}..HEAD`),
    "1",
  );
  const source = f.commit(
    f.writer(),
    "product/inference/gpu/host-agent.py",
    "next reviewed host payload\n",
  );
  writeFileSync(
    f.releaseFile,
    JSON.stringify({ ...f.release, source, sha256: "e".repeat(64) }),
  );
  writeFileSync(hook, "#!/bin/sh\nexit 1\n");
  assert.throws(() => f.run(source), /after three attempts/);
});

test("rechecks host inputs when main changes between rendering and pushing", (t) => {
  const f = fixture(t);
  const writer = f.writer();
  const q = (value) => `'${value.replaceAll("'", "'\\''")}'`;
  const hook = path.join(f.checkout, ".git/hooks/pre-push");
  writeFileSync(
    hook,
    `#!/bin/sh
set -eu
printf 'newer host code\\n' > ${q(path.join(writer, "product/inference/gpu/host-agent.py"))}
git -C ${q(writer)} add .
git -C ${q(writer)} commit -m 'New host source during promotion' >/dev/null
git -C ${q(writer)} push origin main >/dev/null
`,
  );
  chmodSync(hook, 0o755);
  assert.equal(f.run().reason, "newer host build inputs on main");
  const pins = JSON.parse(
    f.git(f.root, "--git-dir", f.remote, "show", `main:${hostPins}`),
  );
  assert.deepEqual(pins, f.pins);
});
