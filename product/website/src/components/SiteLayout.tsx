import { WaitlistButton } from "./WaitlistButton";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";
import {
  absoluteUrl,
  formatPageTitle,
  getPageMetadata,
  getStructuredData,
} from "../metadata";
import { PathField } from "./PathField";
import { ThemeToggle } from "./ThemeToggle";

type SiteLayoutProps = {
  children: ReactNode;
  home?: boolean;
};

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

const SiteHeader = (): ReactElement => {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const mobileMenuLinkClass =
    "border-b border-line py-3 text-ink transition-colors last:border-b-0 hover:text-accent";
  const active = location.pathname.startsWith("/careers")
    ? "careers"
    : location.pathname.startsWith("/docs")
      ? "docs"
      : location.pathname.startsWith("/library") ||
          location.pathname.startsWith("/notes")
        ? "library"
        : "home";

  return (
    <header
      className="relative mx-auto flex h-[76px] max-w-content items-center border-b border-line px-7 max-[850px]:h-[72px] max-[850px]:flex-nowrap max-[850px]:gap-0 max-[850px]:px-5 max-[420px]:px-4"
      style={{ zIndex: 40 }}
    >
      <Link
        className="inline-flex shrink-0 items-center gap-2.5 font-newsreader text-[20px] font-medium leading-none tracking-wordmark transition-colors hover:text-accent"
        to="/"
        aria-label="Gradiated home"
      >
        <img
          className="h-[25px] w-[25px] max-site:h-[23px] max-site:w-[23px]"
          src="/brand/gradiated-mark-dark.svg"
          alt=""
          width="25"
          height="25"
        />
        gradiated
      </Link>
      <nav className="ml-10 flex min-w-0 flex-1 items-center font-libre text-label font-medium uppercase tracking-label max-[850px]:ml-5 max-site:ml-3 max-[420px]:ml-2">
        <div className="flex items-center gap-7 whitespace-nowrap text-left max-[850px]:gap-5 max-site:gap-3 max-[420px]:gap-2">
          <Link
            className={`transition-colors hover:text-accent max-[850px]:hidden ${active === "home" ? "text-ink" : "text-muted"}`}
            to="/"
          >
            Home
          </Link>
          <Link
            className={`transition-colors hover:text-accent max-[850px]:hidden ${active === "docs" ? "text-ink" : "text-muted"}`}
            to="/docs/"
          >
            Docs
          </Link>
          <Link
            className={`transition-colors hover:text-accent max-[850px]:hidden ${active === "library" ? "text-ink" : "text-muted"}`}
            to="/library/"
          >
            Library
          </Link>
          <Link
            className={`transition-colors hover:text-accent max-[850px]:hidden ${active === "careers" ? "text-ink" : "text-muted"}`}
            to="/careers/"
          >
            Careers
          </Link>
        </div>
        <div className="ml-auto flex items-center justify-end gap-7 max-site:gap-3">
          <a
            className="border-b border-current pb-0.5 text-muted transition-colors hover:text-accent max-[850px]:hidden"
            href="https://cal.com/jsgradiated/30min"
            rel="noreferrer"
          >
            Book a call
          </a>
          <WaitlistButton className="border border-ink px-4 pb-[9px] pt-[10px] leading-[11px] text-ink transition-colors hover:bg-ink hover:text-paper max-[1100px]:hidden">
            Request beta access
          </WaitlistButton>
          <button
            aria-controls="mobile-site-menu"
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            className="hidden h-9 cursor-pointer items-center gap-2 border-0 bg-transparent p-0 font-libre text-label font-medium uppercase tracking-label text-ink max-[850px]:flex"
            onClick={() => setMenuOpen((current) => !current)}
            type="button"
          >
            Menu
            <span aria-hidden="true" className="relative h-3.5 w-4">
              <span
                className={`absolute left-0 top-1 block h-px w-4 bg-current transition-transform ${menuOpen ? "translate-y-[3px] rotate-45" : ""}`}
              />
              <span
                className={`absolute bottom-1 left-0 block h-px w-4 bg-current transition-transform ${menuOpen ? "-translate-y-[3px] -rotate-45" : ""}`}
              />
            </span>
          </button>
        </div>
      </nav>
      {menuOpen && (
        <nav
          aria-label="Mobile navigation"
          className="absolute left-0 right-0 top-full z-30 grid border-b border-line bg-paper px-5 py-5 font-libre text-[11px] font-medium uppercase tracking-label shadow-[0_16px_28px_rgba(28,27,24,0.08)] min-[851px]:hidden max-[420px]:px-4"
          id="mobile-site-menu"
        >
          {[
            { label: "Home", to: "/" },
            { label: "Docs", to: "/docs/" },
            { label: "Library", to: "/library/" },
            { label: "Careers", to: "/careers/" },
          ].map((item) => (
            <Link
              className={mobileMenuLinkClass}
              key={item.to}
              onClick={() => setMenuOpen(false)}
              to={item.to}
            >
              {item.label}
            </Link>
          ))}
          <a
            className={mobileMenuLinkClass}
            href="https://cal.com/jsgradiated/30min"
            rel="noreferrer"
          >
            Book a demo
          </a>
          <WaitlistButton className={mobileMenuLinkClass}>
            Request beta access
          </WaitlistButton>
        </nav>
      )}
    </header>
  );
};

