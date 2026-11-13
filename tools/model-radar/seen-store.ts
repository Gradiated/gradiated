// The model IDs the radar has already seen, per org or prefix ("scope"), kept
// in one JSON file between runs. In GitHub Actions the file lives in the
// Actions cache (see .github/workflows/model-radar.yml).

import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

/** Scope -> IDs seen there, e.g. { "openrouter:qwen": ["qwen/qwen3.8-27b"] }. */
export type Seen = Record<string, string[]>;

export class SeenStore {
  readonly #path: string;

  constructor(path: string) {
    this.#path = path;
  }

  /** The saved IDs, or {} when there is no file yet (the first run). */
  async load(): Promise<Seen> {
    let text: string;
    try {
      text = await readFile(this.#path, "utf8");
    } catch (error) {
      if ((error as { code?: string }).code === "ENOENT") return {};
      throw error;
    }
    const seen: unknown = JSON.parse(text);
    if (
      typeof seen !== "object" ||
      seen === null ||
      Array.isArray(seen) ||
      !Object.values(seen).every(
        (ids) =>
          Array.isArray(ids) && ids.every((id) => typeof id === "string"),
      )
    ) {
      throw new Error(`${this.#path} is not a seen-IDs file.`);
    }
    return seen as Seen;
  }

  /** Writes to a temporary file first, so a failed write never leaves half a file. */
  async save(seen: Seen): Promise<void> {
    const sorted = Object.fromEntries(
      Object.keys(seen)
        .sort()
        .map((scope) => [scope, [...seen[scope]!].sort()]),
    );
    await mkdir(dirname(this.#path), { recursive: true });
    const partial = `${this.#path}.partial`;
    await writeFile(partial, `${JSON.stringify(sorted, null, 2)}\n`);
    await rename(partial, this.#path);
  }
}
