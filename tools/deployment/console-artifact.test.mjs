import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, writeFile, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import {
  fileHashes,
  validateConsole,
  consoleKey,
} from "./console-artifact.mjs";
test("console proof rejects altered, extra or missing assets and different inputs", async () => {
  const dir = await mkdtemp(`${tmpdir()}/console-artifact-`);
  try {
    await writeFile(`${dir}/index.html`, "html");
    await writeFile(`${dir}/.hidden`, "asset");
    await writeFile(
      `${dir}/console-proof.json`,
      JSON.stringify({
        schema: 1,
        key: "expected",
        files: await fileHashes(dir),
      }),
    );
    await validateConsole(dir, "expected");
    await assert.rejects(validateConsole(dir, "different"));
    await writeFile(`${dir}/index.html`, "changed");
    await assert.rejects(validateConsole(dir, "expected"));
    await writeFile(`${dir}/index.html`, "html");
    await writeFile(`${dir}/extra.js`, "extra");
    await assert.rejects(validateConsole(dir, "expected"));
    await rm(`${dir}/extra.js`);
    await rm(`${dir}/.hidden`);
    await assert.rejects(validateConsole(dir, "expected"));
    await symlink("/etc/hostname", `${dir}/link`);
    await assert.rejects(fileHashes(dir), /symbolic/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
test("public production configuration participates in console build identity", () => {
  assert.notEqual(
    consoleKey("HEAD", { VITE_API_URL: "one", VITE_POSTHOG_KEY: "public" }),
    consoleKey("HEAD", { VITE_API_URL: "two", VITE_POSTHOG_KEY: "public" }),
  );
});

test("release identity tracks build definitions and ignores screenshots and docs", async () => {
  const { execFileSync } = await import("node:child_process");
  const { mkdir } = await import("node:fs/promises");
  const directory = await mkdtemp(`${tmpdir()}/console-inputs-`);
  const git = (...args) =>
    execFileSync("git", args, { cwd: directory, encoding: "utf8" }).trim();
  const commit = () => {
    git("add", ".");
    git(
      "-c",
      "user.name=Test",
      "-c",
      "user.email=test@example.com",
      "commit",
      "-qm",
      "fixture",
    );
    return git("rev-parse", "HEAD");
  };
  const module = new URL("./console-artifact.mjs", import.meta.url).href;
  const key = (revision) =>
    execFileSync(
      process.execPath,
      [
        "--input-type=module",
        "-e",
        `import {consoleKey} from ${JSON.stringify(module)}; process.stdout.write(consoleKey(process.argv[1]));`,
        revision,
      ],
      { cwd: directory, encoding: "utf8" },
    );
  try {
    git("init", "-q");
    await writeFile(`${directory}/initial`, "fixture");
    let previous = commit();
    for (const path of [
      "tools/deployment/console-artifact.mjs",
      ".github/workflows/tests.yml",
    ]) {
      await mkdir(`${directory}/${path.slice(0, path.lastIndexOf("/"))}`, {
        recursive: true,
      });
      await writeFile(`${directory}/${path}`, "build definition");
      const next = commit();
      assert.notEqual(key(previous), key(next), path);
      previous = next;
    }
    for (const path of [
      "product/services/console/README.md",
      "product/services/console/screenshots/story.png",
    ]) {
      await mkdir(`${directory}/${path.slice(0, path.lastIndexOf("/"))}`, {
        recursive: true,
      });
      await writeFile(`${directory}/${path}`, "documentation");
      const next = commit();
      assert.equal(key(previous), key(next), path);
      previous = next;
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
