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

test("the public guide includes chapter 5 through the completed computer", () => {
  const html = renderPost(source, template, scenes, publication);
  assert.equal(publication.publishedThrough, "computer");
  assert.deepEqual(sceneKeys(html), scenes);
  for (const chapterContent of [
    "Building a computer",
    "von Neumann",
    "LC-3",
    "program counter",
    "sand-instruction-control",
    "sand-controller",
    "sand-computer",
    "machine code",
  ])
    assert.ok(html.includes(chapterContent), chapterContent);
  assert.ok(!html.includes('class="footnote"'));
  assert.ok(html.includes(publication.footer));
  assert.equal(html, renderPost(source, template, scenes));
});

test("an earlier publication boundary still excludes unpublished chapters", () => {
  const boundary = {
    publishedThrough: "memory-buses",
    footer: "More to come.",
  };
  const html = renderPost(source, template, scenes, boundary);
  assert.deepEqual(
    sceneKeys(html),
    scenes.slice(0, scenes.indexOf("memory-buses") + 1),
  );
  assert.ok(!html.includes("Building a computer"));
  assert.ok(!html.includes("sand-computer-overview"));
  assert.ok(!html.includes("sand-controller"));
  assert.ok(html.includes(boundary.footer));
  const publicScenes = sceneKeys(html);
  assert.equal(
    publicScenes.indexOf("timing"),
    publicScenes.indexOf("heat") + 1,
  );
  assert.equal(
    publicScenes.indexOf("latch"),
    publicScenes.indexOf("timing") + 1,
  );
});

test("the complete preview retains all chapters and its own ending", () => {
  const html = renderPost(source, template, scenes);
  assert.deepEqual(sceneKeys(html), scenes);
  assert.ok(html.includes("Building a computer"));
  const previewScenes = sceneKeys(html);
  assert.deepEqual(
    previewScenes.slice(
      previewScenes.indexOf("memory-buses") + 1,
      previewScenes.indexOf("instruction-control") + 1,
    ),
    [
      "computer-overview",
      "memory-width",
      "memory-interface",
      "memory-word",
      "memory-address-space",
      "memory-access",
      "memory-block",
      "working-registers",
      "select-values",
      "alu",
      "processing-block",
      "instruction",
      "addressed-memory",
      "instruction-control",
    ],
  );
  assert.ok(
    html.includes(
      "We used one earlier to choose which stored number reaches memory’s output.",
    ),
  );
  assert.deepEqual(
    previewScenes.slice(previewScenes.indexOf("instruction-control") + 1),
    [
      "program",
      "instruction-fetch",
      "execute",
      "control",
      "controller",
      "computer",
    ],
  );
  assert.ok(html.includes("LC-3"));
  assert.ok(
    html.includes(
      "Next, we will see how a task written by a person becomes the instruction bits that direct these circuits.",
    ),
  );
  assert.ok(!html.includes('class="footnote"'));
});

test("unknown scenes, incomplete chapters and empty endings fail the build", () => {
  for (const invalid of [
    { ...publication, publishedThrough: "missing" },
    { ...publication, publishedThrough: "quartz" },
    { ...publication, publishedThrough: "register" },
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
