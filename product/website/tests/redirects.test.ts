import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import vercel from "../vercel.json";

vi.mock("../src/articles", () => ({ articles: [] }));
vi.mock("../src/careers", () => ({ jobs: [] }));
vi.mock("../src/pages/DocsNextPage", () => ({
  DocsNextPage: () => null,
}));
vi.mock("../src/pages/ReadingPages", () => ({
  ArticleReadingPage: () => null,
}));
vi.mock("../src/handbook", () => ({
  handbookPages: [],
  handbookSections: [],
}));
vi.mock("../src/models", () => ({ models: [] }));

import { AppRoutes } from "../src/App";

const renderLibrary = (search = ""): string =>
  renderToString(
    createElement(
      StaticRouter,
      { location: `/library/${search}` },
      createElement(AppRoutes),
    ),
  );

it("keeps the Library hydration fallback independent of its query string", () => {
  const fallback = renderLibrary();

  expect(renderLibrary("?show=methods")).toBe(fallback);
  expect(renderLibrary("?show=handbook")).toBe(fallback);
  expect(fallback).toContain("gr-mag-masthead");
  expect(fallback).not.toContain("gr-handbook-index");
});

it("redirects every former Library and Methods URL at the server", () => {
  expect(vercel.redirects).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        source: "/library/",
        destination: "/handbook/",
        has: [
          {
            type: "query",
            key: "show",
            value: "(?:methods|handbook)",
          },
        ],
      }),
      expect.objectContaining({
        source: "/methods/",
        destination: "/handbook/",
      }),
      expect.objectContaining({
        source: "/methods/:slug/",
        destination: "/handbook/:slug/",
      }),
      expect.objectContaining({
        source: "/library/method/:slug/",
        destination: "/handbook/:slug/",
      }),
    ]),
  );
});
