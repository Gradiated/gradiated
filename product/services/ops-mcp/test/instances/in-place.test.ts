import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import {
  bootstrapScript,
  verifyInstalledBase,
} from "../../src/instances/in-place.js";

const roots: string[] = [];
const processes: number[] = [];
afterEach(() => {
  for (const pid of processes.splice(0)) {
    try {
      process.kill(pid);
    } catch {}
  }
  for (const root of roots.splice(0))
    rmSync(root, { recursive: true, force: true });
});

const setup = () => {
  const root = mkdtempSync(path.join(tmpdir(), "in-place-enrollment-test-"));
  roots.push(root);
  const file = (name: string, content: string) => {
    const target = path.join(root, name);
    mkdirSync(path.dirname(target), { recursive: true });
    writeFileSync(target, content, { mode: 0o700 });
  };
  file("etc/gradiated/base-id", "test-base-v1\n");
  file("etc/nomad/client.hcl", "client {}\n");
  mkdirSync(path.join(root, "etc/nomad/tls"), { recursive: true });
  mkdirSync(path.join(root, "var/log"), { recursive: true });
  file("bin/pgrep", "#!/bin/sh\nexit 1\n");
  file(
    "opt/gradiated/bin/configure-serving",
    '#!/bin/sh\ntest -n "$GRADIATED_RUNTIME_ACCESS_TOKEN" && test -n "$GRADIATED_DEPLOYMENT_STATUS_TOKEN"\n',
  );
  file(
    "opt/gradiated/bin/start-client",
    `#!/bin/sh\necho $$ > '${root}/client-pid'\nmkdir '${root}/allocation'\nexec sleep 60\n`,
  );
  const script = bootstrapScript
    .replaceAll('"/etc/', `"${root}/etc/`)
    .replaceAll('"/opt/', `"${root}/opt/`)
    .replaceAll('"/var/', `"${root}/var/`)
    .replaceAll("pwd.getpwnam(user)", "pwd.getpwuid(os.getuid())")
    .replaceAll('pwd.getpwnam("nomad")', "pwd.getpwuid(os.getuid())")
    .replaceAll('pwd.getpwnam("root")', "pwd.getpwuid(os.getuid())");
  const environment = {
    GRADIATED_INSTANCE_ID: "019d5a4a-0000-7000-8000-000000000001",
    GRADIATED_NOMAD_NODE_ID: "3f1e5a52-8d4b-4c1e-9a55-111111111111",
    GRADIATED_NOMAD_NODE_SECRET: "3f1e5a52-8d4b-4c1e-9a55-222222222222",
    GRADIATED_NODE_NAME: "runpod-pod1",
    GRADIATED_NOMAD_CA: Buffer.from("test-ca").toString("base64"),
    GRADIATED_NOMAD_CERT: Buffer.from("test-certificate").toString("base64"),
    GRADIATED_NOMAD_KEY: Buffer.from("test-private-key").toString("base64"),
    GRADIATED_ARTIFACT_ENV: Buffer.from("test-artifact-credentials").toString(
      "base64",
    ),
    GRADIATED_RUNTIME_ACCESS_TOKEN: "t".repeat(40),
    GRADIATED_DEPLOYMENT_STATUS_TOKEN: "s".repeat(40),
  };
  const run = (values = environment) =>
    spawnSync("python3", ["-c", script], {
      input: JSON.stringify({
        environment: values,
        renewalScripts: {
          agent: "# renewal agent fixture",
          supervisor: "# supervisor fixture",
          startClient: readFileSync(
            path.join(root, "opt/gradiated/bin/start-client"),
            "utf8",
          ),
        },
      }),
      encoding: "utf8",
      env: { ...process.env, PATH: `${root}/bin:${process.env.PATH}` },
      timeout: 10_000,
    });

  return { root, file, environment, run };
};

