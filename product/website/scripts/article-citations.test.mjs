import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const {
  createCitations,
  articleCitationsPlugin,
  renderCitedSections,
  remarkArticleCitations,
} = require("./article-citations.cjs");
const { renderPost } = require("./sand-renderer.cjs");
const { Marked } = require("marked");
const references = {
  first: {
    authors: ["One, A.", "Two, B."],
    title: "A paper about silicon",
    publication: "Nature Phys.",
    volume: "22",
    pages: "1–5",
    year: 2026,
    url: "https://doi.org/10.1234/example",
  },
  second: {
    authors: ["A research laboratory"],
    title: "An online explanation",
    url: "https://example.org/explanation",
  },
};
const renderer = (sources = references) => {
  const citations = createCitations(sources);
  return { citations, markdown: new Marked(citations.markedExtension) };
};

test("citations number by first appearance and repeated sources share one entry", () => {
  const { citations, markdown } = renderer();
  const html = markdown.parse(
    "Second.[@second] First.[@first] Again.[@second]",
  );
  const bibliography = citations.renderBibliography();

  assert.match(html, /href="#ref-second"[^>]*>1<\/a>/);
  assert.match(html, /href="#ref-first"[^>]*>2<\/a>/);
  assert.match(html, /id="cite-second-2"/);
  assert.ok(
    bibliography.indexOf('id="ref-second"') <
      bibliography.indexOf('id="ref-first"'),
  );
  assert.equal((bibliography.match(/id="ref-second"/g) ?? []).length, 1);
  assert.match(bibliography, /href="#cite-second-1"/);
  assert.match(bibliography, /href="#cite-second-2"/);
  assert.match(
    bibliography,
    /href="https:\/\/example.org\/explanation" target="_blank" rel="noopener noreferrer"/,
  );
  assert.ok(!html.includes('target="_blank"'));
  assert.match(bibliography, /href="#cite-second-1" role="doc-backlink"/);
  assert.match(bibliography, /One, A. &amp; Two, B./);
  assert.match(
    bibliography,
    /<em>Nature Phys.<\/em> <strong>22<\/strong>, 1–5 \(2026\)/,
  );
});

test("code, escaped markers and existing links are not interpreted as citations", () => {
  const { citations, markdown } = renderer();
  const html = markdown.parse(
    "`[@missing]`\n\n```text\n[@missing]\n```\n\n\\[@missing] and [a link [@missing]](https://example.org).",
  );

  assert.ok(html.includes("[@missing]"));
  assert.equal(citations.renderBibliography(), "");
});

test("missing and malformed references fail with useful messages and markup is escaped", () => {
  assert.throws(
    () => renderer().markdown.parse("Missing.[@unknown]"),
    /unknown.*not defined/,
  );
  assert.throws(
    () =>
      renderer({
        first: { ...references.first, url: "javascript:alert(1)" },
      }).markdown.parse("[@first]"),
    /https/,
  );
  assert.throws(
    () =>
      renderer({ first: { title: "Missing fields" } }).markdown.parse(
        "[@first]",
      ),
    /authors|url/,
  );
  const { citations, markdown } = renderer({
    first: { ...references.first, title: '<img src=x onerror="alert(1)">' },
  });
  markdown.parse("[@first]");
  assert.ok(!citations.renderBibliography().includes("<img"));
  assert.match(citations.renderBibliography(), /&lt;img/);
});

test("fabrication sections share numbering without changing scene keys or literal code", () => {
  const result = renderCitedSections(
    "# Intro\n\nText.[@second]\n\n<!-- scene: one -->\n\nA.[@first]\n\n<!-- scene: two -->\n\nAgain.[@second] `[@missing]`",
    references,
  );

  assert.deepEqual(
    result.scenes.map(({ key }) => key),
    ["one", "two"],
  );
  assert.match(result.introduction, />1<\/a>/);
  assert.match(result.scenes[0].html, />2<\/a>/);
  assert.match(result.scenes[1].html, />1<\/a>/);
  assert.match(result.bibliography, /id="ref-first"/);
});

test("Sand publication boundaries include only references used in public scenes", () => {
  const source =
    "# Intro\n\nOverview.\n\n## Public\n\n<!-- scene: one -->\n\nPublic.[@second]\n\n## Draft\n\n<!-- scene: two -->\n\nPrivate.[@first]\n\n<!-- footer -->\n\nEnd.";
  const html = renderPost(
    source,
    "<!--{{TITLE}}-->{{ARTICLE}}",
    ["one", "two"],
    { publishedThrough: "one", footer: "Coming soon." },
    references,
  );

  assert.match(html, /ref-second/);
  assert.ok(!html.includes("ref-first"));
  assert.ok(!html.includes("A paper about silicon"));
  assert.match(html, />1<\/a>/);
});

test("MDX articles compile citations and backlinks while docs remain untouched", async () => {
  const mdxRequire = createRequire(require.resolve("@mdx-js/rollup"));
  const { compile, run } = await import(mdxRequire.resolve("@mdx-js/mdx"));
  const runtime = await import("react/jsx-runtime");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { createElement } = await import("react");
  const directory = mkdtempSync(join(tmpdir(), "article-citations-"));
  try {
    const path = join(directory, "content/articles/example.mdx");
    const { mkdirSync } = await import("node:fs");
    mkdirSync(join(directory, "content/articles"), { recursive: true });
    writeFileSync(
      path.replace(/\.mdx$/, ".references.json"),
      JSON.stringify(references),
    );
    const compiled = await compile(
      { value: "Text.[@first] Again.[@first] `[@missing]`", path },
      {
        outputFormat: "function-body",
        remarkPlugins: [remarkArticleCitations],
      },
    );
    const { default: Content } = await run(compiled, runtime);
    const html = renderToStaticMarkup(createElement(Content));
    assert.match(html, /<sup class="article-citation">/);
    assert.match(html, /role="doc-bibliography"/);
    assert.match(html, /id="ref-first"/);
    assert.match(html, /href="#cite-first-2"/);
    assert.match(
      html,
      /href="https:\/\/doi.org\/10.1234\/example" target="_blank" rel="noopener noreferrer"/,
    );
    assert.match(
      html,
      /href="#ref-first" id="cite-first-1" role="doc-biblioref"/,
    );
    assert.match(html, /<code>\[@missing\]<\/code>/);
    const untouched = await compile(
      {
        value: "Docs [@missing]",
        path: join(directory, "src/docs/example.mdx"),
      },
      { remarkPlugins: [remarkArticleCitations] },
    );
    assert.ok(!String(untouched).includes("article-references"));
    await assert.rejects(
      () =>
        compile(
          { value: "[@missing]", path },
          { remarkPlugins: [remarkArticleCitations] },
        ),
      /not defined/,
    );
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("articles without a companion file do not get an unresolved dev-server import", () => {
  const watched = [];
  articleCitationsPlugin().transform.call(
    { addWatchFile: (path) => watched.push(path) },
    "Text",
    "/not-present/content/articles/no-references.mdx",
  );
  assert.deepEqual(watched, []);
});
