import assert from "node:assert/strict";
import test from "node:test";

import { articleBody, excerpt, renderFeed } from "./feed.mjs";

const absoluteUrl = (path) => new URL(path, "https://gradiated.com").toString();

const page = (prose) =>
  `<main><article><header><h1>Title</h1></header><div class="gr-prose">${prose}</div><footer>Related</footer></article></main>`;

const article = ({ html = page("<p>Body.</p>"), ...metadata }) => ({
  html,
  metadata: {
    author: "Ada Lovelace",
    description: "A short description.",
    image: "/brand/library/poster.jpg",
    title: "A piece",
    ...metadata,
  },
  url: absoluteUrl(`/library/${metadata.slug ?? "a-piece"}/`),
});

test("the article body is the whole prose block, nested blocks included", () => {
  const body = articleBody(
    page("<p>One</p><div><div><p>Two</p></div></div><p>Three</p>"),
    absoluteUrl,
  );

  assert.equal(body, "<p>One</p><div><div><p>Two</p></div></div><p>Three</p>");
});

test("the article body drops controls and makes site links absolute", () => {
  const body = articleBody(
    page(
      [
        '<a href="/team/ada/">Ada</a>',
        '<a href="https://example.com/">Elsewhere</a>',
        '<a href="#note">Note</a>',
        '<img src="/a.png" srcset="/a.png 1x, /a@2x.png 2x" />',
        '<img src="//cdn.example.com/b.png" />',
        '<button type="button">Toggle</button>',
        "<script>run()</script>",
      ].join(""),
    ),
    absoluteUrl,
  );

  assert.equal(
    body,
    [
      '<a href="https://gradiated.com/team/ada/">Ada</a>',
      '<a href="https://example.com/">Elsewhere</a>',
      '<a href="#note">Note</a>',
      '<img src="https://gradiated.com/a.png" srcset="https://gradiated.com/a.png 1x, https://gradiated.com/a@2x.png 2x" />',
      '<img src="//cdn.example.com/b.png" />',
    ].join(""),
  );
});

test("a page without a prose block has no article body", () => {
  assert.equal(articleBody("<main><canvas></canvas></main>", absoluteUrl), "");
});

test("the excerpt is plain text cut at a word to 150 characters", () => {
  const sentence = "Word ".repeat(40).trim();
  const text = excerpt(
    `<h2>Heading</h2><p>It&#x27;s <a href="/x">linked</a>, then</p><p>${sentence}</p>`,
    "Fallback",
  );

  assert.ok(text.startsWith("It's linked, then Word Word"));
  assert.ok(text.endsWith("Word…"));
  assert.ok(text.length <= 151);
  assert.equal(excerpt("<p>Short.</p>", "Fallback"), "Short.");
});

test("the excerpt falls back to the description without paragraphs", () => {
  assert.equal(excerpt("", "Fallback"), "Fallback");
});

test("the feed lists pieces newest first with their art and full text", () => {
  const feed = renderFeed({
    absoluteUrl,
    articles: [
      article({ publishedAt: "2026-10-01", slug: "older" }),
      article({
        html: "<main><canvas></canvas></main>",
        publishedAt: "2026-11-01",
        slug: "journey",
        updatedAt: "2026-11-20",
      }),
      article({ publishedAt: "2026-11-01", slug: "newer", title: "R&D" }),
    ],
    description: "The Library.",
  });
  const entries = feed.split("<entry>").slice(1);

  assert.match(feed, /^<\?xml version="1\.0" encoding="UTF-8"\?>\n<feed /);
  assert.match(feed, /<updated>2026-11-20T00:00:00Z<\/updated>\n {2}<icon>/);
  assert.deepEqual(
    entries.map((entry) => entry.match(/<id>([^<]+)<\/id>/)[1]),
    [
      "https://gradiated.com/library/journey/",
      "https://gradiated.com/library/newer/",
      "https://gradiated.com/library/older/",
    ],
  );
  assert.match(entries[1], /<title>R&amp;D<\/title>/);
  assert.match(
    entries[1],
    /<link rel="enclosure" type="image\/jpeg" href="https:\/\/gradiated\.com\/brand\/library\/poster\.jpg" \/>/,
  );
  assert.match(entries[1], /<author><name>Ada Lovelace<\/name><\/author>/);
  assert.match(entries[1], /<summary>Body\.<\/summary>/);
  assert.match(
    entries[1],
    /<content type="html">&lt;p&gt;Body\.&lt;\/p&gt;<\/content>/,
  );
  assert.match(entries[0], /<summary>A short description\.<\/summary>/);
  assert.doesNotMatch(entries[0], /<content/);
});
