import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const { renderPost } = createRequire(import.meta.url)("./sand-renderer.cjs");
const read = (file) => readFileSync(new URL(file, import.meta.url), "utf8");
const source = read("../content/articles/sand/script.md");
const scenes = JSON.parse(read("../content/articles/sand/scenes.json"));
const publication = JSON.parse(
  read("../content/articles/sand/publication.json"),
);
const template = "<!--{{TITLE}}-->{{ARTICLE}}";
const sceneKeys = (html) =>
  [...html.matchAll(/data-scene="([^"]+)"/g)].map((match) => match[1]);

test("the public guide ends with timing and excludes all chapter 5 prose and links", () => {
  const html = renderPost(source, template, scenes, publication);
  assert.equal(publication.publishedThrough, "timing");
  assert.deepEqual(
    sceneKeys(html),
    scenes.slice(0, scenes.indexOf("timing") + 1),
  );
  for (const draft of [
    "Building a computer",
    "von Neumann",
    "multiplexer",
    "LC-3",
    "program counter",
    "sand-select-values",
    "sand-computer",
  ])
    assert.ok(!html.includes(draft), draft);
  assert.ok(html.includes(publication.footer));
  assert.ok(!html.includes("The LC-3 example"));
});

test("the complete preview retains all chapters and its own ending", () => {
  const html = renderPost(source, template, scenes);
  assert.deepEqual(sceneKeys(html), scenes);
  assert.ok(html.includes("Building a computer"));
  assert.ok(html.includes("LC-3"));
  assert.ok(html.includes("The LC-3 example"));
  assert.ok(!html.includes(publication.footer));
});

test("unknown scenes, incomplete chapters and empty endings fail the build", () => {
  for (const invalid of [
    { ...publication, publishedThrough: "missing" },
    { ...publication, publishedThrough: "quartz" },
    { ...publication, footer: "" },
  ])
    assert.throws(
      () => renderPost(source, template, scenes, invalid),
      /publication|publishedThrough/,
    );
});

test("notes belonging only to unpublished chapters are omitted", () => {
  const draft = `# Example\n\nOverview.\n\n## One\n\n<!-- scene: one -->\n\nPublished text.[^visible]\n\n## Two\n\n<!-- scene: two -->\n\nDraft text.[^hidden]\n\n<!-- footer -->\n\nDraft ending.\n\n[^visible]: Public note.\n[^hidden]: Unpublished note.\n`;
  const html = renderPost(draft, template, ["one", "two"], {
    publishedThrough: "one",
    footer: "Public ending.",
  });
  assert.ok(html.includes("Public note."));
  assert.ok(!html.includes("Unpublished note."));
  assert.ok(!html.includes("fn-hidden"));
});
