import { existsSync } from "node:fs";
import { chmod, readFile, stat, writeFile } from "node:fs/promises";
import { describe, expect } from "vitest";
import {
  readStoredKey,
  removeStoredKey,
  storeKey,
} from "../src/credentials.js";
import { WizardError } from "../src/errors.js";
import { test as it } from "./support/home.js";

describe("stored credentials", () => {
  it("stores the key with owner-only permissions and reads it back", async ({
    paths,
  }) => {
    expect(await storeKey(paths, "grad_fixture")).toBe(true);

    expect(await readStoredKey(paths)).toBe("grad_fixture");
    if (process.platform !== "win32") {
      expect((await stat(paths.credentials)).mode & 0o777).toBe(0o600);
    }
  });

  it.skipIf(process.platform === "win32")(
    "tightens a key file that already has looser permissions",
    async ({ paths }) => {
      await storeKey(paths, "grad_first");
      await chmod(paths.credentials, 0o644);

      await storeKey(paths, "grad_second");

      expect((await stat(paths.credentials)).mode & 0o777).toBe(0o600);
      expect(await readStoredKey(paths)).toBe("grad_second");
    },
  );

  it("reports a change only when the key differs", async ({ paths }) => {
    await storeKey(paths, "grad_first");

    expect(await storeKey(paths, "grad_first")).toBe(false);
    expect(await storeKey(paths, "grad_second")).toBe(true);
    expect(await readStoredKey(paths)).toBe("grad_second");
  });

  it("reads a missing file as no key", async ({ paths }) => {
    expect(await readStoredKey(paths)).toBeNull();
    expect(await removeStoredKey(paths)).toBe(false);
  });

  it("rejects a malformed file and names it", async ({ paths }) => {
    await storeKey(paths, "grad_fixture");
    await writeFile(paths.credentials, "{not json");

    await expect(readStoredKey(paths)).rejects.toThrow(WizardError);
    await expect(readStoredKey(paths)).rejects.toThrow(paths.credentials);
    await expect(removeStoredKey(paths)).rejects.toThrow(paths.credentials);
    expect(await readFile(paths.credentials, "utf8")).toBe("{not json");
  });

  it.skipIf(process.platform === "win32" || process.getuid?.() === 0)(
    "rejects an unreadable file instead of treating it as absent",
    async ({ paths }) => {
      await storeKey(paths, "grad_fixture");
      await chmod(paths.credentials, 0o000);

      await expect(readStoredKey(paths)).rejects.toThrow(
        `Could not read ${paths.credentials}`,
      );
    },
  );

  it("removes a stored key", async ({ paths }) => {
    await storeKey(paths, "grad_fixture");

    expect(await removeStoredKey(paths)).toBe(true);
    expect(existsSync(paths.credentials)).toBe(false);
  });
});
