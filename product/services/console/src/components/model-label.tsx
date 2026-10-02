import {
  modelProviderIcon,
  modelDisplayName,
} from "@gradiated/contracts/model-catalog";
import { Boxes } from "lucide-react";

import type { Option } from "@/components/option-select";
import { cn } from "@/lib/utils";

export const ModelIcon = ({
  id,
  className,
}: {
  id: string;
  className?: string;
}) => {
  const icon = modelProviderIcon(id);

  return icon ? (
    <img
      src={icon}
      alt=""
      aria-hidden="true"
      className={cn("size-4 shrink-0 dark:invert", className)}
    />
  ) : (
    <Boxes aria-hidden="true" className={cn("size-4 shrink-0", className)} />
  );
};

export const ModelLabel = ({
  id,
  label = modelDisplayName(id),
  className,
  iconClassName,
}: {
  id: string | null | undefined;
  label?: string;
  className?: string;
  iconClassName?: string;
}) => (
  <span
    className={cn(
      "inline-flex min-w-0 items-center gap-2 align-middle",
      className,
    )}
  >
    {id ? <ModelIcon id={id} className={cn(iconClassName)} /> : null}
    <span className="truncate">{label}</span>
  </span>
);

export const modelOption = <Id extends string>(id: Id) => ({
  value: id,
  label: modelDisplayName(id),
});

export const ModelOption = ({ value, label }: Option<string>) => (
  <ModelLabel id={value} label={label} />
);
