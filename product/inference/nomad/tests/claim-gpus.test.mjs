import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  existsSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as pause } from "node:timers/promises";

const script = fileURLToPath(new URL("../jobs/claim-gpus.sh", import.meta.url));
const fixture = (t) => {
  const dir = mkdtempSync(join(tmpdir(), "gpu-claims-"));
  const children = [];
  mkdirSync(join(dir, "bin"));
  mkdirSync(join(dir, "bundle"));
  writeFileSync(
    join(dir, "bin", "nvidia-smi"),
    '#!/bin/sh\n[ ! -f "$HOME/query-fails" ] || exit 1\nif [ -f "$HOME/busy" ]; then echo 123; fi\n',
    { mode: 0o755 },
  );
  writeFileSync(
    join(dir, "bundle", "runtime-launch"),
    '#!/bin/sh\ntouch "$HOME/$CLAIM_NAME-started"\nwhile [ ! -f "$HOME/$CLAIM_NAME-release" ]; do sleep 0.05; done\n',
    { mode: 0o755 },
  );
  t.after(() => {
    for (const child of children) {
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch {}
    }
    rmSync(dir, { recursive: true, force: true });
  });
  const start = (name, devices = "GPU-aaaa") => {
    mkdirSync(join(dir, name), { recursive: true });
    const child = spawn("bash", [script, join(dir, "bundle")], {
      detached: true,
      env: {
        ...process.env,
        HOME: dir,
        PATH: `${dir}/bin:${process.env.PATH}`,
        CLAIM_NAME: name,
        NOMAD_ALLOC_DIR: join(dir, name),
        NVIDIA_VISIBLE_DEVICES: devices,
      },
      stdio: ["ignore", "ignore", "pipe"],
    });
    child.stderr.resume();
    child.finished = new Promise((resolve) =>
      child.on("exit", (code) => resolve(code)),
    );
    children.push(child);
    return child;
  };
  const waitFor = async (name) => {
    for (let i = 0; i < 100; i++) {
      if (existsSync(join(dir, `${name}-started`))) return;
      await pause(50);
    }
    throw new Error(`${name} did not start`);
  };
  return { dir, start, waitFor };
};

test(
  "a runtime holds its GPU lock across exec until it exits",
  { timeout: 10000 },
  async (t) => {
    const { dir, start, waitFor } = fixture(t);
    const first = start("first");
    await waitFor("first");
    start("second");
    start("independent", "GPU-bbbb");
    await waitFor("independent");
    await pause(250);
    assert.equal(existsSync(join(dir, "second-started")), false);
    writeFileSync(join(dir, "first-release"), "");
    assert.equal(await first.finished, 0);
    await waitFor("second");
  },
);

test(
  "legacy GPU processes finish before a new runtime starts",
  { timeout: 10000 },
  async (t) => {
    const { dir, start, waitFor } = fixture(t);
    writeFileSync(join(dir, "busy"), "");
    start("waiting");
    await pause(250);
    assert.equal(existsSync(join(dir, "waiting-started")), false);
    assert.equal(existsSync(join(dir, "waiting", "runtime-starting")), false);
    rmSync(join(dir, "busy"));
    await waitFor("waiting");
  },
);

test(
  "device inspection failure cannot launch a runtime",
  { timeout: 10000 },
  async (t) => {
    const { dir, start } = fixture(t);
    writeFileSync(join(dir, "query-fails"), "");
    assert.notEqual(await start("failed").finished, 0);
    assert.equal(existsSync(join(dir, "failed-started")), false);
  },
);

test(
  "overlapping multi-GPU claims use one lock order",
  { timeout: 10000 },
  async (t) => {
    const { dir, start, waitFor } = fixture(t);
    const first = start("first", "GPU-bbbb,GPU-aaaa");
    await waitFor("first");
    start("second", "GPU-aaaa,GPU-bbbb");
    await pause(250);
    assert.equal(existsSync(join(dir, "second-started")), false);
    writeFileSync(join(dir, "first-release"), "");
    await first.finished;
    await waitFor("second");
  },
);

test(
  "the observer waits until its allocation owns the GPUs",
  { timeout: 10000 },
  async (t) => {
    const { dir } = fixture(t);
    const allocation = join(dir, "observer");
    mkdirSync(join(allocation, "runtime"), { recursive: true });
    writeFileSync(
      join(allocation, "runtime", "desmondd"),
      '#!/bin/sh\ntouch "$NOMAD_ALLOC_DIR/observer-started"\n',
      { mode: 0o755 },
    );
    const child = spawn(
      "bash",
      [fileURLToPath(new URL("../jobs/observe-runtime.sh", import.meta.url))],
      {
        detached: true,
        env: { ...process.env, NOMAD_ALLOC_DIR: allocation },
        stdio: "ignore",
      },
    );
    t.after(() => {
      if (child.exitCode === null && child.signalCode === null)
        process.kill(-child.pid, "SIGKILL");
    });
    const finished = new Promise((resolve) => child.on("exit", resolve));
    await pause(250);
    assert.equal(existsSync(join(allocation, "observer-started")), false);
    writeFileSync(join(allocation, "runtime-starting"), "");
    assert.equal(await finished, 0);
    assert.equal(existsSync(join(allocation, "observer-started")), true);
  },
);
