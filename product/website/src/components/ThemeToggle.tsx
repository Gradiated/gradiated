import { useEffect, useState } from "react";
import type { ReactElement } from "react";

type Theme = "light" | "dark";

const getInitialTheme = (): Theme => {
  if (typeof window === "undefined") return "light";

  try {
    const savedTheme = localStorage.getItem("gradiated-theme");
    if (savedTheme === "dark" || savedTheme === "light") return savedTheme;
  } catch {
    // Ignore storage errors and use the system preference.
  }

  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
};

export const ThemeToggle = (): ReactElement => {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(getInitialTheme());
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;

    const favicon = document.querySelector<HTMLLinkElement>(
      "link[data-theme-favicon]",
    );
    if (favicon) {
      favicon.href =
        theme === "dark"
          ? "/brand/gradiated-mark-light.svg"
          : "/brand/gradiated-mark-dark.svg";
    }

    try {
      localStorage.setItem("gradiated-theme", theme);
    } catch {
      // Ignore storage errors.
    }
  }, [theme]);

  const dark = theme === "dark";
  const alternative = dark ? "light" : "dark";

  return (
    <button
      className="group fixed bottom-6 right-7 z-[5] m-0 w-32 border-0 bg-transparent px-0 py-2 text-right font-libre text-label font-medium uppercase tracking-label text-muted opacity-subtle transition-opacity duration-200 hover:text-ink hover:opacity-100 focus-visible:text-ink focus-visible:opacity-100 max-site:relative max-site:bottom-auto max-site:right-auto max-site:mt-8 max-site:w-auto max-site:p-0 max-site:text-left max-site:opacity-70"
      type="button"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={dark}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      <span className="block transition-opacity duration-150 group-hover:opacity-0 group-focus-visible:opacity-0">
        {dark ? "Light" : "Dark"}
        <i className="not-italic text-accent">?</i>
      </span>
      <span
        className="absolute right-0 top-2 block w-full whitespace-nowrap text-ink opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 max-site:left-0 max-site:right-auto max-site:top-0"
        aria-hidden="true"
      >
        Consider {alternative} →
      </span>
    </button>
  );
};
