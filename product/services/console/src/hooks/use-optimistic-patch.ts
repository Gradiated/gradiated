import { useState } from "react";
import {
  hashKey,
  useMutation,
  useMutationState,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

export const useOptimisticValue = <Value, Patch>(
  mutationKey: QueryKey,
  value: Value,
  apply: (value: Value, patch: Patch) => Value,
): Value => {
  const patches = useMutationState({
    filters: { mutationKey, exact: true, status: "pending" },
    select: (mutation) => mutation.state.variables as Patch,
  });

  return patches.reduce(apply, value);
};

export const useOptimisticPatch = <Result, Patch>({
  mutationKey,
  queryKey,
  mutationFn,
  commit,
}: {
  mutationKey: QueryKey;
  queryKey: QueryKey;
  mutationFn: (patch: Patch) => Promise<Result>;
  commit: (result: Result, patch: Patch) => void;
}) => {
  const client = useQueryClient();

  const scope = hashKey(mutationKey);
  const [errors, setErrors] = useState<Record<string, Error | null>>({});
  const mutation = useMutation({
    mutationKey,
    scope: { id: scope },
    mutationFn,
    onMutate: () => {
      setErrors((current) => ({ ...current, [scope]: null }));
      return client.cancelQueries({ queryKey });
    },
    onError: (failure) =>
      setErrors((current) => ({ ...current, [scope]: failure })),
    onSuccess: async (result, patch) => {
      // A refetch started during the save must not overwrite its response.
      await client.cancelQueries({ queryKey });
      commit(result, patch);
    },
    onSettled: () => {
      if (client.isMutating({ mutationKey, exact: true }) === 1) {
        void client.invalidateQueries({ queryKey });
      }
    },
  });

  return { ...mutation, error: errors[scope] ?? null };
};
