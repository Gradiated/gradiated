import type { ReactNode } from "react";

import { Brand } from "@/components/brand";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export const AuthCard = ({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) => (
  <main className="flex min-h-svh flex-col items-center justify-center bg-muted p-6 md:p-10">
    <div className={cn("w-full max-w-md", className)}>
      <div className="mb-6">
        <Brand />
      </div>
      <Card className="overflow-hidden p-0 shadow-xl shadow-black/5">
        <CardContent className="p-0">{children}</CardContent>
      </Card>
    </div>
  </main>
);
