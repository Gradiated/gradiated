import { useEffect, useState } from "react";
import type { ReactElement } from "react";

type Theme = "light" | "dark";

const getInitialTheme = (): Theme => {
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
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;

    const favicon = document.querySelector<HTMLLinkElement>(
      "link[data-theme-favicon]",
    );
    if (favicon) {
      favicon.href =
        theme === "dark"
          ? "/gradiated-logo-light-exact.png"
          : "/gradiated-logo-dark-exact.png";
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
      className="theme-toggle fixed bottom-6 right-7 z-[5] m-0 w-32 border-0 bg-transparent px-0 py-2 text-right font-libre text-label font-medium uppercase tracking-label text-muted opacity-subtle transition-opacity duration-200 hover:text-ink hover:opacity-100 focus-visible:text-ink focus-visible:opacity-100 max-site:relative max-site:bottom-auto max-site:right-auto max-site:ml-auto max-site:w-auto max-site:p-0"
      type="button"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={dark}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      <span className="theme-question">
        {dark ? "Light" : "Dark"}
        <i>?</i>
      </span>
      <span className="theme-consider" aria-hidden="true">
        Consider {alternative} →
      </span>
    </button>
  );
};
