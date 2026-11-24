import { expect, it, vi } from "vitest";
import { buildArticleRegistry } from "../src/article-metadata";
import { libraryStories } from "../src/library-stories";

vi.mock("../src/articles", () => ({
  articles: buildArticleRegistry(
    Object.fromEntries(
      [
        ["note", "library", "notes", "/library/example/"],
        ["hardware", "library", "hardware", "/library/hardware-example/"],
        [
          "guide",
          "sand-to-thought",
          "hardware",
          "/library/sand-to-thought/how-to-get-an-answer-out-of-sand/",
        ],
      ].map(([name, collection, category, path]) => [
        `${name}.mdx`,
        `---
title: ${name}
author: Ada Lovelace
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

vi.mock("../src/handbook", () => ({
  handbookPages: [{ slug: "mission", title: "Mission" }],
}));

it("keeps published writing of every subject in Notes", () => {
  expect(
    libraryStories
      .filter((story) => story.kind === "note")
      .map((story) => story.href),
  ).toEqual(["/library/example/", "/library/hardware-example/"]);
});

it("keeps the guide outside Notes and Handbook in their own collection", () => {
  expect(
    libraryStories.some(
      (story) =>
        story.href ===
        "/library/sand-to-thought/how-to-get-an-answer-out-of-sand/",
    ),
  ).toBe(false);
  expect(
    libraryStories
      .filter((story) => story.kind === "handbook")
      .map((story) => story.href),
  ).toEqual(["/handbook/mission/"]);
});
