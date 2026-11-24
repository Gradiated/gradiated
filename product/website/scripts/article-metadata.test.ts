import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import {
  buildArticleRegistry,
  parseArticleMetadata,
} from "../src/article-metadata";

const fixture = (status = "published", path = "/library/example/") => `---
title: Example
author: Ada Lovelace
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
test("articles can name an author", () => {
  const source = fixture();
  const article = parseArticleMetadata(source, "with-author.mdx");
  assert.equal(article.author, "Ada Lovelace");
  const titled = parseArticleMetadata(
    source.replace(
      "author: Ada Lovelace\n",
      "author: Ada Lovelace\nauthorTitle: Mathematician\n",
    ),
    "with-title.mdx",
  );
  assert.equal(titled.authorTitle, "Mathematician");
  assert.throws(() =>
    parseArticleMetadata(
      fixture().replace("author: Ada Lovelace\n", ""),
      "no-author.mdx",
    ),
  );
});
test("articles can omit the visible description", () => {
  const source = fixture().replace(
    "description: Example article description.\n",
    "",
  );
  const article = parseArticleMetadata(source, "without-description.mdx");
  assert.equal(article.description, undefined);
  assert.equal(article.title, "Example");
});
test("draft filtering applies to every article, not a named route", () => {
  const sources = {
    "a.mdx": fixture(),
    "b.mdx": fixture("draft", "/library/another/"),
    "c.mdx": fixture("draft", "/library/third/"),
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
  assert.equal(thesis.path, "/library/our-thesis/");
});

test("the October progress note is included in production", () => {
  const source = readFileSync(
    new URL("../content/articles/new-post.mdx", import.meta.url),
    "utf8",
  );
  const article = parseArticleMetadata(source, "October progress note");

  assert.equal(article.path, "/library/2026-10-starting-on-hard-mode/");
  assert.equal(article.status, "published");
  assert.equal(buildArticleRegistry({ note: source }, false).length, 1);
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

test("the published sand journey has its own collection and is included in production", () => {
  const source = readFileSync(
    new URL(
      "../content/articles/how-to-get-an-answer-out-of-sand.mdx",
      import.meta.url,
    ),
    "utf8",
  );
  const article = parseArticleMetadata(source, "sand");
  assert.equal(article.category, "hardware");
  assert.equal(article.collection, "sand-to-thought");
  assert.equal(
    article.path,
    "/library/sand-to-thought/how-to-get-an-answer-out-of-sand/",
  );
  assert.equal(article.layout, "journey");
  assert.equal(buildArticleRegistry({ sand: source }, true).length, 1);
  assert.equal(article.status, "published");
  assert.equal(buildArticleRegistry({ sand: source }, false).length, 1);
});
