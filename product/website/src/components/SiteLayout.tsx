import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";
import { PathField } from "./PathField";
import { ThemeToggle } from "./ThemeToggle";

type SiteLayoutProps = {
  children: ReactNode;
  title: string;
  description?: string;
  home?: boolean;
};

const SiteHeader = (): ReactElement => {
  const location = useLocation();
  const active = location.pathname.startsWith("/products")
    ? "products"
    : location.pathname.startsWith("/docs")
      ? "docs"
      : location.pathname.startsWith("/library") ||
          location.pathname.startsWith("/notes")
        ? "library"
        : "home";

  return (
    <header className="nav mx-auto flex h-[76px] max-w-content items-center border-b border-line px-7 max-site:h-[72px] max-site:flex-nowrap max-site:gap-0 max-site:px-5">
      <Link
        className="wordmark inline-flex items-center gap-2.5 font-newsreader text-[20px] font-medium leading-none tracking-wordmark"
        to="/"
        aria-label="Gradiated home"
      >
        <img
          className="wordmark-logo"
          src="/brand/gradiated-mark-dark.svg"
          alt=""
          width="25"
          height="25"
        />
        gradiated
      </Link>
      <nav className="ml-auto mr-0 flex gap-7 font-libre text-label font-medium uppercase tracking-label max-site:order-none max-site:w-auto max-site:gap-5">
        <Link
          className={`text-muted ${active === "home" ? "active text-ink" : ""} max-site:first:hidden`}
          to="/"
        >
          Home
        </Link>
        <Link
          className={active === "products" ? "active text-ink" : "text-muted"}
          to="/products/"
        >
          Products
        </Link>
        <Link
          className={active === "docs" ? "active text-ink" : "text-muted"}
          to="/docs/"
        >
          Docs
        </Link>
        <Link
          className={active === "library" ? "active text-ink" : "text-muted"}
          to="/library/"
        >
          Library
        </Link>
      </nav>
    </header>
  );
};

const SiteFooter = (): ReactElement => (
  <footer className="relative mx-auto min-h-0 max-w-content border-t border-line px-7 pb-10 pt-6 font-libre text-label font-medium uppercase tracking-footer text-muted max-site:flex max-site:flex-wrap max-site:gap-5 max-site:px-5 max-site:pb-9">
    <Link className="text-ink" to="/">
      Gradiated
    </Link>
    <span>© 2026 Gradiated Ltd</span>
    <div className="ml-auto flex flex-wrap gap-5 max-site:ml-auto">
      <Link className="text-ink" to="/privacy/">
        Privacy
      </Link>
      <Link className="text-ink" to="/terms/">
        Terms
      </Link>
      <Link className="text-ink" to="/acceptable-use/">
        Acceptable use
      </Link>
      <Link className="text-ink" to="/dpa/">
        DPA
      </Link>
      <Link className="text-ink" to="/subprocessors-security/">
        Security
      </Link>
      <a
        className="text-ink"
        href="https://status.gradiated.com/"
        rel="noreferrer"
      >
        Status
      </a>
    </div>
    <ThemeToggle />
  </footer>
);

export const SiteLayout = ({
  children,
  title,
  description = "Custom inference paths for open models.",
  home = false,
}: SiteLayoutProps): ReactElement => {
  useEffect(() => {
    document.title = title;
    const descriptionElement = document.querySelector<HTMLMetaElement>(
      'meta[name="description"]',
    );
    descriptionElement?.setAttribute("content", description);
  }, [description, title]);

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
