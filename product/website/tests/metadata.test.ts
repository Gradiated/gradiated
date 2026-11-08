import { expect, it, vi } from "vitest";

vi.mock("../src/articles", () => ({ articles: [] }));
vi.mock("../src/careers", () => ({ jobs: [] }));
vi.mock("../src/handbook", () => ({ handbookPages: [] }));
vi.mock("../src/models", () => ({ models: [] }));

import { getPageMetadata, getStaticPaths } from "../src/metadata";

it("prerenders the Library without adding it to search indexes", () => {
  expect(getStaticPaths()).toContain("/library/");
  expect(getPageMetadata("/library/").index).toBe(false);
});
