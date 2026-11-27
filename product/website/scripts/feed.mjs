// The Library's Atom feed (/feed.xml), built from the prerendered pages.
//
// Each entry carries the title, a 150-character excerpt, the full article as
// HTML, the URL (also its id), the author and the poster art. Journey pieces
// are interactive pages with no article body, so they carry the excerpt only.

const EXCERPT_LENGTH = 150;

const IMAGE_TYPES = {
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
};

const escapeXml = (value) =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const decodeEntities = (value) =>
  value
    .replace(/&#x([0-9a-f]+);/gi, (_match, hex) =>
      String.fromCodePoint(parseInt(hex, 16)),
    )
    .replace(/&#(\d+);/g, (_match, code) => String.fromCodePoint(Number(code)))
    .replaceAll("&quot;", '"')
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&nbsp;", " ")
    .replaceAll("&amp;", "&");

const imageType = (path) =>
  IMAGE_TYPES[path.slice(path.lastIndexOf(".")).toLowerCase()] ?? "image/*";

const atomTime = (date) => `${date}T00:00:00Z`;

/**
 * The article body from a rendered page: the inside of its `.gr-prose` block,
 * without scripts, styles or buttons, and with site-relative links and images
 * made absolute so they work in a feed reader. Empty when the page has none.
 */
export const articleBody = (html, absoluteUrl) => {
  const open = html.match(/<div[^>]*\bclass="gr-prose[" ][^>]*>/);
  if (!open) return "";

  const rest = html.slice(open.index + open[0].length);
  let depth = 1;
  for (const tag of rest.matchAll(/<\/?div\b[^>]*>/g)) {
    depth += tag[0].startsWith("</") ? -1 : 1;
    if (depth > 0) continue;

    return rest
      .slice(0, tag.index)
      .replace(/<(script|style|button)\b[\s\S]*?<\/\1>/g, "")
      .replace(
        /\s(href|src|poster)="(\/(?!\/)[^"]*)"/g,
        (_match, attribute, path) => ` ${attribute}="${absoluteUrl(path)}"`,
      )
      .replace(/\ssrcset="([^"]*)"/g, (_match, candidates) => {
        const absolute = candidates.split(",").map((candidate) => {
          const [url, ...descriptor] = candidate.trim().split(/\s+/);
          const resolved = /^\/(?!\/)/.test(url) ? absoluteUrl(url) : url;
          return [resolved, ...descriptor].join(" ");
        });
        return ` srcset="${absolute.join(", ")}"`;
      })
      .trim();
  }
  return "";
};

/**
 * The opening paragraphs of an article body as plain text, cut at a word
 * boundary to at most 150 characters. Falls back when the body has none.
 */
export const excerpt = (body, fallback) => {
  const text = decodeEntities(
    [...body.matchAll(/<p[\s>][\s\S]*?<\/p>/g)]
      .map(([paragraph]) => paragraph.replace(/<[^>]+>/g, " "))
      .join(" "),
  )
    .replace(/\s+/g, " ")
    .replace(/ ([,.;:!?])/g, "$1")
    .trim();

  if (!text) return fallback;
  if (text.length <= EXCERPT_LENGTH) return text;

  const cut = text.slice(0, EXCERPT_LENGTH);
  return `${cut.slice(0, cut.lastIndexOf(" ")).replace(/[\s,.;:]+$/, "")}…`;
};

const renderEntry = ({ body, metadata, url }, absoluteUrl) => {
  const imageUrl = absoluteUrl(metadata.image);
  return [
    "  <entry>",
    `    <title>${escapeXml(metadata.title)}</title>`,
    `    <id>${url}</id>`,
    `    <link rel="alternate" type="text/html" href="${url}" />`,
    `    <link rel="enclosure" type="${imageType(metadata.image)}" href="${imageUrl}" />`,
    `    <media:thumbnail url="${imageUrl}" />`,
    `    <published>${atomTime(metadata.publishedAt)}</published>`,
    `    <updated>${atomTime(metadata.updatedAt ?? metadata.publishedAt)}</updated>`,
    `    <author><name>${escapeXml(metadata.author)}</name></author>`,
    `    <summary>${escapeXml(excerpt(body, metadata.description))}</summary>`,
    ...(body ? [`    <content type="html">${escapeXml(body)}</content>`] : []),
    "  </entry>",
  ];
};

/**
 * Renders the feed. `articles` are `{ html, metadata, url }` for each
 * published piece, `html` being its prerendered page. Newest first; pieces
 * published the same day are ordered by URL so the output is stable.
 */
export const renderFeed = ({ absoluteUrl, articles, description }) => {
  const entries = articles
    .map(({ html, metadata, url }) => ({
      body: articleBody(html, absoluteUrl),
      metadata,
      url,
    }))
    .sort(
      (a, b) =>
        b.metadata.publishedAt.localeCompare(a.metadata.publishedAt) ||
        a.url.localeCompare(b.url),
    );
  const updated = entries
    .map(({ metadata }) => metadata.updatedAt ?? metadata.publishedAt)
    .sort()
    .at(-1);
  const libraryUrl = absoluteUrl("/library/");

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">',
    "  <title>Gradiated Library</title>",
    `  <subtitle>${escapeXml(description)}</subtitle>`,
    `  <id>${libraryUrl}</id>`,
    `  <link rel="alternate" type="text/html" href="${libraryUrl}" />`,
    `  <link rel="self" type="application/atom+xml" href="${absoluteUrl("/feed.xml")}" />`,
    `  <updated>${updated ? atomTime(updated) : new Date().toISOString()}</updated>`,
    `  <icon>${absoluteUrl("/favicon.ico")}</icon>`,
    `  <logo>${absoluteUrl("/brand/png/gradiated-mark-dark-1024.png")}</logo>`,
    ...entries.flatMap((entry) => renderEntry(entry, absoluteUrl)),
    "</feed>",
    "",
  ].join("\n");
};
