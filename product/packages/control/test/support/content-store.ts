import { vi } from "vitest";
import type { ContentStore } from "../../src/traces/storage.js";

export const createMemoryContentStore = (
  objects: Map<string, Buffer>,
  modifiedAt = new Date().toISOString(),
) =>
  ({
    list: vi.fn(async (prefix, options = {}) => {
      const keys = [...objects.keys()]
        .filter((key) => key.startsWith(prefix))
        .sort();
      if (options.delimiter)
        return {
          keys: [],
          prefixes: [
            ...new Set(
              keys.map(
                (key) =>
                  prefix +
                  key.slice(prefix.length).split(options.delimiter)[0] +
                  options.delimiter,
              ),
            ),
          ],
        };
      const start = options.cursor ? Number(options.cursor) : 0;
      const limit = options.limit ?? 100;
      return {
        keys: keys.slice(start, start + limit),
        modifiedAt: Object.fromEntries(
          keys.slice(start, start + limit).map((key) => [key, modifiedAt]),
        ),
        prefixes: [],
        cursor: keys.length > start + limit ? String(start + limit) : undefined,
      };
    }),
    read: vi.fn(async (key, range) => {
      const bytes = objects.get(key);
      if (!bytes) throw new Error("missing");
      return range
        ? bytes.subarray(range.offset, range.offset + range.length)
        : bytes;
    }),
    delete: vi.fn(async (keys) => {
      for (const key of keys) objects.delete(key);
    }),
  }) satisfies ContentStore;
