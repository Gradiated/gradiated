import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const websiteRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = join(websiteRoot, "dist");
const serverRoot = join(outputRoot, "server");
const serverEntry = join(serverRoot, "entry-server.js");

const { getNotFoundPage, getSeoPages, renderPage } = await import(serverEntry);

const template = await readFile(join(outputRoot, "index.html"), "utf8");

const escapeHtml = (value) =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const absoluteUrl = (path) => new URL(path, "https://gradiated.com").toString();

const canonicalPath = (path) =>
  path === "/" ? "/" : `${path.replace(/\/+$/, "")}/`;

const renderHead = ({ metadata, path, structuredData, title }) => {
  const canonicalUrl = absoluteUrl(canonicalPath(path));
  const imageUrl = absoluteUrl(metadata.image);
  const graph = JSON.stringify({
    "@context": "https://schema.org",
    "@graph": structuredData,
  }).replaceAll("<", "\\u003c");
  const tags = [
    `<meta name="description" content="${escapeHtml(metadata.description)}" />`,
    `<meta name="robots" content="${metadata.index ? "index, follow" : "noindex, nofollow"}" />`,
    `<link rel="canonical" href="${canonicalUrl}" />`,
    '<meta property="og:site_name" content="Gradiated" />',
    `<meta property="og:type" content="${metadata.kind === "article" ? "article" : "website"}" />`,
    `<meta property="og:title" content="${escapeHtml(title)}" />`,
    `<meta property="og:description" content="${escapeHtml(metadata.description)}" />`,
    `<meta property="og:url" content="${canonicalUrl}" />`,
    `<meta property="og:image" content="${imageUrl}" />`,
    `<meta property="og:image:alt" content="${escapeHtml(`${metadata.title} - Gradiated`)}" />`,
    // The square brand mark is the only image made for a small card.
    `<meta name="twitter:card" content="${metadata.image.includes("gradiated-mark") ? "summary" : "summary_large_image"}" />`,
    `<meta name="twitter:title" content="${escapeHtml(title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(metadata.description)}" />`,
    `<meta name="twitter:image" content="${imageUrl}" />`,
  ];

  if (metadata.publishedAt) {
    tags.push(
      `<meta property="article:published_time" content="${metadata.publishedAt}" />`,
    );
  }
  if (metadata.kind === "article") {
    tags.push(
      `<meta property="article:modified_time" content="${metadata.updatedAt ?? metadata.publishedAt}" />`,
    );
  }
  if (structuredData.length > 0) {
    tags.push(
      `<script type="application/ld+json" data-page-structured-data>${graph}</script>`,
    );
  }

  return tags.join("\n    ");
};

const renderDocument = (page) => {
  const content = renderPage(page.path);
  return template
    .replace(/<meta\s+name="description"\s+content="[^"]*"\s*\/>/, "")
    .replace(
      /<title>[\s\S]*?<\/title>/,
      `<title>${escapeHtml(page.title)}</title>`,
    )
    .replace("<!-- page-seo -->", renderHead(page))
    .replace('<div id="root"></div>', `<div id="root">${content}</div>`);
};

