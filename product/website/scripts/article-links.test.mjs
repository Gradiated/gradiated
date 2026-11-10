import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { rehypeArticleExternalLinks } = require("./article-links.cjs");

const link = (href) => ({
  type: "element",
  tagName: "a",
  properties: { href },
  children: [],
});

const run = (path, ...links) => {
  const tree = { type: "root", children: links };
  rehypeArticleExternalLinks()(tree, { path });
  return links;
};

test("external article links open in a new tab", () => {
  const [external, anchor, local] = run(
    "/site/content/articles/post.mdx",
    link("https://example.com/paper"),
    link("#user-content-fn-note"),
    link("/notes/"),
  );

  assert.equal(external.properties.target, "_blank");
  assert.deepEqual(external.properties.rel, ["noopener", "noreferrer"]);
  assert.equal(anchor.properties.target, undefined);
  assert.equal(local.properties.target, undefined);
});

test("links outside articles are left alone", () => {
  const [docsLink] = run(
    "/site/src/docs/page.mdx",
    link("https://example.com"),
  );

  assert.equal(docsLink.properties.target, undefined);
});
