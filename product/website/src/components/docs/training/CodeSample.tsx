import { useState } from "react";
import type { ReactElement, ReactNode } from "react";

/* A small highlighter for the widgets' generated samples. It emits the same
   hljs-* classes rehype-highlight gives the static samples, so both share one
   palette, without shipping highlight.js to the browser. */

const KEYWORDS: Record<string, string[]> = {
  python: [
    "from",
    "import",
    "as",
    "def",
    "return",
    "if",
    "else",
    "for",
    "in",
    "None",
    "True",
    "False",
    "lambda",
    "with",
  ],
  typescript: [
    "import",
    "from",
    "const",
    "let",
    "await",
    "async",
    "new",
    "return",
    "if",
    "else",
    "export",
    "true",
    "false",
    "null",
  ],
  go: [
    "func",
    "package",
    "import",
    "return",
    "if",
    "err",
    "nil",
    "var",
    ":=",
    "range",
    "for",
    "go",
  ],
  rust: [
    "use",
    "let",
    "mut",
    "fn",
    "async",
    "await",
    "Some",
    "None",
    "pub",
    "impl",
    "match",
    "if",
    "else",
  ],
  bash: ["export", "cat", "cd"],
};

const TOKEN =
  /(#[^\n]*|\/\/[^\n]*)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`[^`]*`)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)/g;

export const highlight = (code: string, lang: string): ReactNode[] => {
  const keywords = new Set(KEYWORDS[lang] ?? []);
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;

  for (const match of code.matchAll(TOKEN)) {
    const [text, comment, string, number, word] = match;
    const at = match.index ?? 0;
    if (at > last) nodes.push(code.slice(last, at));
    last = at + text.length;

    const isComment =
      comment !== undefined &&
      (lang === "bash" || lang === "python"
        ? comment.startsWith("#")
        : comment.startsWith("//"));
    const className = isComment
      ? "hljs-comment"
      : string !== undefined
        ? "hljs-string"
        : number !== undefined
          ? "hljs-number"
          : word !== undefined && keywords.has(word)
            ? "hljs-keyword"
            : null;

    if (comment !== undefined && !isComment) {
      nodes.push(text);
      continue;
    }
    nodes.push(
      className ? (
        <span className={className} key={key++}>
          {text}
        </span>
      ) : (
        text
      ),
    );
  }

  if (last < code.length) nodes.push(code.slice(last));
  return nodes;
};

export const CodeSample = ({
  code,
  lang,
  label,
}: {
  code: string;
  lang: string;
  label?: string;
}): ReactElement => {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard
      .writeText(code)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => setCopied(false));
  };

  return (
    <div className="gr-doc-code" data-lang={lang}>
      <div className="gr-doc-code-bar">
        <span className="gr-doc-code-lang">{label ?? lang}</span>
        <button className="gr-doc-copy" onClick={copy} type="button">
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>
        <code>{highlight(code, lang)}</code>
      </pre>
    </div>
  );
};
