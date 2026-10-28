import { useQuery, useQueryClient } from "@tanstack/react-query";

import { playgroundCredentialQuery } from "@/api/queries";
import { useProductContext } from "@/hooks/use-product-context";

// The playground calls the gateway with a short-lived hidden key minted for the
// signed-in user, so nobody has to create or paste an API key first.
export const usePlaygroundCredential = () => {
  const { organizationId, workspaceId } = useProductContext();
  const queryClient = useQueryClient();
  const query = playgroundCredentialQuery(organizationId, workspaceId);
  useQuery(query);

  const secret = async (renew: boolean) => {
    const { secret } = await queryClient.fetchQuery(
      renew ? { ...query, staleTime: 0 } : query,
    );

    return secret;
  };

  return secret;
};