describe("in-place host bootstrap", () => {
  it("installs identity and metadata and starts only the Nomad client", () => {
    const test = setup();
    const result = test.run();
    const pid = Number(
      readFileSync(path.join(test.root, "client-pid"), "utf8"),
    );
    processes.push(pid);

    expect(result.status).toBe(0);
    expect(result.stdout).toBe("");
    expect(result.stderr).toBe("");
    expect(
      readFileSync(
        path.join(test.root, "var/lib/nomad/client/client-id"),
        "utf8",
      ),
    ).toBe(test.environment.GRADIATED_NOMAD_NODE_ID);
    expect(
      readFileSync(
        path.join(test.root, "etc/nomad/tls/client-key.pem"),
        "utf8",
      ),
    ).toBe("test-private-key");
    expect(
      readFileSync(path.join(test.root, "etc/nomad/node.hcl"), "utf8"),
    ).toContain('runtime_base_id = "test-base-v1"');
    expect(
      JSON.parse(
        readFileSync(
          path.join(test.root, "etc/gradiated/in-place-enrollment.json"),
          "utf8",
        ),
      ),
    ).toEqual({
      GRADIATED_INSTANCE_ID: test.environment.GRADIATED_INSTANCE_ID,
      GRADIATED_NOMAD_NODE_ID: test.environment.GRADIATED_NOMAD_NODE_ID,
      GRADIATED_NOMAD_NODE_SECRET: test.environment.GRADIATED_NOMAD_NODE_SECRET,
    });
    expect(process.kill(pid, 0)).toBe(true);
    expect(statSync(path.join(test.root, "allocation")).mode & 0o777).toBe(
      0o755,
    );
    for (const name of [
      "etc/nomad/tls/client-key.pem",
      "etc/gradiated/artifact.env",
      "etc/gradiated/in-place-enrollment.json",
    ]) {
      expect(statSync(path.join(test.root, name)).mode & 0o777).toBe(0o600);
    }
  });

  it("installs renewal during registration on a retained base without an agent", () => {
    const test = setup();
    const result = test.run({
      ...test.environment,
      GRADIATED_NOMAD_RENEWAL_TOKEN: "r".repeat(43),
    } as typeof test.environment);
    expect(result.status).toBe(0);
    processes.push(
      Number(readFileSync(path.join(test.root, "client-pid"), "utf8")),
    );
    for (const name of ["renew-certificate", "run-renewer", "start-client"]) {
      expect(
        statSync(path.join(test.root, "opt/gradiated/bin", name)).mode & 0o777,
      ).toBe(0o755);
    }
    expect(
      JSON.parse(
        readFileSync(
          path.join(test.root, "etc/nomad/tls/renewal.json"),
          "utf8",
        ),
      ),
    ).toEqual({
      instance_id: test.environment.GRADIATED_INSTANCE_ID,
      nomad_node_id: test.environment.GRADIATED_NOMAD_NODE_ID,
      token: "r".repeat(43),
    });
    expect(
      statSync(path.join(test.root, "etc/nomad/tls/renewal.json")).mode & 0o777,
    ).toBe(0o600);
  });

  it("refuses to overwrite a configured client", () => {
    const test = setup();
    test.file("etc/nomad/node.hcl", "existing-client");

    expect(test.run().status).toBe(73);
    expect(
      readFileSync(path.join(test.root, "etc/nomad/node.hcl"), "utf8"),
    ).toBe("existing-client");
  });

  it("rejects injected identifiers before writing credentials", () => {
    const test = setup();

    expect(
      test.run({
        ...test.environment,
        GRADIATED_NODE_NAME: 'invalid"; command',
      }).status,
    ).toBe(64);
    expect(() =>
      readFileSync(path.join(test.root, "etc/nomad/tls/client-key.pem")),
    ).toThrow();
  });
});

describe("installed base qualification", () => {
  it("rejects missing manifests, wrong source images and altered binaries", () => {
    const test = setup();
    const script = verifyInstalledBase
      .replaceAll('"/etc/', `"${test.root}/etc/`)
      .replaceAll('"/usr/', `"${test.root}/usr/`)
      .replaceAll('"/opt/', `"${test.root}/opt/`);
    const run = () =>
      spawnSync("python3", ["-c", script], {
        input: JSON.stringify({ image: "base:inputs-pinned" }),
        encoding: "utf8",
      });

    expect(run().status).not.toBe(0);
    const files: Record<string, string> = {};
    for (const name of [
      "etc/gradiated/base-id",
      "etc/nomad/client.hcl",
      "usr/local/bin/nomad",
      "opt/nomad/plugins/nomad-device-nvidia",
      "opt/gradiated/bin/start-client",
      "opt/gradiated/bin/configure-serving",
      "opt/gradiated/bin/runtime-launch",
      "opt/gradiated/bin/desmondd",
    ]) {
      test.file(name, "pinned bytes");
      files[path.join(test.root, name)] = createHash("sha256")
        .update("pinned bytes")
        .digest("hex");
    }
    const manifest = (image: string) =>
      test.file(
        "etc/gradiated/installed-base.json",
        JSON.stringify({ image, files }),
      );
    manifest("base:inputs-other");
    expect(run().status).not.toBe(0);
    manifest("base:inputs-pinned");
    expect(run().status).toBe(0);
    test.file("usr/local/bin/nomad", "altered bytes");
    expect(run().status).not.toBe(0);
  });
});
