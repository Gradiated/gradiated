import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";
import { SeenStore } from "./seen-store.ts";

const dir = await mkdtemp(join(tmpdir(), "model-radar-"));
after(() => rm(dir, { recursive: true, force: true }));

describe("SeenStore", () => {
  it("starts empty when there is no file", async () => {
    assert.deepEqual(await new SeenStore(join(dir, "missing.json")).load(), {});
  });

  it("saves sorted IDs, creating the folder, and loads them back", async () => {
    const path = join(dir, "nested", "seen.json");
    const store = new SeenStore(path);
    await store.save({
      "openrouter:qwen": ["qwen/b", "qwen/a"],
      "huggingface:Qwen": [],
    });

    assert.equal(
      await readFile(path, "utf8"),
      `${JSON.stringify({ "huggingface:Qwen": [], "openrouter:qwen": ["qwen/a", "qwen/b"] }, null, 2)}\n`,
    );
    assert.deepEqual(await store.load(), {
      "huggingface:Qwen": [],
      "openrouter:qwen": ["qwen/a", "qwen/b"],
    });
  });

  it("refuses a file that is not a seen-IDs file", async () => {
    const path = join(dir, "bad.json");
    await writeFile(path, JSON.stringify({ "openrouter:qwen": "qwen/a" }));
    await assert.rejects(new SeenStore(path).load(), /is not a seen-IDs file/);
  });
});
