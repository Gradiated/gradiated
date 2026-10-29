import { expect, it, vi } from "vitest";

vi.mock("../src/articles", () => ({ articles: [] }));
vi.mock("../src/careers", () => ({ jobs: [] }));
vi.mock("../src/handbook", () => ({ handbookPages: [] }));
vi.mock("../src/models", () => ({ models: [] }));

import { getIndexablePaths, getPageMetadata } from "../src/metadata";

it("keeps the client-only Library redirect out of search indexes", () => {
  expect(getPageMetadata("/library/").index).toBe(false);
  expect(getIndexablePaths()).not.toContain("/library/");
});
