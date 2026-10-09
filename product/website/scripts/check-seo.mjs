import { readFile, readdir } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const websiteRoot = join(fileURLToPath(new URL("..", import.meta.url)));
const outputRoot = join(websiteRoot, "dist");
const files = await readdir(outputRoot, { recursive: true });
const htmlFiles = files.filter(
  (file) => file === "index.html" || file.endsWith("/index.html"),
);

const valueOf = (html, pattern, label, file) => {
  const matches = [...html.matchAll(pattern)];
  if (matches.length !== 1) {
    throw new Error(
      `${file} must contain one ${label}. Found ${matches.length}.`,
    );
  }
  return matches[0][1];
};

const seenTitles = new Map();
const seenDescriptions = new Map();
const seenCanonicals = new Map();

for (const file of htmlFiles) {
  const html = await readFile(join(outputRoot, file), "utf8");
  const title = valueOf(html, /<title>([^<]+)<\/title>/g, "title", file);
  const description = valueOf(
    html,
    /<meta name="description" content="([^"]+)" \/>/g,
    "meta description",
    file,
  );
  const canonical = valueOf(
    html,
    /<link rel="canonical" href="([^"]+)" \/>/g,
    "canonical URL",
    file,
  );
  valueOf(
    html,
    /<meta name="robots" content="([^"]+)" \/>/g,
    "robots meta tag",
    file,
  );
  valueOf(
    html,
    /<meta property="og:title" content="([^"]+)" \/>/g,
    "Open Graph title",
    file,
  );
  valueOf(
    html,
    /<meta property="og:description" content="([^"]+)" \/>/g,
    "Open Graph description",
    file,
  );
  valueOf(
    html,
    /<meta name="twitter:title" content="([^"]+)" \/>/g,
    "Twitter title",
    file,
  );
  valueOf(
    html,
    /<meta name="twitter:description" content="([^"]+)" \/>/g,
    "Twitter description",
    file,
  );
  valueOf(
    html,
    /<script type="application\/ld\+json" data-page-structured-data>([\s\S]*?)<\/script>/g,
    "structured data block",
    file,
  );

  const h1Count = (html.match(/<h1(?:\s|>)/g) ?? []).length;
  if (h1Count !== 1) {
    throw new Error(`${file} must contain one h1. Found ${h1Count}.`);
  }
  if (html.includes("Loading docs") || html.includes("Loading page")) {
    throw new Error(`${file} contains a docs loading fallback.`);
  }
  if (html.includes('<meta property="og:type" content="article" />')) {
    const publishedAt = valueOf(
      html,
      /<meta property="article:published_time" content="([^"]+)" \/>/g,
      "article publication date",
      file,
    );
    const modifiedAt = valueOf(
      html,
      /<meta property="article:modified_time" content="([^"]+)" \/>/g,
      "article modification date",
      file,
    );
    const graph = JSON.parse(
      valueOf(
        html,
        /<script type="application\/ld\+json" data-page-structured-data>([\s\S]*?)<\/script>/g,
        "article structured data",
        file,
      ),
    );
    const article = graph["@graph"].find(
      (entry) => entry["@type"] === "Article",
    );
    if (
      !article ||
      article.datePublished !== publishedAt ||
      article.dateModified !== modifiedAt ||
      article.mainEntityOfPage !== canonical
    )
      throw new Error(`${file}: inconsistent article metadata`);
    if (
      !html.includes(`<time dateTime="${publishedAt}">`) &&
      !html.includes(`<time datetime="${publishedAt}">`)
    )
      throw new Error(`${file}: publication date is not displayed`);
  }

  for (const [value, seen, label] of [
    [title, seenTitles, "title"],
    [description, seenDescriptions, "description"],
    [canonical, seenCanonicals, "canonical URL"],
  ]) {
    const previous = seen.get(value);
    if (previous) {
      throw new Error(
        `${file} and ${previous} use the same ${label}: ${value}`,
      );
    }
    seen.set(value, file);
  }
}

const notFoundHtml = await readFile(join(outputRoot, "404.html"), "utf8");
if (
  !notFoundHtml.includes('<meta name="robots" content="noindex, nofollow" />')
) {
  throw new Error("404.html must use noindex, nofollow.");
}

const sitemap = await readFile(join(outputRoot, "sitemap.xml"), "utf8");
const sitemapUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
  (match) => match[1],
);
if (sitemapUrls.length !== htmlFiles.length) {
  throw new Error(
    `The sitemap has ${sitemapUrls.length} URLs for ${htmlFiles.length} indexable pages.`,
  );
}

for (const markdownFile of files.filter((file) => file.endsWith(".md"))) {
  const markdown = await readFile(join(outputRoot, markdownFile), "utf8");
  if (!markdown.startsWith("# ")) {
    throw new Error(
      `${relative(outputRoot, markdownFile)} must start with an h1.`,
    );
  }
}

const securityTxt = await readFile(
  join(outputRoot, ".well-known/security.txt"),
  "utf8",
);
if (!/^Contact: \S+$/m.test(securityTxt)) {
  throw new Error(".well-known/security.txt must contain a Contact field.");
}
const securityExpires = Date.parse(
  securityTxt.match(/^Expires: (\S+)$/m)?.[1] ?? "",
);
if (!(securityExpires > Date.now())) {
  throw new Error(
    ".well-known/security.txt has expired. Set Expires to a date less than a year away.",
  );
}

console.log(`SEO checks passed for ${htmlFiles.length} static pages.`);
