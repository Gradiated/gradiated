import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import type { BillingAccount } from "@/api/queries";
import { Toaster } from "@/components/ui/sonner";
import { billing } from "@/stories/handlers";
import { createStoryQueryClient } from "@/stories/query-client";

export const Providers = ({ children }: { children: ReactNode }) => {
  const [queryClient] = useState(() => createStoryQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background">{children}</div>
      <Toaster />
    </QueryClientProvider>
  );
};

export const account = (
  overrides: Partial<BillingAccount> = {},
): BillingAccount => ({
  ...billing,
  mode: "prepaid",
  ...overrides,
});
