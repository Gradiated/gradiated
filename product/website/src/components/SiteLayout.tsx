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
  const active = location.pathname.startsWith("/careers")
    ? "careers"
    : location.pathname.startsWith("/docs")
      ? "docs"
      : location.pathname.startsWith("/library") ||
          location.pathname.startsWith("/notes")
        ? "library"
        : "home";

  return (
    <header className="mx-auto flex h-[76px] max-w-content items-center border-b border-line px-7 max-site:h-[72px] max-site:flex-nowrap max-site:gap-0 max-site:px-5">
      <Link
        className="inline-flex items-center gap-2.5 font-newsreader text-[20px] font-medium leading-none tracking-wordmark transition-colors hover:text-accent"
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
      <nav className="ml-10 flex flex-1 items-center font-libre text-label font-medium uppercase tracking-label max-site:ml-3">
        <div className="flex items-center gap-7 text-left max-site:gap-3">
          <Link
            className={`transition-colors hover:text-accent max-site:hidden ${active === "home" ? "text-ink" : "text-muted"}`}
            to="/"
          >
            Home
          </Link>
          <Link
            className={`transition-colors hover:text-accent ${active === "docs" ? "text-ink" : "text-muted"}`}
            to="/docs/"
          >
            Docs
          </Link>
          <Link
            className={`transition-colors hover:text-accent ${active === "library" ? "text-ink" : "text-muted"}`}
            to="/library/"
          >
            Library
          </Link>
          <Link
            className={`transition-colors hover:text-accent ${active === "careers" ? "text-ink" : "text-muted"}`}
            to="/careers/"
          >
            Careers
          </Link>
        </div>
        <div className="ml-auto flex items-center justify-end gap-7 max-site:gap-3">
          <a
            className="border-b border-current pb-0.5 text-muted transition-colors hover:text-accent max-site:hidden"
            href="https://cal.com/jsgradiated/30min"
            rel="noreferrer"
          >
            Book a call
          </a>
          <a
            className="border border-ink px-4 pb-[9px] pt-[10px] leading-[11px] text-ink transition-colors hover:bg-ink hover:text-paper max-site:px-3"
            href="https://console.gradiated.com/"
            rel="noreferrer"
          >
            Log in
          </a>
        </div>
      </nav>
    </header>
  );
};

const SiteFooter = (): ReactElement => (
  <footer className="mx-auto grid max-w-content grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)] gap-x-16 border-t border-line px-7 py-12 font-libre text-[11px] font-medium uppercase tracking-footer text-muted max-site:grid-cols-2 max-site:gap-x-8 max-site:px-[22px] max-site:py-12">
    <div className="flex min-w-0 flex-col items-start">
      <Link
        className="font-newsreader text-[20px] font-medium normal-case tracking-wordmark text-ink transition-colors hover:text-accent"
        to="/"
      >
        Gradiated
      </Link>
      <span className="mt-4 max-w-[150px] leading-[1.6]">
        © 2026 Gradiated Ltd
      </span>
      <ThemeToggle />
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
  </footer>
);

export const SiteLayout = ({
  children,
  title,
  description = "Custom inference paths for open models.",
  home = false,
}: SiteLayoutProps): ReactElement => {
  const location = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.title = title;
    const descriptionElement = document.querySelector<HTMLMetaElement>(
      'meta[name="description"]',
    );
    descriptionElement?.setAttribute("content", description);
  }, [description, location.pathname, title]);

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
