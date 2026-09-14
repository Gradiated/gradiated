/**
 * The theme a reader chose, and where it lives.
 *
 * Two jobs that were previously one, which is what broke persistence: APPLYING
 * a theme and SAVING one are separate events. The selector used a single effect
 * for both, so every mount wrote its own initial state — taupe — to storage
 * before the stored value had been read back, and a page change quietly reset
 * the reader's choice. Saving now happens only when someone picks a theme.
 *
 * Applying belongs to Substrate rather than to the selector. The attribute has
 * to sit on `.gr-root`, because that is the element the tokens are defined on,
 * and Substrate is what renders it — a fresh one per page. The selector lives
 * in the footer and is not the owner of the page's root.
 */

export const THEMES = [
  { id: "taupe", label: "Taupe" },
  { id: "dark", label: "Dark" },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];

export const THEME_STORAGE_KEY = "gr-theme";

/** Taupe is the no-attribute state, so it is also the fallback. */
export const DEFAULT_THEME: ThemeId = "taupe";

const isTheme = (value: unknown): value is ThemeId =>
  THEMES.some(({ id }) => id === value);

/**
 * The stored choice, or the default.
 *
 * Falls back rather than throwing on a value that is no longer offered: Grove
 * and Light were retired from the menu while readers still had them saved.
 */
export const readStoredTheme = (): ThemeId => {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : DEFAULT_THEME;
  } catch {
    // Private browsing and blocked storage both throw on access.
    return DEFAULT_THEME;
  }
};

export const storeTheme = (theme: ThemeId): void => {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // A reader who cannot persist still gets the theme for this page.
  }
};

/** Taupe removes the attribute rather than setting a redundant one. */
export const applyTheme = (root: HTMLElement, theme: ThemeId): void => {
  if (theme === DEFAULT_THEME) delete root.dataset.theme;
  else root.dataset.theme = theme;
};
