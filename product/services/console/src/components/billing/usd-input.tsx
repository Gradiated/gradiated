import type { ComponentProps } from "react";

import { Input } from "@/components/ui/input";

export const UsdInput = (props: ComponentProps<typeof Input>) => (
  <div className="relative">
    <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted-foreground">
      $
    </span>
    <Input className="pl-7" inputMode="decimal" autoComplete="off" {...props} />
  </div>
);
