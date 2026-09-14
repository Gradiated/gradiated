import { useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";

/**
 * A code sample: highlighted with the system's syntax roles, and copyable.
 *
 * The highlighter is deliberately small — comments, strings, numbers and a
 * handful of keywords. It covers the shapes actually shown on the site (JSX,
 * CSS custom properties, a few API calls) and nothing more. Pulling in a real
 * grammar would add weight for samples that are four lines long; if the docs
 * ever need genuine language support this should be replaced rather than
 * extended, because a regex highlighter that tries to be general is a regex
 * highlighter that is quietly wrong.
 *
 * Tokens become React elements, never markup strings — a sample containing
 * angle brackets or braces must render as text, not be parsed as HTML.
 */

const TOKEN =
  /(\/\*[\s\S]*?\*\/|\/\/[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)|(\b\d+(?:\.\d+)?\b)|(\b(?:const|let|await|async|import|export|from|return|function|new|class|true|false|null)\b)/g;

const KIND = ["comment", "string", "number", "keyword"] as const;

const highlight = (code: string): ReactNode[] => {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of code.matchAll(TOKEN)) {
    const at = match.index ?? 0;
    if (at > last) out.push(code.slice(last, at));
    const kind = KIND[match.slice(1).findIndex(Boolean)];
    out.push(
      <span className={`tok-${kind}`} key={(key += 1)}>
        {match[0]}
      </span>,
    );
    last = at + match[0].length;
  }
  if (last < code.length) out.push(code.slice(last));
  return out;
};

export const CodeBlock = ({
  code,
  copyable = true,
}: {
  code: string;
  /** Off where the surrounding component provides its own copy control — two
   *  for one sample is one too many. */
  copyable?: boolean;
}): ReactElement => {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access can be refused — permissions, or a non-secure origin.
      // Say so rather than showing a success that did not happen.
      setCopied(false);
    }
  };

  return (
    <div className="gr-codewrap">
      <pre className="gr-codeblock">
        <code>{highlight(code)}</code>
      </pre>
      {copyable ? (
        <button
          aria-label="Copy code"
          className="gr-copy"
          onClick={copy}
          type="button"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      ) : null}
      {/* Announced rather than only shown, so the confirmation reaches a
          screen reader as well as an eye. */}
      <span aria-live="polite" className="gr-visually-hidden">
        {copied ? "Copied to clipboard" : ""}
      </span>
    </div>
  );
};
