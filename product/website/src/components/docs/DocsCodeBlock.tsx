import { isValidElement, useState } from "react";
import type { ComponentPropsWithoutRef, ReactElement, ReactNode } from "react";

const getCodeText = (node: ReactNode): string => {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) return node.map(getCodeText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return getCodeText(node.props.children);
  }
  return "";
};

export const DocsCodeBlock = ({
  children,
  className = "",
  ...props
}: ComponentPropsWithoutRef<"pre">): ReactElement => {
  const [copied, setCopied] = useState(false);
  const copyCode = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(getCodeText(children).trimEnd());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="docs-code-block relative my-[27px]" data-docs-code-block>
      <button
        className="absolute right-4 top-3 z-[1] cursor-pointer border-0 bg-transparent px-2 py-1 font-site-mono text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--code-muted)] hover:text-[var(--code-fg)] focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-[var(--code-fg)]"
        onClick={copyCode}
        type="button"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <pre
        className={`m-0 overflow-x-auto rounded-xl border border-[var(--code-border)] bg-[var(--code-bg)] px-6 py-[22px] pr-24 font-site-mono text-[12.5px] leading-[1.72] text-[var(--code-fg)] shadow-[var(--code-shadow)] max-[500px]:px-4 max-[500px]:py-[18px] max-[500px]:text-[11.5px] ${className}`}
        {...props}
      >
        {children}
      </pre>
    </div>
  );
};

export const DocsInlineCode = (
  props: ComponentPropsWithoutRef<"code">,
): ReactElement => {
  const block = props.className?.includes("hljs");
  return (
    <code
      {...props}
      className={
        block
          ? `bg-transparent p-0 font-inherit ${props.className ?? ""}`
          : `bg-[rgba(28,27,24,0.08)] px-[5px] py-0.5 font-site-mono text-[0.88em] font-medium leading-[1.4] ${props.className ?? ""}`
      }
    />
  );
};
