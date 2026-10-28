import { CopyStateIcon } from "@/components/copy-state-icon";
import type { Option } from "@/components/option-select";
import { Button } from "@/components/ui/button";
import { copyLabel, useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { highlightCode, type HighlightLanguage } from "@/lib/highlight";
import { cn } from "@/lib/utils";

// A highlighted code sample with variant tabs and a copy button in its header.
export const CodeSnippet = <Value extends string>({
  code,
  language,
  value,
  options,
  onValueChange,
  copyText = "Copy snippet",
  className,
}: {
  code: string;
  language: HighlightLanguage;
  value: Value;
  options: readonly Option<Value>[];
  onValueChange: (value: Value) => void;
  copyText?: string;
  className?: string;
}) => {
  const { state, copy } = useCopyToClipboard();

  return (
    <div
      className={cn(
        "code-snippet min-w-0 max-w-full overflow-hidden rounded-lg",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-(--code-border) px-3">
        <div role="tablist" className="flex gap-4">
          {options.map((option) => {
            const selected = option.value === value;

            return (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={selected}
                className={cn(
                  "-mb-px border-b-2 py-2 font-mono text-[10px] uppercase tracking-[0.06em] transition-colors outline-none focus-visible:text-(--code-fg)",
                  selected
                    ? "border-(--code-fg) text-(--code-fg)"
                    : "border-transparent text-(--code-muted) hover:text-(--code-fg)",
                )}
                onClick={() => onValueChange(option.value)}
              >
                {option.label}
              </button>
            );
          })}
        </div>
        <Button
          variant="ghost"
          size="icon-xs"
          className="text-(--code-muted) hover:bg-white/10 hover:text-(--code-fg)"
          aria-label={copyLabel(state, copyText)}
          onClick={() => void copy(code)}
        >
          <CopyStateIcon state={state} />
        </Button>
      </div>
      <pre className="max-h-96 overflow-auto p-3 font-mono text-[11px] leading-5">
        <code
          dangerouslySetInnerHTML={{ __html: highlightCode(code, language) }}
        />
      </pre>
    </div>
  );
};
