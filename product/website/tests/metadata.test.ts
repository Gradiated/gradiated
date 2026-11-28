import { expect, it, vi } from "vitest";

vi.mock("../src/articles", () => ({ articles: [] }));
vi.mock("../src/careers", () => ({ jobs: [] }));
vi.mock("../src/handbook", () => ({ handbookPages: [] }));
vi.mock("../src/models", () => ({ models: [] }));

import {
  getAllPagePaths,
  getIndexablePaths,
  getPageMetadata,
} from "../src/metadata";

it("indexes the Library magazine", () => {
  expect(getPageMetadata("/library/").index).toBe(true);
  expect(getIndexablePaths()).toContain("/library/");
});

it("keeps internal pages out of the index but still prerendered", () => {
  for (const path of ["/design/", "/style/"]) {
    expect(getPageMetadata(path).index).toBe(false);
    expect(getIndexablePaths()).not.toContain(path);
    expect(getAllPagePaths()).toContain(path);
  }
});
