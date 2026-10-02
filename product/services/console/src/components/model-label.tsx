import {
  catalogModel,
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
  const icon = catalogModel(id)?.icon;

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

export const modelOption = <Id extends string,>(id: Id) => ({
  value: id,
  label: modelDisplayName(id),
});

export const ModelOption = ({ value, label }: Option<string>) => (
  <span className="inline-flex min-w-0 items-center gap-2">
    <ModelIcon id={value} />
    <span className="truncate">{label}</span>
  </span>
);
