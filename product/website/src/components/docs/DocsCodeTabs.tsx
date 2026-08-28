import { Children, isValidElement, useId, useState } from "react";
import type { ReactElement, ReactNode } from "react";

type DocsCodeTabProps = {
  children: ReactNode;
  label: string;
};

type DocsCodeVariantProps = {
  children: ReactNode;
  label: string;
};

export const DocsCodeTab = ({ children }: DocsCodeTabProps): ReactElement => (
  <>{children}</>
);

export const DocsCodeVariant = ({
  children,
}: DocsCodeVariantProps): ReactElement => <>{children}</>;

export const DocsCodeTabs = ({
  action,
  children,
}: {
  action?: ReactNode;
  children: ReactNode;
}): ReactElement => {
  const tabs = Children.toArray(children).filter(
    (child): child is ReactElement<DocsCodeTabProps> =>
      isValidElement<DocsCodeTabProps>(child),
  );
  const [selected, setSelected] = useState(0);
  const id = useId();
  const activeTab = tabs[selected] ?? tabs[0];

  return (
    <div className="my-7 max-w-[760px]">
      <div className="flex flex-wrap items-end justify-between gap-x-5 border-b border-line">
        <div aria-label="Code examples" className="flex gap-6" role="tablist">
          {tabs.map((tab, index) => (
            <button
              aria-controls={`${id}-panel-${index}`}
              aria-selected={selected === index}
              className={`cursor-pointer border-0 border-b bg-transparent px-0 pb-2.5 font-site-mono text-[10px] font-medium uppercase tracking-[0.06em] ${
                selected === index
                  ? "border-ink text-ink"
                  : "border-transparent text-muted hover:text-ink"
              }`}
              id={`${id}-tab-${index}`}
              key={tab.props.label}
              onClick={() => setSelected(index)}
              role="tab"
              type="button"
            >
              {tab.props.label}
            </button>
          ))}
        </div>
        {action && <div className="pb-2.5">{action}</div>}
      </div>
      {activeTab && (
        <div
          aria-labelledby={`${id}-tab-${selected}`}
          className="pt-3 [&_[data-docs-code-block]]:my-0"
          id={`${id}-panel-${selected}`}
          role="tabpanel"
        >
          {activeTab.props.children}
        </div>
      )}
    </div>
  );
};

export const DocsCodeVariants = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const variants = Children.toArray(children).filter(
    (child): child is ReactElement<DocsCodeVariantProps> =>
      isValidElement<DocsCodeVariantProps>(child),
  );
  const [selected, setSelected] = useState(0);
  const id = useId();
  const activeVariant = variants[selected] ?? variants[0];

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--code-border)] bg-[var(--code-bg)] shadow-[var(--code-shadow)]">
      <div
        aria-label="Request format"
        className="flex gap-6 border-b border-[var(--code-border)] px-6 pt-4 max-[500px]:px-4"
        role="tablist"
      >
        {variants.map((variant, index) => (
          <button
            aria-controls={`${id}-panel-${index}`}
            aria-selected={selected === index}
            className={`cursor-pointer border-0 border-b bg-transparent px-0 pb-3 font-site-mono text-[10px] font-medium uppercase tracking-[0.06em] ${
              selected === index
                ? "border-[var(--code-fg)] text-[var(--code-fg)]"
                : "border-transparent text-[var(--code-muted)] hover:text-[var(--code-fg)]"
            }`}
            id={`${id}-tab-${index}`}
            key={variant.props.label}
            onClick={() => setSelected(index)}
            role="tab"
            type="button"
          >
            {variant.props.label}
          </button>
        ))}
      </div>
      {activeVariant && (
        <div
          aria-labelledby={`${id}-tab-${selected}`}
          className="[&_[data-docs-code-block]]:my-0 [&_[data-docs-code-block]>pre]:rounded-none [&_[data-docs-code-block]>pre]:border-0 [&_[data-docs-code-block]>pre]:shadow-none"
          id={`${id}-panel-${selected}`}
          role="tabpanel"
        >
          {activeVariant.props.children}
        </div>
      )}
    </div>
  );
};