const outputPathFor = (path) =>
  path === "/"
    ? join(outputRoot, "index.html")
    : join(outputRoot, path.replace(/^\//, ""), "index.html");

const pages = getSeoPages();
for (const page of pages) {
  const outputPath = outputPathFor(page.path);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, renderDocument(page));
}

const notFoundPage = getNotFoundPage();
await writeFile(join(outputRoot, "404.html"), renderDocument(notFoundPage));

const stripTags = (value) =>
  value
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const toPortableMarkdown = (source) =>
  source
    .replace(
      /<DocsLead>\s*([\s\S]*?)\s*<\/DocsLead>/g,
      (_match, content) => `${content.replace(/^ {2}/gm, "").trim()}\n`,
    )
    .replace(/<DocsCodeTab label="([^"]+)">/g, "\n### $1\n")
    .replace(/<DocsCodeVariant label="([^"]+)">/g, "\n#### $1\n")
    .replace(/<DocsNext>\s*([\s\S]*?)\s*<\/DocsNext>/g, (_match, content) =>
      [
        ...content.matchAll(
          /<a href="([^"]+)">\s*<small>([\s\S]*?)<\/small>\s*<strong>([\s\S]*?)<\/strong>\s*<\/a>/g,
        ),
      ]
        .map(
          ([, href, label, title]) =>
            `- [${stripTags(label)}: ${stripTags(title)}](${href})`,
        )
        .join("\n"),
    )
    .replace(
      /<a href="([^"]+)">([\s\S]*?)<\/a>/g,
      (_match, href, label) => `[${stripTags(label)}](${href})`,
    )
    .replace(
      /<DocsModelCatalog\s*\/>/g,
      "[View the live model catalog](https://api.gradiated.com/api/v1/models)",
    )
    .replace(/<DocsApiKeyAction\s*\/>/g, "")
    .replace(/<\/?Docs[A-Za-z]+(?:\s[^>]*)?>/g, "")
    .replace(/^[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .concat("\n");

const docsPages = pages.filter(({ path }) => path.startsWith("/docs/"));
const markdownPages = await Promise.all(
  docsPages.map(async ({ path }) => {
    const slug =
      path === "/docs/" ? "index" : path.split("/").filter(Boolean).at(-1);
    const source = await readFile(
      join(websiteRoot, "src", "docs", `${slug}.mdx`),
      "utf8",
    );
    return {
      content: toPortableMarkdown(source),
      path:
        path === "/docs/" ? "/docs/index.md" : `${path.replace(/\/$/, "")}.md`,
    };
  }),
);
for (const page of markdownPages) {
  const outputPath = join(outputRoot, page.path.replace(/^\//, ""));
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, page.content);
}

const sitemap = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ...pages
    .filter(({ metadata }) => metadata.index)
    .map(
      ({ path }) =>
        `  <url><loc>${absoluteUrl(canonicalPath(path))}</loc></url>`,
    ),
  "</urlset>",
  "",
].join("\n");
await writeFile(join(outputRoot, "sitemap.xml"), sitemap);

await writeFile(
  join(outputRoot, "robots.txt"),
  [
    "User-agent: *",
    "Allow: /",
    "",
    "Sitemap: https://gradiated.com/sitemap.xml",
    "",
  ].join("\n"),
);

const llmsText = [
  "# Gradiated",
  "",
  "> Software and hardware for affordable open-model inference.",
  "",
  "## Developer docs",
  "",
  ...docsPages.map(({ metadata, path }) => {
    const markdownPath =
      path === "/docs/" ? "/docs/index.md" : `${path.replace(/\/$/, "")}.md`;
    return `- [${metadata.title}](${absoluteUrl(markdownPath)}): ${metadata.description}`;
  }),
  "",
  "## Company",
  "",
  `- [About](${absoluteUrl("/about/")}): How Gradiated began inside PostHog and why it exists.`,
  `- [Careers](${absoluteUrl("/careers/")}): Open roles in inference software and silicon.`,
  `- [Thesis](${absoluteUrl("/library/our-thesis/")}): The Gradiated view of inference.`,
  "",
].join("\n");
await writeFile(join(outputRoot, "llms.txt"), llmsText);

const llmsFullText = [
  llmsText,
  ...markdownPages.map(({ content, path }) =>
    ["---", "", `Source: ${absoluteUrl(path)}`, "", content].join("\n"),
  ),
].join("\n");
await writeFile(join(outputRoot, "llms-full.txt"), llmsFullText);

await rm(serverRoot, { force: true, recursive: true });

console.log(
  `Generated ${pages.length} static pages and ${markdownPages.length} Markdown pages.`,
);
