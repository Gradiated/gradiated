import { expect, it, vi } from "vitest";
import { buildArticleRegistry } from "../src/article-metadata";
import { libraryStories } from "../src/library-stories";

vi.mock("../src/articles", () => ({
  articles: buildArticleRegistry(
    Object.fromEntries(
      [
        ["note", "library", "notes", "/library/example/"],
        ["hardware", "library", "hardware", "/library/hardware-example/"],
        ["guide", "sand-to-thought", "hardware", "/sand-to-thought/"],
      ].map(([name, collection, category, path]) => [
        `${name}.mdx`,
        `---
title: ${name}
description: Example article.
path: ${path}
collection: ${collection}
category: ${category}
status: published
publishedAt: "2026-09-02"
---
Article body.
`,
      ]),
    ),
    false,
  ),
}));

vi.mock("../src/method", () => ({
  methodPages: [
    { slug: "mission", title: "Mission", indexDescription: "Our mission." },
  ],
}));

it("keeps Library articles of every subject in the Notes filter", () => {
  expect(
    libraryStories
      .filter((story) => story.kind === "note")
      .map((story) => story.href),
  ).toEqual(["/library/example/", "/library/hardware-example/"]);
});

it("keeps the guide outside the Library and Methods in their own filter", () => {
  expect(
    libraryStories.some((story) => story.href === "/sand-to-thought/"),
  ).toBe(false);
  expect(
    libraryStories
      .filter((story) => story.kind === "method")
      .map((story) => story.href),
  ).toEqual(["/library/method/mission/"]);
});