const SiteFooter = (): ReactElement => (
  <footer className="mx-auto grid max-w-content grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)] gap-x-16 border-t border-line px-7 py-12 font-libre text-[11px] font-medium uppercase tracking-footer text-muted max-site:grid-cols-1 max-site:gap-x-0 max-site:gap-y-12 max-site:px-[22px] max-site:py-12">
    <div className="flex min-w-0 flex-col items-start">
      <Link
        className="font-newsreader text-[20px] font-medium normal-case tracking-wordmark text-ink transition-colors hover:text-accent"
        to="/"
      >
        Gradiated
      </Link>
      <span className="mt-4 max-w-[150px] leading-[1.6]">
        © 2026 PostHog Inc.
      </span>
    </div>
    <nav className="grid grid-cols-2 gap-x-10 gap-y-4 max-site:grid-cols-1 max-site:content-start max-site:justify-items-start">
      <Link
        className="text-ink transition-colors hover:text-accent"
        to="/privacy/"
      >
        Privacy
      </Link>
      <Link
        className="text-ink transition-colors hover:text-accent"
        to="/terms/"
      >
        Terms
      </Link>
      <Link
        className="text-ink transition-colors hover:text-accent"
        to="/acceptable-use/"
      >
        Acceptable use
      </Link>
      <Link className="text-ink transition-colors hover:text-accent" to="/dpa/">
        DPA
      </Link>
      <Link
        className="text-ink transition-colors hover:text-accent"
        to="/careers/"
      >
        Careers
      </Link>
      <Link
        className="text-ink transition-colors hover:text-accent"
        to="/subprocessors-security/"
      >
        Security
      </Link>
      <a
        className="text-ink transition-colors hover:text-accent"
        href="https://status.gradiated.com/"
        rel="noreferrer"
      >
        Status
      </a>
    </nav>
    <ThemeToggle />
  </footer>
);

export const SiteLayout = ({
  children,
  home = false,
}: SiteLayoutProps): ReactElement => {
  const location = useLocation();
  const metadata = getPageMetadata(location.pathname);
  const canonicalPath =
    location.pathname === "/"
      ? "/"
      : `${location.pathname.replace(/\/+$/, "")}/`;

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
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
  }, [
    canonicalPath,
    location.pathname,
    metadata.description,
    metadata.image,
    metadata.index,
    metadata.kind,
    metadata.publishedAt,
    metadata.updatedAt,
    metadata.title,
  ]);

  return (
    <div
      className={`page-shell relative min-h-screen overflow-hidden${home ? " home-page" : ""}`}
    >
      {home && <PathField />}
      <SiteHeader />
      {children}
      <SiteFooter />
    </div>
  );
};
