import { Fragment, useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactElement } from "react";
import { useNavigate } from "react-router-dom";

type Entry = {
  group: string;
  path: string;
  title: string;
  heading?: string;
  text: string;
};

const MAX_RESULTS = 12;

let indexRequest: Promise<Entry[]> | null = null;

/* Written by prerender; fetched once, the first time anyone opens search. */
const loadIndex = (): Promise<Entry[]> => {
  indexRequest ??= fetch("/docs/search.json")
    .then((response) => {
      if (!response.ok) throw new Error(`search index: ${response.status}`);
      return response.json() as Promise<{ entries: Entry[] }>;
    })
    .then((index) => index.entries)
    .catch((error: unknown) => {
      indexRequest = null;
      throw error;
    });
  return indexRequest;
};

const score = (entry: Entry, words: string[]): number => {
  const title = entry.title.toLowerCase();
  const heading = (entry.heading ?? "").toLowerCase();
  const text = entry.text.toLowerCase();
  let total = 0;

  for (const word of words) {
    const inHeading = heading.includes(word);
    const inTitle = title.includes(word);
    const inText = text.includes(word);
    if (!inHeading && !inTitle && !inText) return 0;
    total +=
      (heading.startsWith(word) ? 6 : 0) +
      (inHeading ? 5 : 0) +
      (inTitle ? 3 : 0) +
      (inText ? 1 : 0);
  }
  return entry.heading ? total : total + 1;
};

export const searchEntries = (entries: Entry[], query: string): Entry[] => {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [];

  return entries
    .map((entry) => ({ entry, score: score(entry, words) }))
    .filter((result) => result.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, MAX_RESULTS)
    .map((result) => result.entry);
};

/* The text around the first word that matched, with matches marked. */
const Snippet = ({ text, words }: { text: string; words: string[] }) => {
  const lower = text.toLowerCase();
  const at = Math.max(
    0,
    Math.min(...words.map((word) => lower.indexOf(word)).filter((i) => i >= 0)),
  );
  const start = Math.max(0, at - 40);
  const slice = `${start ? "…" : ""}${text.slice(start, start + 160)}${text.length > start + 160 ? "…" : ""}`;
  const pattern = new RegExp(
    `(${words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi",
  );

  return (
    <>
      {slice
        .split(pattern)
        .map((part, index) =>
          index % 2 ? (
            <mark key={index}>{part}</mark>
          ) : (
            <Fragment key={index}>{part}</Fragment>
          ),
        )}
    </>
  );
};

const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement &&
  (target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

export const DocsSearch = (): ReactElement => {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const listId = useId();

  const open = () => {
    if (!dialog.current?.open) dialog.current?.showModal();
    input.current?.select();
    loadIndex()
      .then((loaded) => {
        setEntries(loaded);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const shortcut =
        (event.key === "k" && (event.metaKey || event.ctrlKey)) ||
        (event.key === "/" && !isTyping(event.target));
      if (!shortcut) return;

      event.preventDefault();
      open();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // `open` reads only refs and state setters, so the first one stays valid.
  }, []);

  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const results = useMemo(
    () => (entries ? searchEntries(entries, query) : []),
    [entries, query],
  );

  useEffect(() => setActive(0), [query]);

  const go = (entry: Entry | undefined) => {
    if (!entry) return;
    dialog.current?.close();
    setQuery("");
    navigate(entry.path);
    const hash = entry.path.split("#")[1];
    window.setTimeout(() => {
      if (hash) document.getElementById(hash)?.scrollIntoView();
      else window.scrollTo({ top: 0 });
    }, 0);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) =>
        results.length ? (current + step + results.length) % results.length : 0,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(results[active]);
    }
  };

  return (
    <>
      <button
        aria-haspopup="dialog"
        aria-label="Search the docs"
        aria-keyshortcuts="Control+K Meta+K /"
        className="gr-doc-search-open"
        onClick={open}
        type="button"
      >
        <svg
          aria-hidden="true"
          fill="none"
          height="13"
          stroke="currentColor"
          strokeWidth="1.6"
          viewBox="0 0 16 16"
          width="13"
        >
          <circle cx="7" cy="7" r="4.5" />
          <path d="m10.5 10.5 3.5 3.5" />
        </svg>
        <span>Search</span>
        <kbd>/</kbd>
      </button>

      <dialog
        aria-label="Search the docs"
        className="gr-doc-search"
        onClick={(event) => {
          if (event.target === dialog.current) dialog.current.close();
        }}
        ref={dialog}
      >
        <div className="gr-doc-search-panel">
          <input
            aria-activedescendant={
              results[active] ? `${listId}-${active}` : undefined
            }
            aria-autocomplete="list"
            aria-controls={listId}
            aria-expanded={results.length > 0}
            autoComplete="off"
            className="gr-doc-search-input"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search the docs: recipes, endpoints, error codes…"
            ref={input}
            role="combobox"
            spellCheck={false}
            type="search"
            value={query}
          />
          <ul className="gr-doc-search-results" id={listId} role="listbox">
            {results.map((entry, index) => (
              <li
                aria-selected={index === active}
                id={`${listId}-${index}`}
                key={entry.path}
                onClick={() => go(entry)}
                onMouseMove={() => setActive(index)}
                role="option"
              >
                <span className="gr-doc-search-where">
                  {entry.group} · {entry.title}
                </span>
                <span className="gr-doc-search-heading">
                  {entry.heading ?? entry.title}
                </span>
                {entry.text ? (
                  <span className="gr-doc-search-text">
                    <Snippet text={entry.text} words={words} />
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          <p aria-live="polite" className="gr-doc-search-status">
            {failed
              ? "Search isn't available right now."
              : !entries
                ? "Loading…"
                : words.length && !results.length
                  ? `Nothing matches "${query}".`
                  : words.length
                    ? "↑↓ to move, Enter to open, Esc to close"
                    : `${entries.length} sections, endpoints and error codes`}
          </p>
        </div>
      </dialog>
    </>
  );
};
