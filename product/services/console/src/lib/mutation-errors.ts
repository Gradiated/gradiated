import type { Mutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { errorMessage, httpStatus } from "@/lib/errors";

declare module "@tanstack/react-query" {
  interface Register {
    // Naming a fallback message opts a mutation into an error toast.
    mutationMeta: { errorMessage?: string };
  }
}

// The mutation cache shows one toast for every mutation that opts in, so call
// sites name their message instead of each writing an onError handler.
export const toastMutationError = (
  error: Error,
  _variables: unknown,
  _context: unknown,
  mutation: Mutation<unknown, unknown, unknown, unknown>,
) => {
  const fallback = mutation.meta?.errorMessage;
  if (!fallback || httpStatus(error) === 401) return;

  toast.error(errorMessage(error, fallback));
};
