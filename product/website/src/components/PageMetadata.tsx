import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import {
  absoluteUrl,
  formatPageTitle,
  getPageMetadata,
  getStructuredData,
} from "../metadata";

/* The document head, kept in step with the route on the client. The
   prerender writes the same tags into each page's static HTML; this is
   what updates them when the router moves without a reload. Mounted
   once, under the router, for every route — a page can't forget it. */

const setMetaContent = (
  attribute: "name" | "property",
  key: string,
  content?: string,
): void => {
  const selector = `meta[${attribute}="${key}"]`;
  const current = document.querySelector<HTMLMetaElement>(selector);
  if (!content) {
    current?.remove();
    return;
  }

  const element = current ?? document.createElement("meta");
  element.setAttribute(attribute, key);
  element.content = content;
  if (!current) document.head.append(element);
};

const setCanonicalUrl = (url: string): void => {
  const current = document.querySelector<HTMLLinkElement>(
    'link[rel="canonical"]',
  );
  const element = current ?? document.createElement("link");
  element.rel = "canonical";
  element.href = url;
  if (!current) document.head.append(element);
};

const setStructuredData = (data: object[]): void => {
  const current = document.querySelector<HTMLScriptElement>(
    "script[data-page-structured-data]",
  );
  if (data.length === 0) {
    current?.remove();
    return;
  }

  const element = current ?? document.createElement("script");
  element.type = "application/ld+json";
  element.dataset.pageStructuredData = "true";
  element.textContent = JSON.stringify({
    "@context": "https://schema.org",
    "@graph": data,
  });
  if (!current) document.head.append(element);
};

export const usePageMetadata = (): void => {
  const { pathname } = useLocation();
  const canonicalPath =
    pathname === "/" ? "/" : `${pathname.replace(/\/+$/, "")}/`;

  useEffect(() => {
    const metadata = getPageMetadata(canonicalPath);
    const title = formatPageTitle(metadata.title);
    const canonicalUrl = absoluteUrl(canonicalPath);
    const imageUrl = absoluteUrl(metadata.image);

    document.title = title;
    setCanonicalUrl(canonicalUrl);
    setMetaContent("name", "description", metadata.description);
    setMetaContent(
      "name",
      "robots",
      metadata.index ? "index, follow" : "noindex, nofollow",
    );
    setMetaContent("property", "og:site_name", "Gradiated");
    setMetaContent(
      "property",
      "og:type",
      metadata.kind === "article" ? "article" : "website",
    );
    setMetaContent("property", "og:title", title);
    setMetaContent("property", "og:description", metadata.description);
    setMetaContent("property", "og:url", canonicalUrl);
    setMetaContent("property", "og:image", imageUrl);
    setMetaContent("property", "og:image:alt", `${metadata.title} - Gradiated`);
    setMetaContent("property", "article:published_time", metadata.publishedAt);
    setMetaContent(
      "property",
      "article:modified_time",
      metadata.kind === "article"
        ? (metadata.updatedAt ?? metadata.publishedAt)
        : undefined,
    );
    setMetaContent(
      "name",
      "twitter:card",
      metadata.image.startsWith("/assets/") ? "summary_large_image" : "summary",
    );
    setMetaContent("name", "twitter:title", title);
    setMetaContent("name", "twitter:description", metadata.description);
    setMetaContent("name", "twitter:image", imageUrl);
    setStructuredData(getStructuredData(canonicalPath));
  }, [canonicalPath]);
};

export const PageMetadata = (): null => {
  usePageMetadata();
  return null;
};
