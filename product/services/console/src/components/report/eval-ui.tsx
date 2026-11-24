import type { EvalModel } from "@gradiated/contracts";
import type { ReactNode } from "react";

import { Logo } from "@/components/logo";
import { cn } from "@/lib/utils";

export const MODEL_COLORS = ["#2a78d6", "#eb6834"] as const;
export const SAME_COLOR = "#e4e3dd";

const PROVIDER_ICONS = new Set([
  "anthropic",
  "deepseek",
  "openai",
  "qwen",
  "zai",
]);

export const ModelMark = ({
  model,
  boxed = false,
}: {
  model: EvalModel;
  boxed?: boolean;
}) => {
  const icon =
    model.provider === "gradiated" ? (
      <Logo className="size-3.5" />
    ) : model.provider && PROVIDER_ICONS.has(model.provider) ? (
      <img
        src={`/model-providers/${model.provider}.svg`}
        alt=""
        className="size-3.5"
      />
    ) : null;
  if (!icon) return null;

  return boxed ? (
    <span className="grid size-7 shrink-0 place-items-center rounded-md border bg-card">
      {icon}
    </span>
  ) : (
    icon
  );
};

export const Swatch = ({ color }: { color: string }) => (
  <span
    aria-hidden
    className="inline-block size-2.5 shrink-0 rounded-[3px]"
    style={{ background: color }}
  />
);

export const Legend = ({ items }: { items: [string, string][] }) => (
  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
    {items.map(([color, label]) => (
      <span key={label} className="inline-flex items-center gap-1.5">
        <Swatch color={color} />
        {label}
      </span>
    ))}
  </div>
);

export const Panel = ({
  title,
  subtitle,
  children,
  className,
}: {
  title?: string | undefined;
  subtitle?: string | undefined;
  children: ReactNode;
  className?: string;
}) => (
  <section
    className={cn(
      "flex min-w-0 flex-col gap-4 rounded-xl border bg-card px-6 py-5",
      className,
    )}
  >
    {title || subtitle ? (
      <header className="flex flex-col gap-1">
        {title ? (
          <h3 className="text-[15px] leading-5 font-semibold">{title}</h3>
        ) : null}
        {subtitle ? (
          <p className="text-[13px] leading-5 text-muted-foreground">
            {subtitle}
          </p>
        ) : null}
      </header>
    ) : null}
    {children}
  </section>
);

export const SectionLabel = ({ children }: { children: ReactNode }) => (
  <h4 className="text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
    {children}
  </h4>
);

export const ScoreChip = ({
  model,
  label,
  rate,
}: {
  model?: EvalModel;
  label: string;
  rate: number | null;
}) => (
  <span
    className={cn(
      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium tabular-nums",
      rate === null
        ? "border-border bg-muted text-muted-foreground"
        : rate >= 1
          ? "border-[#cadb87] bg-[#f2f7d9] text-[#475617]"
          : rate <= 0
            ? "border-[#efc2bf] bg-[#fcecea] text-[#9c2a24]"
            : "border-[#e4c880] bg-[#fbf3db] text-[#755b15]",
    )}
  >
    {model ? <ModelMark model={model} /> : null}
    {label}
  </span>
);
