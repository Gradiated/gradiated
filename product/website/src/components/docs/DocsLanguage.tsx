import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactElement, ReactNode } from "react";

import { SDK_LANGUAGES, isSdkLanguage } from "./training/data";
import type { SdkLanguage } from "./training/data";

const STORAGE_KEY = "gradiated.docs.lang";

/* Tab labels that mean the same language as a picker choice. */
const ALIASES: Record<SdkLanguage, string[]> = {
  Python: ["Python"],
  TypeScript: ["TypeScript", "Node", "JavaScript"],
  Go: ["Go"],
  Rust: ["Rust"],
  CLI: ["CLI", "CLI (YAML)"],
};

export const languageOfLabel = (label: string): SdkLanguage | null =>
  SDK_LANGUAGES.find((language) => ALIASES[language].includes(label)) ?? null;

export const indexForLanguage = (
  labels: readonly string[],
  language: SdkLanguage | null,
): number =>
  language
    ? labels.findIndex((label) => ALIASES[language].includes(label))
    : -1;

type LanguageState = {
  language: SdkLanguage | null;
  /** Choose a language; `anchor` keeps that element still on screen while
      every tab group on the page swaps to the new language. */
  setLanguage: (language: SdkLanguage, anchor?: Element | null) => void;
};

const DocsLanguageContext = createContext<LanguageState>({
  language: null,
  setLanguage: () => {},
});

export const useDocsLanguage = (): LanguageState =>
  useContext(DocsLanguageContext);

/** The reader's language, or Python until they choose. */
export const useSdkLanguage = (): SdkLanguage =>
  useDocsLanguage().language ?? "Python";

export const DocsLanguageProvider = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const [language, setLanguageState] = useState<SdkLanguage | null>(null);
  const anchor = useRef<{ element: Element; top: number } | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (isSdkLanguage(saved)) setLanguageState(saved);
    } catch {
      // Storage can be blocked; the default still works.
    }

    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY && isSdkLanguage(event.newValue)) {
        setLanguageState(event.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  /* Switching every sample on the page changes the height of everything above
     the one that was clicked; scroll by the difference so it does not move. */
  useLayoutEffect(() => {
    const held = anchor.current;
    anchor.current = null;
    if (!held || !held.element.isConnected) return;

    const delta = held.element.getBoundingClientRect().top - held.top;
    if (Math.abs(delta) > 1) window.scrollBy({ top: delta });
  }, [language]);

  const setLanguage = useCallback(
    (next: SdkLanguage, element?: Element | null) => {
      if (element) {
        anchor.current = { element, top: element.getBoundingClientRect().top };
      }
      setLanguageState(next);
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Not persisted, but this page still switches.
      }
    },
    [],
  );

  const value = useMemo(
    () => ({ language, setLanguage }),
    [language, setLanguage],
  );

  return (
    <DocsLanguageContext.Provider value={value}>
      {children}
    </DocsLanguageContext.Provider>
  );
};

/** The page-wide choice: every SDK sample on every page follows it. */
export const DocsLanguagePicker = (): ReactElement => {
  const { language, setLanguage } = useDocsLanguage();
  const current = language ?? "Python";

  return (
    <div
      aria-label="SDK language for every code sample"
      className="gr-doc-langpick"
      role="radiogroup"
    >
      {SDK_LANGUAGES.map((option) => (
        <button
          aria-checked={option === current}
          className="gr-doc-langpick-option"
          key={option}
          onClick={(event) => setLanguage(option, event.currentTarget)}
          onKeyDown={(event) => {
            const step =
              event.key === "ArrowRight"
                ? 1
                : event.key === "ArrowLeft"
                  ? -1
                  : 0;
            if (!step) return;

            event.preventDefault();
            const index = SDK_LANGUAGES.indexOf(current);
            const next =
              SDK_LANGUAGES[
                (index + step + SDK_LANGUAGES.length) % SDK_LANGUAGES.length
              ];
            setLanguage(next, event.currentTarget);
            const sibling = event.currentTarget.parentElement?.children[
              SDK_LANGUAGES.indexOf(next)
            ] as HTMLElement | undefined;
            sibling?.focus();
          }}
          role="radio"
          tabIndex={option === current ? 0 : -1}
          type="button"
        >
          {option}
        </button>
      ))}
    </div>
  );
};
