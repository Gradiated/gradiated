import { Check, Copy, X } from "lucide-react";

import type { CopyState } from "@/hooks/use-copy-to-clipboard";

export const CopyStateIcon = ({
  state,
  className,
}: {
  state: CopyState;
  className?: string;
}) => {
  if (state === "copied") return <Check className={className} />;
  if (state === "failed") return <X className={className} />;

  return <Copy className={className} />;
};
