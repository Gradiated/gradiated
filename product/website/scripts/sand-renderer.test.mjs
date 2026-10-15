import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const { renderPost } = createRequire(import.meta.url)("./sand-renderer.cjs");
const template = "<title>{{TITLE}}</title>{{ARTICLE}}";
const script = (text, notes = "") =>
  `# A & B\n\nOverview.\n\n## Chapter\n\n<!-- scene: one -->\n\n${text}\n\n<!-- footer -->\n\nEnding.\n\n${notes}`;
const render = (source) => renderPost(source, template, ["one"]);

test("repeated footnotes have unique references and a return link for each", () => {
  const html = render(
    script("First.[^note] Again.[^note]", "[^note]: A note."),
  );

  assert.ok(html.includes('id="fn-note-ref"'));
  assert.ok(html.includes('id="fn-note-ref-2"'));
  assert.ok(html.includes('href="#fn-note-ref" class="fn-back"'));
  assert.ok(html.includes('href="#fn-note-ref-2" class="fn-back"'));
  assert.equal((html.match(/id="fn-note"/g) ?? []).length, 1);
});

test("editorial cues stay private while ordinary blockquotes are published", () => {
  const html = render(
    script(
      "> **Visual cue** Private drawing direction.\n\n> A public quotation.\n\n<!-- Editorial note. -->\n\nArticle text.",
    ),
  );

  assert.ok(!html.includes("Private drawing direction"));
  assert.ok(!html.includes("Editorial note"));
  assert.ok(html.includes("<blockquote>"));
  assert.ok(html.includes("A public quotation."));
});

test("invalid footnotes fail rather than silently publishing broken links", () => {
  for (const source of [
    script("Missing.[^note]"),
    script("No reference.", "[^note]: Unused."),
    script("Reference.[^note]", "[^note]: First.\n[^note]: Duplicate."),
    script("Reference.[^note]", "[^note]: Nested.[^other]\n[^other]: Other."),
  ]) {
    assert.throws(() => render(source), /Footnote|footnote/);
  }
});

test("raw HTML and unsafe links cannot bypass Markdown restrictions", () => {
  for (const text of [
    "<script>alert(1)</script>",
    "Text <span>HTML</span>.",
    "[Unsafe](javascript:alert)",
    "[Unsafe](data:text/html,test)",
  ]) {
    assert.throws(() => render(script(text)), /HTML|protocol/);
  }
});

test("scene validation and literal dollar characters survive template rendering", () => {
  assert.throws(
    () => renderPost(script("Text."), template, ["other"]),
    /Scene order/,
  );
  assert.throws(
    () => renderPost(script("Text."), "{{ARTICLE}}", ["one"]),
    /Template/,
  );

  const html = render(script("A literal $& and $1."));
  assert.ok(html.includes("A literal $&amp; and $1."));
  assert.ok(html.includes("<title>A &amp; B</title>"));
});
