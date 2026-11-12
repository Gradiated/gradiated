import { useProductContext } from "@/hooks/use-product-context";
import { privateModelName } from "@/lib/model-name";

export const usePrivateModelName = () => {
  const { selectedOrganization } = useProductContext();

  return (task: string, version?: string) =>
    selectedOrganization
      ? privateModelName(selectedOrganization.slug, task, version)
      : (version ?? task);
};
