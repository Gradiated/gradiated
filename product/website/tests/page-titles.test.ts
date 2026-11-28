import { readdirSync } from "node:fs";
import { join } from "node:path";
import { isValidElement } from "react";
import { Navigate, createRoutesFromChildren } from "react-router-dom";
import { expect, it, vi } from "vitest";
import vercel from "../vercel.json";

/* Every route the router knows must have page metadata of its own —
   otherwise it ships with the 404 page's title, and if it is not
   prerendered it IS the 404 page on Vercel. Routes come from the real
   route tree so a new page is covered the moment it is added. */

const websiteRoot = join(import.meta.dirname, "..");

/* Article content is MDX, which the test runner does not compile; the
   routes are the paths declared in the files' front matter. Hoisted
   because vi.mock factories run before the module body. */
const { articlePaths } = vi.hoisted(() => {
  const fs = require("node:fs") as typeof import("node:fs");
  const path = require("node:path") as typeof import("node:path");
  const articleDir = path.join(__dirname, "..", "content", "articles");
  return {
    articlePaths: fs
      .readdirSync(articleDir)
      .filter((file) => file.endsWith(".mdx"))
      .map((file) => {
        const source = fs.readFileSync(path.join(articleDir, file), "utf8");
        return /^path:\s*(\S+)/m.exec(source)?.[1];
      })
      .filter((value): value is string => Boolean(value)),
  };
});

vi.mock("../src/articles", () => ({
  articles: articlePaths.map((path) => ({
    path,
    title: path,
    description: path,
    image: "/brand/png/gradiated-mark-dark-1024.png",
    publishedAt: "2026-01-01",
    status: "published",
    collection: "notes",
    layout: "note",
    author: "Ada Lovelace",
  })),
  authorOf: () => undefined,
}));
vi.mock("../src/handbook", () => ({
  handbookPages: [],
  handbookSections: [],
}));
vi.mock("../src/pages/DocsNextPage", () => ({ DocsNextPage: () => null }));
/* entry-server re-exports the generated docs for prerender, which import the
   MDX documents; the titles under test don't depend on them. */
vi.mock("../src/components/docs/training/generated-docs", () => ({
  docsGenerated: () => ({}),
}));
vi.mock("../src/pages/ReadingPages", () => ({
  ArticleReadingPage: () => null,
}));

import { AppRoutes, MovedJourney } from "../src/App";
import { getSeoPages } from "../src/entry-server";
import { getPageMetadata } from "../src/metadata";

const docsPaths = readdirSync(join(websiteRoot, "src", "docs"), {
  recursive: true,
})
  .map((entry) => String(entry).replaceAll("\\", "/"))
  .filter((file) => file.endsWith(".mdx"))
  .map((file) => file.replace(/\.mdx$/, ""))
  .map((slug) => {
    if (slug === "index") return "/docs/";
    if (slug.endsWith("/index"))
      return `/docs/${slug.slice(0, -"/index".length)}/`;
    return `/docs/${slug}/`;
  });

const redirectedAtTheEdge = new Set(
  vercel.redirects.map((redirect) => redirect.source),
);

const canonical = (path: string): string =>
  path === "/" ? "/" : `${path.replace(/\/+$/, "")}/`;

const routePaths = (): string[] => {
  const routes = createRoutesFromChildren(AppRoutes().props.children);
  return routes.flatMap((route) => {
    const { element, path } = route;
    if (!path || path === "*") return [];
    if (isValidElement(element) && element.type === Navigate) return [];
    if (isValidElement(element) && element.type === MovedJourney) return [];
    if (path === "/docs/*") return docsPaths;
    if (redirectedAtTheEdge.has(path)) return [];
    return [canonical(path)];
  });
};

it("walks the real route tree", () => {
  const paths = routePaths();
  expect(paths.length).toBeGreaterThan(40);
  expect(paths).toContain("/");
  expect(paths).toContain("/design/");
  expect(paths).toContain("/docs/quickstart/");
});

it("gives every route a title of its own", () => {
  const untitled = routePaths().filter(
    (path) => getPageMetadata(path).title === "Page not found",
  );
  expect(untitled).toEqual([]);
});

it("prerenders every route so none falls through to the 404 page", () => {
  const prerendered = new Set(
    getSeoPages().map((page) => canonical(page.path)),
  );
  const missing = routePaths().filter((path) => !prerendered.has(path));
  expect(missing).toEqual([]);
});
