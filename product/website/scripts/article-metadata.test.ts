import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import {
  buildArticleRegistry,
  parseArticleMetadata,
} from "../src/article-metadata";

const fixture = (status = "published", path = "/library/example/") => `---
title: Example
description: Example article description.
path: ${path}
status: ${status}
publishedAt: "2026-09-02"
---
Article body.
`;
test("frontmatter provides article metadata without reading its body", () => {
  const article = parseArticleMetadata(fixture(), "example.mdx");
  assert.equal(article.publishedAt, "2026-09-02");
  assert.equal(article.title, "Example");
  assert.equal(article.collection, "library");
  assert.equal(article.image, "/brand/png/gradiated-mark-dark-1024.png");
});
test("draft filtering applies to every article, not a named route", () => {
  const sources = {
    "a.mdx": fixture(),
    "b.mdx": fixture("draft", "/library/another/"),
    "c.mdx": fixture("draft", "/notes/third/"),
  };
  assert.equal(buildArticleRegistry(sources, true).length, 3);
  assert.deepEqual(
    buildArticleRegistry(sources, false).map((a) => a.path),
    ["/library/example/"],
  );
});
test("invalid metadata and duplicate paths fail loudly", () => {
  for (const source of [
    "no frontmatter",
    fixture("typo"),
    fixture().replace("2026-09-02", "2026-02-30"),
    fixture().replace("title: Example", "title: ''"),
    fixture().replace("/library/example/", "/docs/example/"),
  ]) {
    assert.throws(() => parseArticleMetadata(source, "bad.mdx"));
  }
  assert.throws(
    () => buildArticleRegistry({ a: fixture(), b: fixture() }, false),
    /Duplicate/,
  );
});
test("Carat is published with the requested date; Thesis uses the same schema", () => {
  const carat = parseArticleMetadata(
    readFileSync(
      new URL(
        "../content/articles/building-gemma-inference-engine.mdx",
        import.meta.url,
      ),
      "utf8",
    ),
    "carat",
  );
  assert.equal(carat.status, "published");
  assert.equal(carat.publishedAt, "2026-09-02");
  const thesis = parseArticleMetadata(
    readFileSync(
      new URL("../content/articles/our-thesis.mdx", import.meta.url),
      "utf8",
    ),
    "thesis",
  );
  assert.equal(thesis.path, "/notes/our-thesis/");
});

test("existing articles default to the Library and hardware remains a subject", () => {
  assert.equal(parseArticleMetadata(fixture(), "legacy").category, "notes");
  assert.equal(parseArticleMetadata(fixture(), "legacy").layout, "reading");
  const hardware = fixture().replace(
    "status: published",
    "category: hardware\nlayout: journey\nstatus: published",
  );
  assert.equal(parseArticleMetadata(hardware, "hardware").category, "hardware");
  assert.equal(parseArticleMetadata(hardware, "hardware").layout, "journey");
  assert.throws(() =>
    parseArticleMetadata(
      hardware.replace("category: hardware", "category: typo"),
      "bad",
    ),
  );
});

test("the sand journey has its own collection and remains excluded from production", () => {
  const source = readFileSync(
    new URL(
      "../content/articles/how-to-get-an-answer-out-of-sand.mdx",
      import.meta.url,
    ),
    "utf8",
  );
  const draft = parseArticleMetadata(source, "sand");
  assert.equal(draft.category, "hardware");
  assert.equal(draft.collection, "sand-to-thought");
  assert.equal(draft.path, "/sand-to-thought/");
  assert.equal(draft.layout, "journey");
  assert.equal(buildArticleRegistry({ sand: source }, true).length, 1);
  assert.equal(buildArticleRegistry({ sand: source }, false).length, 0);
});
