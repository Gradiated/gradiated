import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const Canvas = ({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) => (
  <div className={cn("min-h-screen bg-background p-8", className)}>
    {children}
  </div>
);

export const States = ({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) => (
  <Canvas>
    <div
      className={cn(
        "grid grid-cols-[repeat(auto-fill,minmax(14rem,1fr))] items-start gap-x-12 gap-y-10",
        className,
      )}
    >
      {children}
    </div>
  </Canvas>
);

export const State = ({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) => (
  <section className="flex min-w-0 flex-col items-start gap-3">
    <h6 className="text-[13px] font-semibold tracking-tight text-foreground">
      {label}
    </h6>
    {children}
  </section>
);
