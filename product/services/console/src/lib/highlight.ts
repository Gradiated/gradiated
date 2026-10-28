import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";

// The grammars the docs highlight with rehype-highlight, registered on demand.
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("json", json);
hljs.registerLanguage("python", python);
hljs.registerLanguage("typescript", typescript);

export type HighlightLanguage = "bash" | "json" | "python" | "typescript";

// highlight.js escapes the source, so the result is safe to render as markup.
export const highlightCode = (code: string, language: HighlightLanguage) =>
  hljs.highlight(code, { language }).value;
