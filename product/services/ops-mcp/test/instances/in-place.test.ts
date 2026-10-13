import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
  installInPlace,
  verifyInstalledBase,
} from "../../src/instances/in-place.js";
import type { RunSsh } from "../../src/instances/ssh.js";
describe("pinned GPU bootstrap", () => {
  it("refuses modified bootstrap files before enrollment", () => {
    const root = mkdtempSync(join(tmpdir(), "gpu-bootstrap-"));
    try {
      const path = join(root, "bootstrap.py");
      writeFileSync(path, "pinned bootstrap");
      const files = {
        [path]: createHash("sha256").update("pinned bootstrap").digest("hex"),
      };
      const run = () =>
        spawnSync("python3", ["-c", verifyInstalledBase], {
          input: JSON.stringify({ files }),
          encoding: "utf8",
        });
      expect(run().status).toBe(0);
      writeFileSync(path, "modified bootstrap");
      expect(run().status).not.toBe(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
  it("keeps bootstrap credentials out of SSH command arguments and returns only inventory", async () => {
    const expected = {
      tailscaleIp: "100.64.0.1",
      gpuCount: 8,
      gpuProduct: "B300",
      cpu: 96,
      memoryGiB: 1280,
    };
    const run = vi.fn<RunSsh>(async () => JSON.stringify(expected));
    const env = { GRADIATED_GPU_BOOTSTRAP: "private-bootstrap" };
    expect(
      await installInPlace(
        run,
        { host: "127.0.0.1", port: 22, hostKeySha256: "a".repeat(64) },
        env,
      ),
    ).toEqual(expected);
    expect(run.mock.calls[0]?.[1]).not.toContain("private-bootstrap");
    expect(JSON.parse(run.mock.calls[0]![2]!)).toEqual({ environment: env });
  });
  it("rejects public network addresses and unqualified hardware in enrollment results", async () => {
    const run: RunSsh = async () =>
      JSON.stringify({
        tailscaleIp: "8.8.8.8",
        gpuCount: 8,
        gpuProduct: "unknown",
        cpu: 96,
        memoryGiB: 1280,
      });
    await expect(
      installInPlace(
        run,
        { host: "127.0.0.1", port: 22, hostKeySha256: "a".repeat(64) },
        { GRADIATED_GPU_BOOTSTRAP: "test" },
      ),
    ).rejects.toThrow();
  });
});
